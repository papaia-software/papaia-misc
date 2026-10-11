import unicodedata

WEIGHTS = {'theme':30,'audience':25,'engagement':20,'credibility':15,'commercial':10}
NICHES = ['nutrição materno-infantil','nutrição pediátrica','introdução alimentar','alimentação complementar','seletividade alimentar','gestação','amamentação','maternidade','pediatria','desenvolvimento infantil','alimentação saudável infantil','nutricionistas que atendem famílias','educação alimentar']

def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c))

def calculate(influencer, profile, metrics, campaign='B2B', weights=None):
    weights = weights or WEIGHTS
    text = normalize(' '.join(influencer.niches or [])+' '+(profile.biography or ''))
    matched = [n for n in NICHES if normalize(n) in text]
    audience = normalize(influencer.target_audience or '')
    profession = normalize(influencer.professional_category or '')
    audience_match = any(t in audience for t in (['nutricion','profission','clinica'] if campaign=='B2B' else ['famil','maes','pais','responsaveis']))
    values = {
        'theme': (min(len(matched)/2,1), bool(text.strip()), f'Temas declarados: {", ".join(matched) or "nenhum tema do catálogo identificado"}.'),
        'audience': (1 if audience_match else 0, bool(audience), 'Compatibilidade com público declarado; sem inferência demográfica.'),
        'engagement': (min((metrics.engagement or 0)/5,1) if metrics else 0, metrics is not None and metrics.engagement is not None, 'Taxa informada, referência de 5%; não mede autenticidade.'),
        'credibility': (0, False, 'Segurança e credibilidade exigem revisão humana; não atesta habilitação profissional.'),
        'commercial': (0.5 if ((campaign=='B2B' and 'nutricion' in profession) or (campaign=='B2C' and audience_match)) else 0, bool(profession or audience), 'Afinidade comercial declarada; sem uso da quantidade de seguidores.')
    }
    evidence = [{'criterion':k,'points':round(v[0]*weights[k],2),'available':v[1],'explanation':v[2], 'urls':profile.evidence_urls or [profile.url]} for k,v in values.items()]
    return {'value':round(sum(e['points'] for e in evidence),2),'confidence':sum(weights[k] for k,v in values.items() if v[1]), 'weights':weights,'evidence':evidence,'explanation':'Heurística conservadora baseada em dados declarados da fonte. Métricas ausentes recebem zero; pesos não são redistribuídos. Confiança indica cobertura, não veracidade. Revisão humana necessária.'}
