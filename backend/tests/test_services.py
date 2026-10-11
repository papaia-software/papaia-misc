from types import SimpleNamespace
import pytest
import httpx
from sqlalchemy import select,func
from fastapi import HTTPException
from app.scoring import calculate
from app.services import canonical_url,classify,collection_lock,monitor_page
from app.network import resolve_public,SourceError,fetch_public
from app.providers import ApifyDatasetProvider,RSSProvider
from app.config import settings
from app.db import SessionLocal
from app.models import Competitor,CompetitorSource,MonitoringSnapshot,Alert,MonitoringJob,News,now

@pytest.mark.parametrize('category,title',[('Parceria','Anunciamos parceria estratégica'),('Nova funcionalidade','Nova funcionalidade clínica'),('Lançamento de produto','Lançamento do app'),('Alteração comercial','Mudança de preços'),('Investimento','Novo aporte'),('Expansão','Expansão regional'),('Outros','Uma publicação comum')])
def test_news_rules(category,title):
    assert classify(title)[0]==category


def test_followers_never_increase_score():
    inf=SimpleNamespace(niches=['introdução alimentar'],target_audience='Famílias',professional_category='Criadora')
    p=SimpleNamespace(biography='',evidence_urls=[],url='https://example.org')
    a=calculate(inf,p,SimpleNamespace(engagement=None,followers=1),'B2C')
    b=calculate(inf,p,SimpleNamespace(engagement=None,followers=10000000),'B2C')
    assert a['value']==b['value']==45
    assert a['confidence']==65
    assert calculate(inf,p,None,'B2B')['value']<a['value']


def test_canonicalization():
    assert canonical_url('https://EXAMPLE.org/a/?utm_source=x&b=2#title')=='https://example.org/a?b=2'
    assert canonical_url('https://example.org/b?ref=123')!='https://example.org/b'

@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','169.254.169.254','::1','fc00::1','0.0.0.0','192.168.1.2'])
def test_ssrf_rejects_nonpublic_dns(ip,monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(None,None,None,None,(ip,443))])
    with pytest.raises(SourceError): resolve_public('evil.example')


def test_ssrf_rejects_mixed_dns(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(None,None,None,None,(ip,443)) for ip in ['8.8.8.8','127.0.0.1']])
    with pytest.raises(SourceError):resolve_public('evil.example')


def test_public_fetch_pins_ip_and_sni(monkeypatch):
    monkeypatch.setattr('app.network.resolve_public',lambda host:'93.184.216.34')
    actual=httpx.Client
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,content=b'feed')
    monkeypatch.setattr('app.network.httpx.Client',lambda **kw:actual(transport=httpx.MockTransport(handler),**kw))
    assert fetch_public('https://example.org/feed')[0]==b'feed'
    assert requests[0].url.host=='93.184.216.34'
    assert requests[0].headers['host']=='example.org'
    assert requests[0].extensions['sni_hostname']=='example.org'


def test_redirect_revalidates_dns(monkeypatch):
    def resolve(host):
        if host=='private.example':raise SourceError('blocked')
        return '93.184.216.34'
    monkeypatch.setattr('app.network.resolve_public',resolve)
    actual=httpx.Client
    monkeypatch.setattr('app.network.httpx.Client',lambda **kw:actual(transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={'Location':'http://private.example'})),**kw))
    with pytest.raises(SourceError):fetch_public('https://example.org')


def test_apify_mapped_response_and_rate_limit(monkeypatch):
    cfg=settings()
    monkeypatch.setattr(cfg,'apify_token','test-secret')
    monkeypatch.setattr(cfg,'apify_dataset_id','test_dataset')
    monkeypatch.setattr(cfg,'apify_field_map','{"name":"fullName","username":"handle","platform":"network","url":"profileUrl","followers":"count"}')
    actual=httpx.Client
    def handler(request):
        assert request.url.path=='/v2/datasets/test_dataset/items'
        assert request.headers['authorization']=='Bearer test-secret'
        return httpx.Response(200,json=[{'fullName':'Fictício','handle':'@teste','network':'Instagram','profileUrl':'https://example.org/t','count':42}])
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kw:actual(transport=httpx.MockTransport(handler),**kw))
    records=ApifyDatasetProvider().discover()
    assert records[0].username=='teste' and records[0].engagement is None
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kw:actual(transport=httpx.MockTransport(lambda r:httpx.Response(429)),**kw))
    with pytest.raises(SourceError,match='limitou'):ApifyDatasetProvider().discover()


def test_apify_invalid_dataset_is_atomic(monkeypatch):
    cfg=settings()
    monkeypatch.setattr(cfg,'apify_token','test')
    monkeypatch.setattr(cfg,'apify_dataset_id','test')
    actual=httpx.Client
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kw:actual(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=[{'invented':'schema'}])),**kw))
    with pytest.raises(SourceError,match='incompatível'):ApifyDatasetProvider().discover()


def test_collection_lock_rejects_overlap():
    with collection_lock():
        with pytest.raises(HTTPException) as exc:
            with collection_lock():pass
        assert exc.value.status_code==409


def test_page_snapshots_diff_and_permissions(auth,monkeypatch):
    pages=[b'<html><main>Plano inicial R$ 10</main></html>',b'<html><main>Plano inicial R$ 20</main></html>']
    def fetch(url,**kwargs):
        if url.endswith('robots.txt'):return b'User-agent: *\nAllow: /',url
        return pages.pop(0),url
    monkeypatch.setattr('app.services.fetch_public',fetch)
    with SessionLocal() as db:
        c=Competitor(name='Fictício',website='https://example.org')
        db.add(c);db.flush()
        s=CompetitorSource(competitor_id=c.id,url='https://example.org/pricing',kind='page',access_confirmed=False)
        db.add(s);db.flush()
        with pytest.raises(SourceError,match='Confirme'):monitor_page(db,s)
        s.access_confirmed=True
        assert monitor_page(db,s)==1
        db.flush()
        assert monitor_page(db,s)==1
        db.commit()
        snapshot=db.scalar(select(MonitoringSnapshot).order_by(MonitoringSnapshot.id.desc()))
        assert '-Plano inicial R$ 10' in snapshot.diff and '+Plano inicial R$ 20' in snapshot.diff
        assert db.scalar(select(func.count()).select_from(Alert))==1


def test_scheduler_does_not_repeat_claimed_job(auth,monkeypatch):
    from app.scheduler import tick
    called=[]
    monkeypatch.setattr('app.scheduler.collect_sources',lambda db,key:called.append(key))
    tick();tick()
    assert called==['rss','page']


def test_page_redirect_blocked_before_access(monkeypatch):
    actual=httpx.Client
    called=[]
    monkeypatch.setattr('app.network.resolve_public',lambda host:'93.184.216.34')
    def handler(request):
        called.append(request)
        return httpx.Response(302,headers={'Location':'https://other.example/path'})
    monkeypatch.setattr('app.network.httpx.Client',lambda **kw:actual(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(SourceError,match='recadastro'):
        fetch_public('https://example.org',allowed_origin='example.org')
    assert len(called)==1


def test_public_cache_reuses_successful_bytes_and_respects_bounds(monkeypatch):
    from app.network import clear_cache
    calls=[]
    def fetch(url,allowed_origin=None):
        calls.append(url)
        return b'cached feed',url
    monkeypatch.setattr('app.network._fetch_public_uncached',fetch)
    assert fetch_public('https://example.org/cache')==fetch_public('https://example.org/cache')
    assert len(calls)==1
    fetch_public('https://example.org/cache',cache_ttl=0)
    assert len(calls)==2
    with pytest.raises(SourceError):fetch_public('https://example.org/cache',allowed_origin='other.example')
