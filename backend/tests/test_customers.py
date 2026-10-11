import csv
import io
BASE={'name':'Teste fictício','username':'@cliente_teste','url':'https://example.org/perfil','professional_category':'Nutricionista','niches':['Introdução alimentar']}
def create(auth,**kw):
    r=auth.post('/api/customer-leads',json={**BASE,**kw});assert r.status_code==201,r.text;return r.json()
def test_auth(client):
    for p in ['/api/customer-leads','/api/customer-leads/export','/api/customer-leads/summary']:assert client.get(p).status_code==401

def test_crud(auth):
    lead=create(auth);assert lead['score']==70 and lead['confidence']==70
    assert lead['username']=='cliente_teste'
    assert auth.post('/api/customer-leads',json=BASE).status_code==409
    path='/api/customer-leads/'+str(lead['id'])
    assert auth.patch(path,json={'stage':'Assinante'}).status_code==200
    assert auth.get('/api/customer-leads/summary').json()['subscribers']==1
    assert auth.get('/api/customer-leads?stage=Novo').json()['total']==0
    assert auth.patch(path,json={'stage':'Parceria fechada'}).status_code==422
    assert auth.delete(path).status_code==204
    assert auth.get(path).status_code==404

def test_evidence(auth):
    lead=create(auth,professional_category=None,niches=[]);assert lead['score']==lead['confidence']==0
    assert auth.post('/api/customer-leads',json={**BASE,'username':'other','offers_consultations':True}).status_code==422
    lead=create(auth,username='complete',offers_consultations=True,expressed_interest=True,evidence_urls=['https://example.org/evidence'])
    assert lead['score']==lead['confidence']==100
    path='/api/customer-leads/'+str(lead['id'])
    assert auth.patch(path,json={'evidence_urls':[]}).status_code==422
    r=auth.patch(path,json={'offers_consultations':None,'expressed_interest':None,'evidence_urls':[]});assert r.status_code==200 and r.json()['score']==70
    assert create(auth,username='student',professional_category='Estudante de nutrição')['score']==30

def test_csv(auth):
    invalid='name,username,url\nTeste,valid,https://example.org/a\nErro,invalid,ftp://example.org\n'
    assert auth.post('/api/customer-leads/import',files={'file':('a.csv',invalid,'text/csv')}).status_code==422
    assert auth.get('/api/customer-leads').json()['total']==0
    create(auth,name='=FORMULA',notes='@formula',stage='Qualificado')
    export=auth.get('/api/customer-leads/export?stage=Qualificado');assert export.status_code==200
    rows=list(csv.DictReader(io.StringIO(export.content.decode('utf-8-sig'))));assert rows[0]['name']=="'=FORMULA" and rows[0]['notes']=="'@formula"
    r=auth.post('/api/customer-leads/import',files={'file':('a.csv',export.content,'text/csv')});assert r.status_code==200,r.text
    assert r.json()['imported']==0 and r.json()['skipped']==1

def test_research(auth,monkeypatch):
    import httpx
    def forbidden(*a,**kw):raise AssertionError('No paid/network requests')
    monkeypatch.setattr(httpx,'get',forbidden)
    create(auth)
    r=auth.post('/api/customer-leads/search-plan',json={'query':'Introdução alimentar @perfil'}).json()
    assert r['mode']=='manual_research' and r['cost']==0 and r['seed_handles']==['perfil']
    assert len(r['local_matches'])==1 and auth.get('/api/customer-leads').json()['total']==1

def test_influencer_copy_independent(auth,influencer):
    original=auth.post('/api/influencers',json=influencer).json()
    r=auth.post('/api/customer-leads/from-influencer/'+str(original['id']))
    assert r.status_code==201,r.text
    lead=r.json();assert lead['influencer_id']==original['id'] and lead['score']==70
    assert auth.patch('/api/customer-leads/'+str(lead['id']),json={'stage':'Assinante'}).status_code==200
    assert auth.get('/api/influencers/'+str(original['id'])).json()['stage']!='Assinante'
