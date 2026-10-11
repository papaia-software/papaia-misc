import os
import tempfile
import pytest

TEST_DB = tempfile.mktemp(prefix='papaia-test-',suffix='.db')
os.environ.update(DATABASE_URL=os.environ.get('TEST_DATABASE_URL',f'sqlite:///{TEST_DB}'),SECRET_KEY='test-secret-key-at-least-32-characters-long',ADMIN_PASSWORD='test-password-12345',SCHEDULER_ENABLED='false')
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        yield client

@pytest.fixture
def auth(client):
    assert client.post('/api/auth/login',json={'email':'admin@papaia.local','password':'test-password-12345'}).status_code==200
    return client

@pytest.fixture
def influencer():
    return {'name':'Perfil de teste fictício','platform':'Instagram','username':'teste_ficticio','url':'https://example.org/teste','professional_category':'Nutricionista (declarado)','niches':['Introdução alimentar','Nutrição pediátrica'],'target_audience':'Profissionais de nutrição','engagement':4.0,'followers':1200,'evidence_urls':['https://example.org/teste']}

@pytest.fixture
def rss():
    return b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Fonte de teste</title><link>https://example.org</link><description>Teste</description><item><title>Nova parceria para introducao alimentar</title><link>https://example.org/parceria?utm_source=teste</link><pubDate>Sun, 11 Oct 2026 09:00:00 GMT</pubDate><description>&lt;p&gt;Parceria anunciada em teste.&lt;script&gt;bad()&lt;/script&gt;&lt;/p&gt;</description></item></channel></rss>'''


@pytest.fixture(autouse=True)
def clear_public_http_cache():
    from app.network import clear_cache
    clear_cache()
    yield
    clear_cache()
