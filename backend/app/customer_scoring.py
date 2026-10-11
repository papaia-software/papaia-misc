"""Customer suitability, never an estimate of income or professional registration."""
import re
from .scoring import NICHES,normalize
from .models import now

CUSTOMER_WEIGHTS={'profession':40,'theme':30,'consultations':20,'interest':10}

def calculate_customer(lead):
    profession=normalize(lead.professional_category or '')
    student=bool(re.search(r'\b(estudante|graduand[ao]|academico|academica)\b',profession))
    suitable=bool(re.search(r'\b(nutricionista[s]?|nutritionist[s]?|dietitian[s]?)\b|clinica de nutricao',profession)) and not student
    content=normalize(' '.join(lead.niches or [])+' '+(lead.biography or ''))
    matched=[n for n in NICHES if normalize(n) in content]
    urls=list(lead.evidence_urls or []) or [lead.url]
    assessed=bool(lead.evidence_urls)
    criteria=[
        ('profession',40 if suitable else 0,bool(profession),'Profissão declarada compatível com software de nutrição.' if suitable else 'Profissão compatível não identificada na categoria declarada; revisão necessária.'),
        ('theme',30 if matched else 0,bool(content.strip()),'Temas declarados: '+(', '.join(matched) or 'nenhum tema do catálogo identificado')+'.'),
        ('consultations',20 if lead.offers_consultations is True and assessed else 0,lead.offers_consultations is not None and assessed,'Atendimento profissional avaliado manualmente com evidência pública; desconhecido não recebe pontos.'),
        ('interest',10 if lead.expressed_interest is True and assessed else 0,lead.expressed_interest is not None and assessed,'Interesse declarado em software avaliado manualmente; não inferimos intenção de compra a partir do conteúdo.')
    ]
    return {'score':sum(points for _,points,_,_ in criteria),'confidence':sum(CUSTOMER_WEIGHTS[key] for key,_,available,_ in criteria if available),'score_evidence':[{'criterion':key,'weight':CUSTOMER_WEIGHTS[key],'points':points,'available':available,'explanation':explanation,'urls':urls} for key,points,available,explanation in criteria],'scored_at':now()}

def refresh_customer_score(lead):
    for key,value in calculate_customer(lead).items():
        setattr(lead,key,value)
