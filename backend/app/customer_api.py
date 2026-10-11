"""Free local prospecting: manual research, CRM, imports and spreadsheet export."""
import csv
import io
import re
from typing import Literal
from urllib.parse import urlencode
from fastapi import APIRouter,Depends,Query,UploadFile,File,HTTPException,Response
from pydantic import ValidationError
from sqlalchemy import select,func,or_,cast,String
from .db import get_db
from .models import CustomerLead,Influencer,InfluencerProfile
from .schemas import CustomerLeadCreate,CustomerLeadPatch,CustomerStage,CustomerSearchRequest,CUSTOMER_STAGES
from .security import current_user
from .services import get_or_404,serialize,audit
from .scoring import NICHES,normalize
from .customer_scoring import refresh_customer_score

router=APIRouter(prefix='/api/customer-leads',tags=['Potenciais clientes'])

def customer_query(q='',stage=None,region='',niche='',min_score=0):
    stmt=select(CustomerLead).where(CustomerLead.score>=min_score)
    if q:
        stmt=stmt.where(or_(*(field.ilike(f'%{q}%') for field in (CustomerLead.name,CustomerLead.username,CustomerLead.professional_category,CustomerLead.biography))))
    if stage: stmt=stmt.where(CustomerLead.stage==stage)
    if region: stmt=stmt.where(CustomerLead.region.ilike(f'%{region}%'))
    if niche: stmt=stmt.where(cast(CustomerLead.niches,String).ilike(f'%{niche}%'))
    return stmt


def insert_customer(db,payload,provider='manual'):
    if db.scalar(select(CustomerLead.id).where(CustomerLead.platform==payload.platform,CustomerLead.username==payload.username)):
        raise HTTPException(409,'Este perfil já está cadastrado como potencial cliente')
    lead=CustomerLead(**payload.model_dump(),provider=provider)
    refresh_customer_score(lead)
    db.add(lead)
    db.flush()
    return lead


@router.get('')
def list_customers(q:str='',stage:CustomerStage|None=None,region:str='',niche:str='',min_score:float=Query(0,ge=0,le=100),sort:Literal['score','newest','name']='score',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db=Depends(get_db),user=Depends(current_user)):
    stmt=customer_query(q,stage,region,niche,min_score)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    order={'score':CustomerLead.score.desc(),'newest':CustomerLead.id.desc(),'name':CustomerLead.name.asc()}[sort]
    rows=db.scalars(stmt.order_by(order,CustomerLead.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[serialize(r) for r in rows],'total':total,'page':page,'page_size':page_size}


@router.get('/summary')
def customer_summary(db=Depends(get_db),user=Depends(current_user)):
    stages=dict(db.execute(select(CustomerLead.stage,func.count()).group_by(CustomerLead.stage)).all())
    return {'total':sum(stages.values()),'qualified':stages.get('Qualificado',0),'trial':stages.get('Em teste',0),'subscribers':stages.get('Assinante',0),'pipeline':[{'name':stage,'value':stages.get(stage,0)} for stage in CUSTOMER_STAGES]}


@router.post('',status_code=201)
def create_customer(payload:CustomerLeadCreate,db=Depends(get_db),user=Depends(current_user)):
    lead=insert_customer(db,payload)
    audit(db,user,'created','customer_lead',lead.id)
    db.commit()
    return serialize(lead)


@router.post('/search-plan')
def customer_search_plan(payload:CustomerSearchRequest,db=Depends(get_db),user=Depends(current_user)):
    """Public search links, not scraped results. No API/model is invoked."""
    text=normalize(payload.query)
    topics=[n for n in NICHES if normalize(n) in text]
    handles=re.findall(r'@([A-Za-z0-9_.]+)',payload.query)
    queries=[f'site:instagram.com "nutricionista" "{topic}"' for topic in topics[:3]]
    if not queries: queries=['site:instagram.com nutricionista '+payload.query]
    if handles: queries.insert(0,f'site:instagram.com "nutricionista" "@{handles[0]}"')
    local=select(CustomerLead).where(or_(CustomerLead.professional_category.ilike('%nutricionista%'),CustomerLead.professional_category.ilike('%clínica de nutrição%')))
    rows=[]
    for lead in db.scalars(local.order_by(CustomerLead.score.desc(),CustomerLead.id.desc()).execution_options(yield_per=100)):
        content=normalize(' '.join(lead.niches or [])+' '+(lead.biography or ''))
        if not topics or any(normalize(topic) in content for topic in topics):
            rows.append(lead)
        if len(rows)>=20: break
    return {'mode':'manual_research','cost':0,'message':'Buscas públicas para revisão manual. Não extraímos seguidores de um @ nem consultamos provedores pagos. Os perfis abaixo já pertencem à sua base. Localização e demais requisitos devem ser conferidos na fonte.','topics':topics,'seed_handles':handles,'searches':[{'query':query,'url':'https://www.google.com/search?'+urlencode({'q':query})} for query in queries],'local_matches':[serialize(r) for r in rows]}


EXPORT_FIELDS=['name','username','platform','url','professional_category','niches','region','public_contact','source_url','evidence_urls','offers_consultations','expressed_interest','stage','owner','follow_up','notes','score','confidence','provider']

def spreadsheet_safe(value):
    text='' if value is None else str(value)
    if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')):
        text="'"+text
    return text


@router.get('/export')
def export_customers(q:str='',stage:CustomerStage|None=None,region:str='',niche:str='',min_score:float=Query(0,ge=0,le=100),db=Depends(get_db),user=Depends(current_user)):
    stmt=customer_query(q,stage,region,niche,min_score).order_by(CustomerLead.score.desc(),CustomerLead.id.desc())
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    if total>10000: raise HTTPException(422,'Restrinja os filtros: limite de 10.000 leads por exportação')
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=EXPORT_FIELDS,quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for lead in db.scalars(stmt):
        data=serialize(lead)
        for key in ('niches','evidence_urls'): data[key]=' | '.join(data[key])
        for key in ('offers_consultations','expressed_interest'): data[key]='' if data[key] is None else str(data[key]).lower()
        writer.writerow({key:spreadsheet_safe(data.get(key)) for key in EXPORT_FIELDS})
    audit(db,user,'exported','customer_lead')
    db.commit()
    return Response(content=('\ufeff'+stream.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="papaia-potenciais-clientes.csv"','Cache-Control':'no-store'})


@router.post('/import')
def import_customers(file:UploadFile=File(...),db=Depends(get_db),user=Depends(current_user)):
    raw=file.file.read(2_000_001)
    if len(raw)>2_000_000: raise HTTPException(413,'CSV excede 2 MB')
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        parsed=[]
        for line,row in enumerate(reader,2):
            if len(parsed)>=1000: raise ValueError('Limite de 1.000 linhas')
            data={k:v for k,v in row.items() if v not in ('',None) and k not in ('score','confidence','provider')}
            for key in ('niches','evidence_urls'):
                if key in data: data[key]=[v.strip() for v in data[key].split('|') if v.strip()]
            parsed.append(CustomerLeadCreate.model_validate(data))
        if not parsed: raise ValueError('Arquivo sem leads')
    except (ValueError,UnicodeError,TypeError,csv.Error) as exc:
        raise HTTPException(422,f'CSV inválido na linha {locals().get("line",1)}: {str(exc)[:500]}')
    added=skipped=0
    for payload in parsed:
        if db.scalar(select(CustomerLead.id).where(CustomerLead.platform==payload.platform,CustomerLead.username==payload.username)):
            skipped+=1
            continue
        lead=insert_customer(db,payload,'csv')
        audit(db,user,'imported','customer_lead',lead.id)
        added+=1
    db.commit()
    return {'imported':added,'skipped':skipped,'message':'Duplicados preservados, sem sobrescrever avaliações ou pipeline.'}


@router.post('/from-influencer/{ident}',status_code=201)
def customer_from_influencer(ident:int,db=Depends(get_db),user=Depends(current_user)):
    inf=get_or_404(db,Influencer,ident)
    profile=db.scalar(select(InfluencerProfile).where(InfluencerProfile.influencer_id==ident).order_by(InfluencerProfile.id))
    if not profile: raise HTTPException(422,'Influenciador sem perfil público')
    payload=CustomerLeadCreate(name=inf.name,platform=profile.platform,username=profile.username,url=profile.url,professional_category=inf.professional_category,biography=profile.biography,niches=inf.niches,region=inf.region,public_contact=profile.public_contact,evidence_urls=profile.evidence_urls)
    lead=insert_customer(db,payload,'existing_profile')
    lead.influencer_id=ident
    audit(db,user,'copied_from_influencer','customer_lead',lead.id)
    db.commit()
    return serialize(lead)


@router.get('/{ident}')
def customer_detail(ident:int,db=Depends(get_db),user=Depends(current_user)):
    return serialize(get_or_404(db,CustomerLead,ident))


@router.patch('/{ident}')
def update_customer(ident:int,payload:CustomerLeadPatch,db=Depends(get_db),user=Depends(current_user)):
    lead=get_or_404(db,CustomerLead,ident)
    changes=payload.model_dump(exclude_unset=True)
    candidate={key:getattr(lead,key) for key in CustomerLeadCreate.model_fields}
    candidate.update(changes)
    try: CustomerLeadCreate.model_validate(candidate)
    except ValidationError: raise HTTPException(422,'Sinais avaliados exigem links públicos de evidência; revise os dados')
    for key,value in changes.items(): setattr(lead,key,value)
    if set(changes)&{'professional_category','biography','niches','url','evidence_urls','offers_consultations','expressed_interest'}:
        refresh_customer_score(lead)
    audit(db,user,'updated','customer_lead',ident)
    db.commit()
    return serialize(lead)


@router.delete('/{ident}',status_code=204)
def delete_customer(ident:int,db=Depends(get_db),user=Depends(current_user)):
    db.delete(get_or_404(db,CustomerLead,ident))
    audit(db,user,'deleted','customer_lead',ident)
    db.commit()
