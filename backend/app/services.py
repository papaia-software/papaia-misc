from contextlib import contextmanager
from datetime import timedelta
from difflib import SequenceMatcher, unified_diff
from hashlib import sha256
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from urllib.robotparser import RobotFileParser
import fcntl
import tempfile
from sqlalchemy import select, func, text
from fastapi import HTTPException
from bs4 import BeautifulSoup
from .models import *
from .db import engine
from .network import fetch_public, SourceError
from .providers import RSSProvider
from .schemas import InfluencerCreate, public_url
from .scoring import normalize

@contextmanager
def collection_lock():
    """Nonblocking global lock, shared by API workers and scheduler instances."""
    if engine.dialect.name == 'postgresql':
        with engine.connect() as conn:
            if not conn.scalar(text('SELECT pg_try_advisory_lock(873412901)')):
                raise HTTPException(409,'Uma coleta já está em andamento')
            try:
                yield
            finally:
                conn.execute(text('SELECT pg_advisory_unlock(873412901)'))
    else:
        path = tempfile.gettempdir()+'/papaia-collection-'+sha256(str(engine.url).encode()).hexdigest()[:16]+'.lock'
        with open(path,'w') as handle:
            try:
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raise HTTPException(409,'Uma coleta já está em andamento')
            try:
                yield
            finally:
                fcntl.flock(handle,fcntl.LOCK_UN)

def serialize(obj):
    return {c.name:getattr(obj,c.name) for c in obj.__table__.columns}

def get_or_404(db, model, ident):
    result = db.get(model,ident)
    if not result:
        raise HTTPException(404,'Registro não encontrado')
    return result

def audit(db,user,action,entity,ident=None):
    db.add(AuditLog(user_id=user.id if user else None,action=action,entity=entity,entity_id=ident))

def influencer_dict(db, influencer, detail=False):
    data = serialize(influencer)
    profiles = db.scalars(select(InfluencerProfile).where(InfluencerProfile.influencer_id==influencer.id)).all()
    data['profiles'] = []
    for profile in profiles:
        p = serialize(profile)
        metric = db.scalar(select(InfluencerMetric).where(InfluencerMetric.profile_id==profile.id).order_by(InfluencerMetric.id.desc()))
        p['metrics'] = serialize(metric) if metric else None
        data['profiles'].append(p)
    score = db.scalar(select(InfluencerScore).where(InfluencerScore.influencer_id==influencer.id).order_by(InfluencerScore.id.desc()))
    data['score'] = serialize(score) if score else None
    if score:
        data['score']['evidence'] = [serialize(e) for e in db.scalars(select(ScoreEvidence).where(ScoreEvidence.score_id==score.id))]
    if detail:
        data['score_history'] = [serialize(s) for s in db.scalars(select(InfluencerScore).where(InfluencerScore.influencer_id==influencer.id).order_by(InfluencerScore.id.desc()))]
        data['contacts'] = [serialize(c) for c in db.scalars(select(ContactInteraction).where(ContactInteraction.influencer_id==influencer.id).order_by(ContactInteraction.occurred_at.desc()))]
        data['negotiations'] = [serialize(n) for n in db.scalars(select(Negotiation).where(Negotiation.influencer_id==influencer.id))]
    return data

def insert_influencer(db, data: InfluencerCreate, provider='manual', upsert=False):
    existing = db.scalar(select(InfluencerProfile).where(InfluencerProfile.platform==data.platform,InfluencerProfile.username==data.username))
    if existing:
        if not upsert:
            raise HTTPException(409,'Perfil já cadastrado nesta plataforma')
        # Preserve curated CRM fields. Append only a metrics observation from this source.
        db.add(InfluencerMetric(profile_id=existing.id,**{k:getattr(data,k) for k in METRIC_FIELDS}))
        existing.updated_at = now()
        return db.get(Influencer,existing.influencer_id),False
    inf = Influencer(**{k:getattr(data,k) for k in ('name','professional_category','niches','region','language','target_audience')})
    db.add(inf)
    db.flush()
    profile = InfluencerProfile(influencer_id=inf.id,provider=provider,**{k:getattr(data,k) for k in ('platform','username','url','photo_url','biography','public_contact','evidence_urls','relevant_posts','previous_collaborations')})
    db.add(profile)
    db.flush()
    db.add(InfluencerMetric(profile_id=profile.id,**{k:getattr(data,k) for k in METRIC_FIELDS}))
    return inf,True

METRIC_FIELDS = ('followers','engagement','average_views','posting_frequency','audience_countries','audience_demographics')

def canonical_url(url):
    public_url(url)
    p=urlsplit(url)
    query = urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')))
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/') or '/',query,''))

CATEGORY_RULES = {
    'Alteração comercial':['preco','pricing','price','plano comercial','reajuste'],
    'Parceria':['parceria','partnership','colaboracao','partner'],
    'Investimento':['investimento','aporte','funding','investment'],
    'Nova funcionalidade':['funcionalidade','feature','atualizacao do produto'],
    'Lançamento de produto':['lancamento','launch','novo produto'],
    'Expansão':['expansao','expansion','novo mercado'],
    'Campanha de marketing':['campanha','campaign'],
    'Atualização institucional':['institucional','nova diretoria','acquisition'],
    'Tendência de mercado':['tendencia','trend','pesquisa','estudo']
}

def classify(title,summary='',keywords=None):
    content = normalize(title+' '+(summary or ''))
    category = next((cat for cat,words in CATEGORY_RULES.items() if any(w in content for w in words)),'Outros')
    matches = [k for k in (keywords or []) if normalize(k) in content]
    relevance = min(100,(60 if category!='Outros' else 20)+len(matches)*10)
    return category,relevance,matches

def news_dict(db,item):
    data = serialize(item)
    competitors = db.scalars(select(Competitor).join(NewsCompetitor,NewsCompetitor.competitor_id==Competitor.id).where(NewsCompetitor.news_id==item.id)).all()
    data['competitors']=[{'id':c.id,'name':c.name} for c in competitors]
    influencers = db.scalars(select(Influencer).join(NewsInfluencer,NewsInfluencer.influencer_id==Influencer.id).where(NewsInfluencer.news_id==item.id)).all()
    data['influencers']=[{'id':i.id,'name':i.name,'stage':i.stage} for i in influencers]
    return data

def ingest_news(db, record, competitor=None):
    url = canonical_url(record['url'])
    item = db.scalar(select(News).where(News.url==url))
    if not item:
        # Limit similarity comparisons by source and recent ingestion; unrelated publishers are not merged.
        candidates = db.scalars(select(News).where(News.source==record['source'],News.created_at>=now()-timedelta(days=30)).limit(500)).all()
        item = next((n for n in candidates if SequenceMatcher(None,normalize(n.title),normalize(record['title'])).ratio()>=0.94),None)
    fresh = item is None
    if fresh:
        category,relevance,keywords = classify(record['title'],record.get('summary'),competitor.keywords if competitor else [])
        item=News(**record,category=category,relevance=relevance,keywords=keywords,evidence=[record['url']])
        item.url=url
        db.add(item)
        db.flush()
        alert_config=db.scalar(select(ProviderConfig).where(ProviderConfig.name=='alerts'))
        config=alert_config.config if alert_config else {}
        if config.get('enabled',True) and (relevance>=config.get('threshold',70) or category in config.get('categories',['Lançamento de produto','Nova funcionalidade','Parceria','Alteração comercial'])):
            db.add(Alert(news_id=item.id,title=item.title,kind=category))
    if competitor and not db.scalar(select(NewsCompetitor).where(NewsCompetitor.news_id==item.id,NewsCompetitor.competitor_id==competitor.id)):
        db.add(NewsCompetitor(news_id=item.id,competitor_id=competitor.id))
    return item,fresh

def quota(db,provider,limit):
    start=now().replace(hour=0,minute=0,second=0,microsecond=0)
    count=db.scalar(select(func.count()).select_from(CollectionRun).where(CollectionRun.provider==provider,CollectionRun.created_at>=start))
    if count>=limit:
        raise HTTPException(429,'Quota diária atingida')
    recent=db.scalar(select(CollectionRun).where(CollectionRun.provider==provider,CollectionRun.created_at>=now()-timedelta(minutes=5)).order_by(CollectionRun.id.desc()))
    if recent:
        raise HTTPException(429,'Cache/intervalo de coleta: aguarde cinco minutos')

def monitor_page(db,source):
    if not source.access_confirmed:
        raise SourceError('Confirme permissão e termos da fonte antes de monitorar páginas')
    p=urlsplit(source.url)
    robots_url=urlunsplit((p.scheme,p.netloc,'/robots.txt','',''))
    # Fail closed on unavailable robots; the operator can use RSS instead.
    content,_=fetch_public(robots_url,allowed_origin=p.netloc)
    robots=RobotFileParser()
    robots.parse(content.decode('utf-8',errors='replace').splitlines())
    if not robots.can_fetch('PapaiaMisc',source.url):
        raise SourceError('robots.txt não permite acesso a esta página')
    delay=robots.crawl_delay('PapaiaMisc') or 0
    if delay>0:
        import time
        time.sleep(min(delay,30))
        if delay>30:
            raise SourceError('Crawl delay da fonte excede o limite do coletor')
    raw,final=fetch_public(source.url,allowed_origin=p.netloc)
    if urlsplit(final).netloc!=p.netloc:
        raise SourceError('Redirecionamento entre domínios requer recadastro da fonte')
    soup=BeautifulSoup(raw,'html.parser')
    for element in soup(['script','style','noscript','nav','footer']):
        element.decompose()
    content=soup.get_text('\n',strip=True)[:100000]
    digest=sha256(content.encode()).hexdigest()
    previous=db.scalar(select(MonitoringSnapshot).where(MonitoringSnapshot.source_id==source.id).order_by(MonitoringSnapshot.id.desc()))
    if previous and previous.content_hash==digest:
        return 0
    diff='\n'.join(unified_diff(previous.content.splitlines(),content.splitlines(),fromfile='anterior',tofile='atual'))[:50000] if previous else None
    db.add(MonitoringSnapshot(source_id=source.id,content=content,content_hash=digest,diff=diff))
    if previous:
        db.add(Alert(title=f'Mudança detectada: {source.url}',kind='Mudança de página'))
    return 1

def collect_sources(db,kind='rss'):
    run=CollectionRun(provider=kind,status='running')
    db.add(run)
    db.commit()
    errors=[]
    sources=db.scalars(select(CompetitorSource).where(CompetitorSource.kind==kind,CompetitorSource.enabled.is_(True))).all()
    for source in sources:
        try:
            with db.begin_nested():
                competitor=db.get(Competitor,source.competitor_id)
                imported=0
                if kind=='rss':
                    for record in RSSProvider().collect(source.url):
                        _,fresh=ingest_news(db,record,competitor)
                        imported+=int(fresh)
                else:
                    imported=monitor_page(db,source)
                source.last_collected_at=now()
            run.imported+=imported
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception('source_collection_failed')
            reason=str(exc) if isinstance(exc,(SourceError,ValueError)) else 'Falha interna ao processar fonte; consulte logs'
            errors.append(f'Fonte {source.id}: {reason}')
        db.commit()
    run.status='partial' if errors and run.imported else ('failed' if errors else 'success')
    run.error='; '.join(errors) or None
    run.finished_at=now()
    db.commit()
    return serialize(run)
