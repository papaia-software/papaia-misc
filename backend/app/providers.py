"""Provider contracts. Third-party actor schemas are configured, never assumed."""
from typing import Protocol
from datetime import datetime, timezone
import json
import re
import httpx
import feedparser
from bs4 import BeautifulSoup
from .config import settings
from .network import fetch_public, SourceError
from .schemas import InfluencerCreate

class InfluencerProvider(Protocol):
    def discover(self) -> list[InfluencerCreate]: ...

class NewsProvider(Protocol):
    def collect(self, url: str) -> list[dict]: ...

class RSSProvider:
    def collect(self,url):
        content, final_url = fetch_public(url)
        feed = feedparser.parse(content)
        if feed.bozo and not feed.entries:
            raise SourceError('A fonte não contém um feed RSS/Atom válido')
        result = []
        for entry in feed.entries[:100]:
            if not entry.get('link') or not entry.get('title'):
                continue
            published = entry.get('published_parsed') or entry.get('updated_parsed')
            date = datetime(*published[:6],tzinfo=timezone.utc) if published else None
            result.append({'title':entry.title[:500], 'url':entry.link,'source':feed.feed.get('title',urlsplit_host(final_url))[:250], 'summary':BeautifulSoup(entry.get('summary',''),'html.parser').get_text(' ',strip=True)[:20000], 'published_at':date})
        return result

def urlsplit_host(url):
    from urllib.parse import urlsplit
    return urlsplit(url).hostname

class ApifyDatasetProvider:
    def discover(self):
        cfg = settings()
        if not cfg.apify_token or not cfg.apify_dataset_id:
            raise SourceError('Integração pendente: configure APIFY_TOKEN e APIFY_DATASET_ID')
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',cfg.apify_dataset_id):
            raise SourceError('Identificador de dataset inválido')
        mapping = json.loads(cfg.apify_field_map)
        records = []
        # Read an existing dataset only. No paid Actor execution.
        with httpx.Client(timeout=30,trust_env=False) as client:
            response = client.get(f'https://api.apify.com/v2/datasets/{cfg.apify_dataset_id}/items',headers={'Authorization':f'Bearer {cfg.apify_token}'},params={'format':'json','clean':'true','limit':100})
            if response.status_code == 429:
                raise SourceError('Apify limitou a requisição; tente novamente mais tarde')
            if response.status_code != 200:
                raise SourceError(f'Apify retornou HTTP {response.status_code}; verifique credenciais e acesso ao dataset')
            try:
                items = response.json()
                if not isinstance(items,list):
                    raise ValueError('Lista esperada')
                for item in items:
                    data = {key:item.get(source) for key,source in mapping.items() if item.get(source) is not None} if mapping else item
                    records.append(InfluencerCreate.model_validate(data))
            except (ValueError,TypeError) as exc:
                raise SourceError('Dataset incompatível. Configure APIFY_FIELD_MAP conforme o schema documentado; nenhum dado foi importado') from exc
        return records

PROVIDERS: dict[str,InfluencerProvider] = {'apify':ApifyDatasetProvider()}
