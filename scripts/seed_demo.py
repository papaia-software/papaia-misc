"""Optional fictional records only; run from backend with DEMO_ENABLED=true."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'backend'))
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import Competitor,Influencer,InfluencerProfile
from app.schemas import InfluencerCreate
from app.services import insert_influencer

if not settings().demo_enabled:
    raise SystemExit('Demo desativada. Defina DEMO_ENABLED=true explicitamente para continuar.')
with SessionLocal() as db:
    if db.scalar(select(InfluencerProfile).where(InfluencerProfile.username=='demo_papaia_ficticio')):
        raise SystemExit('Demo já cadastrada; nenhum registro duplicado.')
    inf,_=insert_influencer(db,InfluencerCreate(name='DEMO · Perfil fictício',username='demo_papaia_ficticio',platform='Instagram',url='https://example.org/demo',biography='Registro fictício para demonstração. Não representa uma pessoa real.',niches=['Introdução alimentar'],target_audience='Famílias (fictício)',professional_category='Criadora fictícia'),provider='demo')
    inf.demo=True
    if not db.scalar(select(Competitor).where(Competitor.name=='DEMO · Empresa fictícia')):
        db.add(Competitor(name='DEMO · Empresa fictícia',website='https://example.org',description='Exemplo fictício, sem relação com concorrentes reais do Papaia.',demo=True))
    db.commit()
print('Demo explicitamente identificada criada. Métricas não foram inventadas. Exclua pela interface quando quiser.')
