from contextlib import asynccontextmanager
from datetime import timedelta
from collections import Counter
import csv
import io
import json
import logging
import time
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, or_, delete
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from .config import settings
from .db import get_db, SessionLocal
from .models import *
from .schemas import *
from .security import bootstrap,current_user,verify_password,token_for,hash_password
from .services import *
from .providers import PROVIDERS
from .scoring import calculate,NICHES,normalize
from .scheduler import start_scheduler

from .logging_config import configure_logging
configure_logging()
log=logging.getLogger('papaia')

@asynccontextmanager
async def lifespan(app):
    with SessionLocal() as db:
        bootstrap(db)
        for key in ('rss','page'):
            if not db.scalar(select(MonitoringJob).where(MonitoringJob.key==key)):
                db.add(MonitoringJob(key=key))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    scheduler=start_scheduler() if settings().scheduler_enabled else None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)

app=FastAPI(title='Papaia Misc — Marketing & Market Intelligence',version='0.1.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[settings().allowed_origin],allow_credentials=True,allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Content-Type','Authorization'])

@app.middleware('http')
async def request_log(request,call_next):
    started=time.monotonic()
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    log.info(json.dumps({'event':'request','method':request.method,'path':request.url.path,'status':response.status_code,'duration_ms':round((time.monotonic()-started)*1000)}))
    return response

@app.exception_handler(HTTPException)
async def http_error(request,exc):
    return JSONResponse(status_code=exc.status_code,content={'error':{'code':exc.status_code,'message':exc.detail}})

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return JSONResponse(status_code=422,content={'error':{'code':422,'message':'Dados inválidos','details':jsonable_encoder(exc.errors(),custom_encoder={ValueError:str})}})

@app.exception_handler(IntegrityError)
async def integrity_error(request,exc):
    return JSONResponse(status_code=409,content={'error':{'code':409,'message':'Registro duplicado ou referência inválida'}})

@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    log.exception('unexpected_error')
    return JSONResponse(status_code=500,content={'error':{'code':500,'message':'Erro interno. Consulte os logs do servidor.'}})

@app.get('/health')
def health(db=Depends(get_db)):
    db.execute(select(1))
    return {'status':'ok'}

@app.post('/api/auth/login')
def login(payload:Login,request:Request,response:Response,db=Depends(get_db)):
    # Persisted global failure counter works across workers and restarts. No passwords in audit.
    failures=db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='login_failed',AuditLog.created_at>=now()-timedelta(minutes=5)))
    if failures>=20:
        raise HTTPException(429,'Muitas tentativas. Aguarde cinco minutos.')
    user=db.scalar(select(User).where(User.email==payload.email))
    valid=verify_password(payload.password,user.password_hash) if user else verify_password(payload.password,hash_password('invalid-password'))
    if not user or not valid:
        db.add(AuditLog(action='login_failed',entity='auth'))
        db.commit()
        raise HTTPException(401,'E-mail ou senha inválidos')
    response.set_cookie('papaia_session',token_for(user),httponly=True,secure=settings().cookie_secure,samesite='strict',max_age=28800,path='/')
    return {'id':user.id,'name':user.name,'email':user.email}

@app.post('/api/auth/logout')
def logout(response:Response,user=Depends(current_user)):
    response.delete_cookie('papaia_session',path='/')
    return {'ok':True}

@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    return {'id':user.id,'name':user.name,'email':user.email}

@app.get('/api/dashboard')
def dashboard(db=Depends(get_db),user=Depends(current_user)):
    stages=dict(db.execute(select(Influencer.stage,func.count()).group_by(Influencer.stage)).all())
    total=sum(stages.values())
    count=lambda model,*where:db.scalar(select(func.count()).select_from(model).where(*where))
    seven=now()-timedelta(days=7)
    news_count=count(News,News.created_at>=seven)
    closed=stages.get('Parceria fechada',0)+stages.get('Parceria concluída',0)
    return {'total_leads':total,'new_leads':count(Influencer,Influencer.created_at>=seven),'qualified':stages.get('Qualificado',0),'contacted':sum(stages.get(s,0) for s in STAGES[4:9]),'negotiating':stages.get('Em negociação',0),'closed':closed,'conversion':round(closed/total*100,1) if total else 0,'competitors':count(Competitor),'news_7d':news_count,'alerts':count(Alert,Alert.read.is_(False)),'launches':count(News,News.category=='Lançamento de produto',News.created_at>=seven),'partnerships':count(News,News.category=='Parceria',News.created_at>=seven),'pipeline':[{'name':s,'value':stages.get(s,0)} for s in STAGES],'news_categories':[{'name':k,'value':v} for k,v in db.execute(select(News.category,func.count()).where(News.created_at>=seven).group_by(News.category))],'recent_activity':[serialize(a) for a in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(8))],'priority_alerts':[serialize(a) for a in db.scalars(select(Alert).where(Alert.read.is_(False)).order_by(Alert.id.desc()).limit(5))]}

@app.get('/api/influencers')
def influencers(q:str='',stage:Stage|None=None,platform:Platform|None=None,niche:str='',region:str='',language:str='',target_audience:str='',professional_category:str='',min_followers:int|None=Query(None,ge=0),max_followers:int|None=Query(None,ge=0),min_engagement:float|None=Query(None,ge=0,le=100),min_score:float|None=Query(None,ge=0,le=100),sort:Literal['newest','name','score']='newest',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db=Depends(get_db),user=Depends(current_user)):
    stmt=select(Influencer)
    if q:
        stmt=stmt.where(or_(Influencer.name.ilike(f'%{q}%'),Influencer.id.in_(select(InfluencerProfile.influencer_id).where(InfluencerProfile.username.ilike(f'%{q}%')))))
    if stage:
        stmt=stmt.where(Influencer.stage==stage)
    for field,value in ((Influencer.region,region),(Influencer.language,language),(Influencer.target_audience,target_audience),(Influencer.professional_category,professional_category)):
        if value:
            stmt=stmt.where(field.ilike(f'%{value}%'))
    latest_metric=select(func.max(InfluencerMetric.id)).where(InfluencerMetric.profile_id==InfluencerProfile.id).correlate(InfluencerProfile).scalar_subquery()
    if platform or min_followers is not None or max_followers is not None or min_engagement is not None:
        profiles=select(InfluencerProfile.influencer_id).outerjoin(InfluencerMetric,InfluencerMetric.id==latest_metric)
        if platform:
            profiles=profiles.where(InfluencerProfile.platform==platform)
        if min_followers is not None:
            profiles=profiles.where(InfluencerMetric.followers>=min_followers)
        if max_followers is not None:
            profiles=profiles.where(InfluencerMetric.followers<=max_followers)
        if min_engagement is not None:
            profiles=profiles.where(InfluencerMetric.engagement>=min_engagement)
        stmt=stmt.where(Influencer.id.in_(profiles))
    if niche:
        # JSON array text portable between PostgreSQL and SQLite.
        from sqlalchemy import cast,String
        stmt=stmt.where(cast(Influencer.niches,String).ilike(f'%{niche}%'))
    latest_score=select(InfluencerScore.value).where(InfluencerScore.influencer_id==Influencer.id).order_by(InfluencerScore.id.desc()).limit(1).correlate(Influencer).scalar_subquery()
    if min_score is not None:
        stmt=stmt.where(latest_score>=min_score)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    ordering=Influencer.name.asc() if sort=='name' else latest_score.desc().nullslast() if sort=='score' else Influencer.id.desc()
    rows=db.scalars(stmt.order_by(ordering,Influencer.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[influencer_dict(db,i) for i in rows],'total':total,'page':page,'page_size':page_size}

@app.post('/api/influencers',status_code=201)
def create_influencer(payload:InfluencerCreate,db=Depends(get_db),user=Depends(current_user)):
    inf,_=insert_influencer(db,payload)
    audit(db,user,'created','influencer',inf.id)
    db.commit()
    return influencer_dict(db,inf)

@app.post('/api/influencers/import')
def import_csv(file:UploadFile=File(...),db=Depends(get_db),user=Depends(current_user)):
    content=file.file.read(2_000_001)
    if len(content)>2_000_000:
        raise HTTPException(413,'CSV excede 2 MB')
    try:
        reader=csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        rows=[]
        for index,row in enumerate(reader,2):
            if len(rows)>=1000:
                raise ValueError('Limite de 1000 linhas')
            data={k:v for k,v in row.items() if v is not None and v!=''}
            if 'niches' in data:
                data['niches']=[v.strip() for v in data['niches'].split('|') if v.strip()]
            for key in ('evidence_urls','relevant_posts','previous_collaborations'):
                if key in data:
                    data[key]=data[key].split('|')
            for key in ('audience_countries','audience_demographics'):
                if key in data:
                    data[key]=json.loads(data[key])
            rows.append(InfluencerCreate.model_validate(data))
    except (ValueError,UnicodeError,csv.Error,TypeError) as exc:
        raise HTTPException(422,f'CSV inválido na linha {locals().get("index",1)}: {str(exc)[:600]}')
    imported=0
    for row in rows:
        _,fresh=insert_influencer(db,row,provider='csv',upsert=True)
        imported+=int(fresh)
    audit(db,user,'csv_import','influencer')
    db.commit()
    return {'imported':imported,'updated':len(rows)-imported}

@app.post('/api/influencers/discover')
def discover(payload:Discover,db=Depends(get_db),user=Depends(current_user)):
    # Natural language inference is deliberately restricted to known topics and explicit fields.
    inferred=[n for n in NICHES if normalize(n) in normalize(payload.query)]
    if not payload.confirm:
        return {'status':'confirmation_required','message':'A busca consulta um dataset Apify existente (até 100 perfis). Revise e confirme a importação. Não executa Actors pagos.','inferred_niches':inferred,'query':payload.query}
    with collection_lock():
        quota(db,'apify',settings().provider_daily_limit)
        run=CollectionRun(provider='apify',status='running')
        db.add(run)
        db.commit()
        try:
            records=PROVIDERS['apify'].discover()
            selected=[]
            for row in records:
                text=normalize(' '.join(row.niches)+' '+(row.biography or ''))
                if inferred and not any(normalize(n) in text for n in inferred): continue
                if payload.niche and normalize(payload.niche) not in text: continue
                if payload.platform and row.platform!=payload.platform: continue
                if payload.min_followers is not None and (row.followers is None or row.followers<payload.min_followers): continue
                if payload.max_followers is not None and (row.followers is None or row.followers>payload.max_followers): continue
                if payload.min_engagement is not None and (row.engagement is None or row.engagement<payload.min_engagement): continue
                if any(value and normalize(value) not in normalize(getattr(row,key) or '') for key,value in [('region',payload.region),('language',payload.language),('target_audience',payload.target_audience),('professional_category',payload.professional_category)]): continue
                if payload.min_score is not None:
                    from types import SimpleNamespace
                    if calculate(row,SimpleNamespace(biography=row.biography,evidence_urls=row.evidence_urls,url=row.url),row)['value']<payload.min_score: continue
                selected.append(row)
            with db.begin_nested():
                for row in selected:
                    _,fresh=insert_influencer(db,row,provider='apify',upsert=True)
                    run.imported+=int(fresh)
            run.status='success'
            audit(db,user,'discovered','influencer')
        except Exception as exc:
            run.status='failed'
            run.error=str(exc)[:1000] if isinstance(exc,(SourceError,ValueError)) else 'Falha no provedor externo'
            run.imported=0
        run.finished_at=now()
        db.commit()
        return serialize(run)

@app.get('/api/influencers/{ident}')
def influencer_detail(ident:int,db=Depends(get_db),user=Depends(current_user)):
    return influencer_dict(db,get_or_404(db,Influencer,ident),True)

@app.patch('/api/influencers/{ident}')
def update_influencer(ident:int,payload:InfluencerPatch,db=Depends(get_db),user=Depends(current_user)):
    inf=get_or_404(db,Influencer,ident)
    old=inf.stage
    for k,v in payload.model_dump(exclude_unset=True).items():
        setattr(inf,k,v)
    audit(db,user,f'stage:{old} → {inf.stage}' if old!=inf.stage else 'updated','influencer',ident)
    db.commit()
    return influencer_dict(db,inf,True)

@app.delete('/api/influencers/{ident}',status_code=204)
def delete_influencer(ident:int,db=Depends(get_db),user=Depends(current_user)):
    db.delete(get_or_404(db,Influencer,ident))
    audit(db,user,'deleted','influencer',ident)
    db.commit()

@app.patch('/api/profiles/{ident}')
def update_profile(ident:int,payload:InfluencerCreate,db=Depends(get_db),user=Depends(current_user)):
    profile=get_or_404(db,InfluencerProfile,ident)
    inf=get_or_404(db,Influencer,profile.influencer_id)
    for key in ('name','professional_category','niches','region','language','target_audience'):
        setattr(inf,key,getattr(payload,key))
    for key in ('platform','username','url','photo_url','biography','public_contact','evidence_urls','relevant_posts','previous_collaborations'):
        setattr(profile,key,getattr(payload,key))
    profile.provider='manual'
    profile.updated_at=now()
    db.add(InfluencerMetric(profile_id=ident,**{k:getattr(payload,k) for k in METRIC_FIELDS}))
    audit(db,user,'profile_updated','influencer',inf.id)
    db.commit()
    return influencer_dict(db,inf,True)

@app.post('/api/influencers/{ident}/profiles',status_code=201)
def add_profile(ident:int,payload:InfluencerCreate,db=Depends(get_db),user=Depends(current_user)):
    inf=get_or_404(db,Influencer,ident)
    profile=InfluencerProfile(influencer_id=ident,provider='manual',**{k:getattr(payload,k) for k in ('platform','username','url','photo_url','biography','public_contact','evidence_urls','relevant_posts','previous_collaborations')})
    db.add(profile)
    db.flush()
    db.add(InfluencerMetric(profile_id=profile.id,**{k:getattr(payload,k) for k in METRIC_FIELDS}))
    audit(db,user,'profile_linked_manually','influencer',ident)
    db.commit()
    return influencer_dict(db,inf,True)

@app.post('/api/influencers/{ident}/score')
def score_influencer(ident:int,payload:ScoreRequest,db=Depends(get_db),user=Depends(current_user)):
    inf=get_or_404(db,Influencer,ident)
    profile=db.scalar(select(InfluencerProfile).where(InfluencerProfile.influencer_id==ident))
    metrics=db.scalar(select(InfluencerMetric).where(InfluencerMetric.profile_id==profile.id).order_by(InfluencerMetric.id.desc()))
    result=calculate(inf,profile,metrics,payload.campaign_type,payload.weights)
    evidence=result.pop('evidence')
    if payload.manual_value is not None:
        result['value']=payload.manual_value
        result['confidence']=100
        result['explanation']='Avaliação humana: '+payload.rationale+'. Confiança representa cobertura da revisão, não verificação profissional.'
        evidence=[{'criterion':'manual','points':payload.manual_value,'available':True,'explanation':payload.rationale,'urls':payload.evidence_urls}]
    score=InfluencerScore(influencer_id=ident,campaign_type=payload.campaign_type,manual=payload.manual_value is not None,**result)
    db.add(score)
    db.flush()
    for e in evidence:
        db.add(ScoreEvidence(score_id=score.id,**e))
    audit(db,user,'scored','influencer',ident)
    db.commit()
    return influencer_dict(db,inf,True)

@app.post('/api/influencers/{ident}/contacts',status_code=201)
def create_contact(ident:int,payload:ContactCreate,db=Depends(get_db),user=Depends(current_user)):
    get_or_404(db,Influencer,ident)
    contact=ContactInteraction(influencer_id=ident,**payload.model_dump(exclude_none=True))
    db.add(contact)
    audit(db,user,'contact_logged','influencer',ident)
    db.commit()
    return serialize(contact)

@app.post('/api/influencers/{ident}/proposal')
def proposal(ident:int,campaign_type:Literal['B2B','B2C']='B2B',db=Depends(get_db),user=Depends(current_user)):
    inf=get_or_404(db,Influencer,ident)
    niche=', '.join(inf.niches[:2]) or 'seu conteúdo'
    objective='apresentar nosso software para profissionais de nutrição' if campaign_type=='B2B' else 'compartilhar conteúdo útil com famílias e responsáveis'
    return {'draft':f'Olá, {inf.name}! Somos da equipe Papaia, software de nutrição com foco materno-infantil. Gostaríamos de conhecer melhor seu trabalho sobre {niche} e conversar sobre uma possível parceria para {objective}. Você teria interesse em receber uma proposta? Podemos alinhar objetivos, entregáveis e condições em conjunto. Obrigado!','requires_review':True,'sent':False}

@app.get('/api/campaigns')
def campaigns(page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),db=Depends(get_db),user=Depends(current_user)):
    return paged(db,select(Campaign).order_by(Campaign.id.desc()),page,page_size)

@app.post('/api/campaigns',status_code=201)
def create_campaign(payload:CampaignCreate,db=Depends(get_db),user=Depends(current_user)):
    obj=Campaign(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit(db,user,'created','campaign',obj.id)
    db.commit()
    return serialize(obj)

@app.get('/api/negotiations')
def negotiations(influencer_id:int|None=None,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),db=Depends(get_db),user=Depends(current_user)):
    stmt=select(Negotiation).order_by(Negotiation.id.desc())
    if influencer_id:
        stmt=stmt.where(Negotiation.influencer_id==influencer_id)
    return paged(db,stmt,page,page_size)

def associate_campaign(db,inf_id,campaign_id):
    if campaign_id:
        get_or_404(db,Campaign,campaign_id)
        if not db.scalar(select(CampaignInfluencer).where(CampaignInfluencer.campaign_id==campaign_id,CampaignInfluencer.influencer_id==inf_id)):
            db.add(CampaignInfluencer(campaign_id=campaign_id,influencer_id=inf_id))

@app.post('/api/negotiations',status_code=201)
def create_negotiation(payload:NegotiationCreate,db=Depends(get_db),user=Depends(current_user)):
    get_or_404(db,Influencer,payload.influencer_id)
    associate_campaign(db,payload.influencer_id,payload.campaign_id)
    obj=Negotiation(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit(db,user,'created','negotiation',obj.id)
    db.commit()
    return serialize(obj)

@app.patch('/api/negotiations/{ident}')
def update_negotiation(ident:int,payload:NegotiationPatch,db=Depends(get_db),user=Depends(current_user)):
    obj=get_or_404(db,Negotiation,ident)
    associate_campaign(db,obj.influencer_id,payload.campaign_id)
    for k,v in payload.model_dump(exclude_unset=True).items(): setattr(obj,k,v)
    audit(db,user,'updated','negotiation',ident)
    db.commit()
    return serialize(obj)

@app.delete('/api/negotiations/{ident}',status_code=204)
def delete_negotiation(ident:int,db=Depends(get_db),user=Depends(current_user)):
    db.delete(get_or_404(db,Negotiation,ident))
    audit(db,user,'deleted','negotiation',ident)
    db.commit()

def paged(db,stmt,page,page_size,formatter=serialize):
    total=db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return {'items':[formatter(r) for r in db.scalars(stmt.offset((page-1)*page_size).limit(page_size))],'total':total,'page':page,'page_size':page_size}

def competitor_dict(db,c):
    return {**serialize(c),'sources':[serialize(s) for s in db.scalars(select(CompetitorSource).where(CompetitorSource.competitor_id==c.id))]}

@app.get('/api/competitors')
def competitors(q:str='',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db=Depends(get_db),user=Depends(current_user)):
    stmt=select(Competitor).where(Competitor.name.ilike(f'%{q}%')).order_by(Competitor.name)
    return paged(db,stmt,page,page_size,lambda c:competitor_dict(db,c))

@app.get('/api/competitors/{ident}')
def competitor_detail(ident:int,db=Depends(get_db),user=Depends(current_user)):
    return competitor_dict(db,get_or_404(db,Competitor,ident))

@app.post('/api/competitors',status_code=201)
def create_competitor(payload:CompetitorCreate,db=Depends(get_db),user=Depends(current_user)):
    obj=Competitor(**payload.model_dump(exclude={'sources'}))
    db.add(obj)
    db.flush()
    for s in payload.sources:
        db.add(CompetitorSource(competitor_id=obj.id,**s.model_dump()))
    audit(db,user,'created','competitor',obj.id)
    db.commit()
    return competitor_dict(db,obj)

@app.patch('/api/competitors/{ident}')
def update_competitor(ident:int,payload:CompetitorPatch,db=Depends(get_db),user=Depends(current_user)):
    obj=get_or_404(db,Competitor,ident)
    for k,v in payload.model_dump(exclude_unset=True).items(): setattr(obj,k,v)
    audit(db,user,'updated','competitor',ident)
    db.commit()
    return competitor_dict(db,obj)

@app.delete('/api/competitors/{ident}',status_code=204)
def delete_competitor(ident:int,db=Depends(get_db),user=Depends(current_user)):
    db.delete(get_or_404(db,Competitor,ident))
    audit(db,user,'deleted','competitor',ident)
    db.commit()

@app.post('/api/competitors/{ident}/sources',status_code=201)
def add_source(ident:int,payload:SourceCreate,db=Depends(get_db),user=Depends(current_user)):
    get_or_404(db,Competitor,ident)
    obj=CompetitorSource(competitor_id=ident,**payload.model_dump())
    db.add(obj)
    audit(db,user,'source_added','competitor',ident)
    db.commit()
    return serialize(obj)

@app.delete('/api/sources/{ident}',status_code=204)
def delete_source(ident:int,db=Depends(get_db),user=Depends(current_user)):
    db.delete(get_or_404(db,CompetitorSource,ident))
    audit(db,user,'deleted','source',ident)
    db.commit()

@app.get('/api/sources/{ident}/snapshots')
def snapshots(ident:int,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50),db=Depends(get_db),user=Depends(current_user)):
    get_or_404(db,CompetitorSource,ident)
    return paged(db,select(MonitoringSnapshot).where(MonitoringSnapshot.source_id==ident).order_by(MonitoringSnapshot.id.desc()),page,page_size)

@app.get('/api/news')
def news(q:str='',category:str|None=None,competitor_id:int|None=None,watched:bool|None=None,read:bool|None=None,min_relevance:int=Query(0,ge=0,le=100),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db=Depends(get_db),user=Depends(current_user)):
    stmt=select(News).where(News.relevance>=min_relevance).order_by(News.created_at.desc(),News.id.desc())
    if q: stmt=stmt.where(News.title.ilike(f'%{q}%'))
    if category: stmt=stmt.where(News.category==category)
    if watched is not None: stmt=stmt.where(News.watched==watched)
    if read is not None: stmt=stmt.where(News.read==read)
    if competitor_id: stmt=stmt.where(News.id.in_(select(NewsCompetitor.news_id).where(NewsCompetitor.competitor_id==competitor_id)))
    return paged(db,stmt,page,page_size,lambda n:news_dict(db,n))

@app.post('/api/news',status_code=201)
def manual_news(payload:ManualNews,db=Depends(get_db),user=Depends(current_user)):
    competitor=get_or_404(db,Competitor,payload.competitor_id) if payload.competitor_id else None
    obj,fresh=ingest_news(db,payload.model_dump(exclude={'competitor_id'}),competitor)
    audit(db,user,'manual_news','news',obj.id)
    db.commit()
    return news_dict(db,obj)

@app.post('/api/news/collect')
def collect_news(db=Depends(get_db),user=Depends(current_user)):
    with collection_lock():
        quota(db,'rss',settings().provider_daily_limit)
        result=collect_sources(db)
        audit(db,user,'collected','news')
        db.commit()
        return result

@app.post('/api/monitoring/collect')
def collect_pages(db=Depends(get_db),user=Depends(current_user)):
    with collection_lock():
        quota(db,'page',settings().provider_daily_limit)
        return collect_sources(db,'page')

@app.get('/api/news/{ident}')
def news_detail(ident:int,db=Depends(get_db),user=Depends(current_user)):
    return news_dict(db,get_or_404(db,News,ident))

@app.patch('/api/news/{ident}')
def update_news(ident:int,payload:NewsPatch,db=Depends(get_db),user=Depends(current_user)):
    obj=get_or_404(db,News,ident)
    for k,v in payload.model_dump(exclude_unset=True).items(): setattr(obj,k,v)
    db.commit()
    return news_dict(db,obj)

@app.delete('/api/news/{ident}',status_code=204)
def delete_news(ident:int,db=Depends(get_db),user=Depends(current_user)):
    db.delete(get_or_404(db,News,ident))
    audit(db,user,'deleted','news',ident)
    db.commit()

@app.post('/api/news/{ident}/analyze')
def analyze_news(ident:int,db=Depends(get_db),user=Depends(current_user)):
    obj=get_or_404(db,News,ident)
    competitors=news_dict(db,obj)['competitors']
    obj.analysis={'facts':{'what_happened':obj.title,'source':obj.url,'competitors':[c['name'] for c in competitors],'caveat':'Conteúdo atribuído à fonte, sem verificação independente.'},'interpretation':{'why_relevant':f'Sinal classificado por regras como {obj.category}; relevância {obj.relevance}/100.','possible_impact':'Pode influenciar expectativas de clientes e posicionamento. Impacto ainda não validado.','opportunity_or_threat':'Hipótese de oportunidade a investigar; não constitui evidência de ameaça.','suggested_action':'Revisar a fonte, comparar com o roadmap Papaia e validar com a equipe comercial.'},'method':'Regras, sem LLM'}
    audit(db,user,'analyzed','news',ident)
    db.commit()
    return news_dict(db,obj)

@app.post('/api/news/{ident}/influencers',status_code=201)
def link_news(ident:int,payload:LinkInfluencer,db=Depends(get_db),user=Depends(current_user)):
    get_or_404(db,News,ident)
    get_or_404(db,Influencer,payload.influencer_id)
    if not payload.confirmed: raise HTTPException(422,'Confirme a evidência antes de vincular')
    db.add(NewsInfluencer(news_id=ident,influencer_id=payload.influencer_id,confirmed_by=user.id))
    audit(db,user,'link_confirmed','news',ident)
    db.commit()
    return news_dict(db,db.get(News,ident))

@app.get('/api/alerts')
def alerts(read:bool|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db=Depends(get_db),user=Depends(current_user)):
    stmt=select(Alert).order_by(Alert.id.desc())
    if read is not None: stmt=stmt.where(Alert.read==read)
    return paged(db,stmt,page,page_size)

@app.patch('/api/alerts/{ident}')
def update_alert(ident:int,payload:AlertPatch,db=Depends(get_db),user=Depends(current_user)):
    obj=get_or_404(db,Alert,ident)
    obj.read=payload.read
    db.commit()
    return serialize(obj)

@app.get('/api/integrations/status')
def integrations(db=Depends(get_db),user=Depends(current_user)):
    cfg=settings()
    return {'providers':[{'name':'Cadastro manual','status':'ready'},{'name':'CSV','status':'ready'},{'name':'RSS / Google Alerts RSS','status':'ready'},{'name':'Apify dataset','status':'ready' if cfg.apify_token and cfg.apify_dataset_id else 'pending','detail':'Importação de dataset existente; não executa Actors pagos'},{'name':'Modash','status':'not_implemented'},{'name':'HypeAuditor','status':'not_implemented'},{'name':'YouTube Data API','status':'not_implemented'}],'scheduler_enabled':cfg.scheduler_enabled,'schedule_hour_utc':cfg.schedule_hour,'daily_limit':cfg.provider_daily_limit,'demo_enabled':cfg.demo_enabled,'paid_actor_execution':False,'ai_classification':'disabled','jobs':[serialize(j) for j in db.scalars(select(MonitoringJob))]}

@app.get('/api/collection-runs')
def runs(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db=Depends(get_db),user=Depends(current_user)):
    return paged(db,select(CollectionRun).order_by(CollectionRun.id.desc()),page,page_size)

@app.patch('/api/monitoring/jobs/{ident}')
def update_job(ident:int,payload:JobPatch,db=Depends(get_db),user=Depends(current_user)):
    obj=get_or_404(db,MonitoringJob,ident)
    obj.enabled=payload.enabled
    obj.interval_hours=payload.interval_hours
    audit(db,user,'updated','monitoring_job',ident)
    db.commit()
    return serialize(obj)

@app.get('/api/alert-config')
def alert_settings(db=Depends(get_db),user=Depends(current_user)):
    obj=db.scalar(select(ProviderConfig).where(ProviderConfig.name=='alerts'))
    return obj.config if obj else AlertConfig().model_dump()

@app.patch('/api/alert-config')
def update_alert_settings(payload:AlertConfig,db=Depends(get_db),user=Depends(current_user)):
    obj=db.scalar(select(ProviderConfig).where(ProviderConfig.name=='alerts'))
    if not obj:
        obj=ProviderConfig(name='alerts')
        db.add(obj)
    obj.config=payload.model_dump()
    audit(db,user,'updated','alert_config')
    db.commit()
    return obj.config


from .customer_api import router as customer_router
app.include_router(customer_router)
