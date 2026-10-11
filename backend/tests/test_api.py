import io
from datetime import timedelta
from sqlalchemy import select,func
from app.db import SessionLocal
from app.models import Influencer, InfluencerMetric, CollectionRun, News, ContactInteraction, Negotiation, MonitoringJob, now
from app.schemas import STAGES


def test_auth_protects_all_modules(client):
    for path in ('dashboard','influencers','negotiations','competitors','news','alerts','integrations/status','campaigns','collection-runs'):
        assert client.get('/api/'+path).status_code==401
    assert client.post('/api/auth/login',json={'email':'admin@papaia.local','password':'wrong'}).status_code==401
    response=client.post('/api/auth/login',json={'email':'admin@papaia.local','password':'test-password-12345'})
    assert response.status_code==200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert client.get('/api/auth/me').json()['email']=='admin@papaia.local'
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/influencers').status_code==401


def test_auth_rate_limit(client):
    for _ in range(20):
        assert client.post('/api/auth/login',json={'email':'a','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'a','password':'wrong'}).status_code==429


def test_crud_pipeline_dashboard_and_cascade(auth,influencer):
    created=auth.post('/api/influencers',json=influencer)
    assert created.status_code==201, created.text
    ident=created.json()['id']
    assert auth.post('/api/influencers',json=influencer).status_code==409
    for stage in STAGES:
        response=auth.patch(f'/api/influencers/{ident}',json={'stage':stage})
        assert response.status_code==200, response.text
        assert response.json()['stage']==stage
    assert auth.patch(f'/api/influencers/{ident}',json={'stage':'invalid'}).status_code==422
    assert auth.patch(f'/api/influencers/{ident}',json={'stage':None}).status_code==422
    auth.patch(f'/api/influencers/{ident}',json={'stage':'Parceria fechada','notes':'Observação','owner':'Equipe'})
    contact=auth.post(f'/api/influencers/{ident}/contacts',json={'channel':'Reunião','notes':'Conversa fictícia de teste'})
    assert contact.status_code==201
    campaign=auth.post('/api/campaigns',json={'name':'Campanha teste','objective':'B2B'}).json()
    negotiation=auth.post('/api/negotiations',json={'influencer_id':ident,'campaign_id':campaign['id'],'agreed_value':500})
    assert negotiation.status_code==201,negotiation.text
    nid=negotiation.json()['id']
    assert auth.patch('/api/negotiations/'+str(nid),json={'agreed_value':450}).json()['agreed_value']==450
    assert auth.patch('/api/negotiations/'+str(nid),json={'agreed_value':-1}).status_code==422
    detail=auth.get(f'/api/influencers/{ident}').json()
    assert len(detail['contacts'])==len(detail['negotiations'])==1
    dashboard=auth.get('/api/dashboard').json()
    assert dashboard['total_leads']==dashboard['closed']==1
    assert dashboard['conversion']==100
    assert auth.delete(f'/api/influencers/{ident}').status_code==204
    assert auth.get(f'/api/influencers/{ident}').status_code==404
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContactInteraction))==0
        assert db.scalar(select(func.count()).select_from(Negotiation))==0


def test_filters_pagination_latest_metrics(auth,influencer):
    auth.post('/api/influencers',json=influencer)
    auth.post('/api/influencers',json={**influencer,'name':'Outro','username':'outro','platform':'YouTube','engagement':1,'followers':100})
    assert auth.get('/api/influencers?platform=Instagram&min_followers=1000').json()['total']==1
    assert auth.get('/api/influencers?min_engagement=3').json()['total']==1
    assert auth.get('/api/influencers?page_size=1&page=2').json()['items'][0]['name']==influencer['name']
    assert auth.get('/api/influencers?page=0').status_code==422
    assert auth.get('/api/influencers?q=outro').json()['total']==1


def test_csv_atomic_dedup_and_no_metrics_fabrication(auth):
    csv='name,username,platform,url,followers,niches\nTeste,teste,Instagram,https://example.org/t,123,Introdução alimentar|Nutrição pediátrica\n'
    response=auth.post('/api/influencers/import',files={'file':('test.csv',csv,'text/csv')})
    assert response.json()=={'imported':1,'updated':0}
    response=auth.post('/api/influencers/import',files={'file':('test.csv',csv,'text/csv')})
    assert response.json()=={'imported':0,'updated':1}
    row=auth.get('/api/influencers').json()['items'][0]
    assert row['profiles'][0]['metrics']['engagement'] is None
    invalid=csv+'Invalid,bad,Unknown,https://example.org/b,42,Teste\n'
    assert auth.post('/api/influencers/import',files={'file':('bad.csv',invalid,'text/csv')}).status_code==422
    assert auth.get('/api/influencers').json()['total']==1


def test_score_missing_data_and_weights(auth,influencer):
    created=auth.post('/api/influencers',json={'name':'Sem dados','username':'sem_dados','platform':'TikTok','url':'https://example.org/s'}).json()
    response=auth.post(f'/api/influencers/{created["id"]}/score',json={})
    score=response.json()['score']
    assert score['value']==0
    assert score['confidence']==0
    assert all(not e['available'] for e in score['evidence'])
    ident=auth.post('/api/influencers',json=influencer).json()['id']
    result=auth.post(f'/api/influencers/{ident}/score',json={'campaign_type':'B2B'}).json()['score']
    assert result['value']==76
    assert result['confidence']==85
    assert next(e for e in result['evidence'] if e['criterion']=='credibility')['points']==0
    invalid={'theme':100,'audience':25,'engagement':20,'credibility':15,'commercial':10}
    assert auth.post(f'/api/influencers/{ident}/score',json={'weights':invalid}).status_code==422
    assert auth.post(f'/api/influencers/{ident}/score',json={'manual_value':95}).status_code==422
    manual=auth.post(f'/api/influencers/{ident}/score',json={'manual_value':60,'rationale':'Revisão documentada','evidence_urls':['https://example.org/evidence']})
    assert manual.json()['score']['manual'] is True
    assert auth.get('/api/influencers?min_score=50').json()['total']==1


def test_proposal_is_draft_only(auth,influencer):
    ident=auth.post('/api/influencers',json=influencer).json()['id']
    draft=auth.post(f'/api/influencers/{ident}/proposal?campaign_type=B2C').json()
    assert draft['requires_review'] is True and draft['sent'] is False
    assert 'famílias' in draft['draft']


def test_rss_collect_classify_dedup_alert_link(auth,rss,influencer,monkeypatch):
    monkeypatch.setattr('app.providers.fetch_public',lambda url:(rss,url))
    c=auth.post('/api/competitors',json={'name':'Concorrente fictício teste','website':'https://example.org','keywords':['introducao alimentar'],'sources':[{'url':'https://example.org/rss'}]})
    assert c.status_code==201,c.text
    response=auth.post('/api/news/collect')
    assert response.status_code==200,response.text
    assert response.json()['imported']==1
    item=auth.get('/api/news').json()['items'][0]
    assert item['url']=='https://example.org/parceria'
    assert item['category']=='Parceria' and item['relevance']==70
    assert '<script>' not in item['summary'] and 'bad()' not in item['summary']
    assert len(item['competitors'])==1
    assert auth.get('/api/alerts').json()['total']==1
    assert auth.post('/api/news/collect').status_code==429
    duplicate=auth.post('/api/news',json={'title':item['title'],'url':'https://example.org/parceria?fbclid=x','source':item['source']})
    assert duplicate.json()['id']==item['id']
    similar=auth.post('/api/news',json={'title':item['title']+'!','url':'https://example.org/other','source':item['source']})
    assert similar.json()['id']==item['id']
    assert auth.get('/api/news').json()['total']==1
    nid=item['id']
    assert auth.patch(f'/api/news/{nid}',json={'read':True,'watched':True}).status_code==200
    assert auth.get('/api/news?watched=true').json()['total']==1
    analyzed=auth.post(f'/api/news/{nid}/analyze').json()
    assert 'facts' in analyzed['analysis'] and 'interpretation' in analyzed['analysis']
    inf=auth.post('/api/influencers',json=influencer).json()
    assert auth.post(f'/api/news/{nid}/influencers',json={'influencer_id':inf['id'],'confirmed':False}).status_code==422
    linked=auth.post(f'/api/news/{nid}/influencers',json={'influencer_id':inf['id'],'confirmed':True})
    assert linked.status_code==201,linked.text
    assert linked.json()['influencers'][0]['stage']=='Descoberto'


def test_rss_failure_visible(auth,monkeypatch):
    from app.network import SourceError
    def fail(_): raise SourceError('Fonte indisponível')
    monkeypatch.setattr('app.providers.fetch_public',fail)
    auth.post('/api/competitors',json={'name':'Teste','website':'https://example.org','sources':[{'url':'https://example.org/feed'}]})
    result=auth.post('/api/news/collect').json()
    assert result['status']=='failed' and 'indisponível' in result['error']
    assert auth.get('/api/news').json()['total']==0
    assert auth.get('/api/collection-runs').json()['items'][0]['status']=='failed'


def test_pending_integration_never_mocks(auth):
    pending=auth.get('/api/integrations/status').json()
    assert next(p for p in pending['providers'] if p['name']=='Apify dataset')['status']=='pending'
    preview=auth.post('/api/influencers/discover',json={'query':'introdução alimentar'}).json()
    assert preview['status']=='confirmation_required'
    assert preview['inferred_niches']==['introdução alimentar']
    result=auth.post('/api/influencers/discover',json={'confirm':True}).json()
    assert result['status']=='failed' and result['imported']==0
    assert auth.get('/api/influencers').json()['total']==0


def test_origin_and_validation(auth,influencer):
    assert auth.post('/api/influencers',json=influencer,headers={'Origin':'https://evil.example'}).status_code==403
    assert auth.post('/api/influencers',json={**influencer,'url':'javascript:alert(1)'}).status_code==422
    assert auth.post('/api/influencers',json={**influencer,'followers':-1}).status_code==422
    assert auth.post('/api/influencers',json={**influencer,'engagement':101}).status_code==422
    assert auth.post('/api/influencers',json={**influencer,'secret_token':'bad'}).status_code==422


def test_alert_config_and_monitoring_jobs(auth):
    assert auth.patch('/api/alert-config',json={'threshold':95,'categories':[],'enabled':False}).status_code==200
    auth.post('/api/news',json={'title':'Nova parceria','source':'Fonte','url':'https://example.org/1'})
    assert auth.get('/api/alerts').json()['total']==0
    assert auth.get('/api/alert-config').json()['threshold']==95
    job=auth.get('/api/integrations/status').json()['jobs'][0]
    assert auth.patch('/api/monitoring/jobs/'+str(job['id']),json={'enabled':False,'interval_hours':48}).json()['interval_hours']==48


def test_competitor_update_delete_and_sources(auth):
    c=auth.post('/api/competitors',json={'name':'Teste','website':'https://example.org'}).json()
    assert auth.patch('/api/competitors/'+str(c['id']),json={'priority':'high','keywords':['produto']}).status_code==200
    source=auth.post(f'/api/competitors/{c["id"]}/sources',json={'url':'https://example.org/rss'}).json()
    assert auth.get('/api/competitors').json()['items'][0]['sources'][0]['id']==source['id']
    assert auth.delete('/api/sources/'+str(source['id'])).status_code==204
    assert auth.delete('/api/competitors/'+str(c['id'])).status_code==204
    assert auth.get('/api/competitors').json()['total']==0


def test_profile_update_keeps_metric_history_and_explicit_platform_link(auth,influencer):
    inf=auth.post('/api/influencers',json=influencer).json()
    pid=inf['profiles'][0]['id']
    response=auth.patch('/api/profiles/'+str(pid),json={**influencer,'followers':1500,'engagement':3})
    assert response.status_code==200,response.text
    assert response.json()['profiles'][0]['metrics']['followers']==1500
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(InfluencerMetric))==2
    linked=auth.post(f'/api/influencers/{inf["id"]}/profiles',json={**influencer,'platform':'YouTube','username':'teste_video','url':'https://youtube.com/@teste_video'})
    assert linked.status_code==201,linked.text
    assert len(linked.json()['profiles'])==2
    assert auth.get('/api/influencers').json()['total']==1
