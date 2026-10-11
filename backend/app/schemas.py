from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from urllib.parse import urlsplit

STAGES = ['Descoberto','Em análise','Qualificado','Contato pendente','Contatado','Respondeu','Em negociação','Parceria fechada','Parceria concluída','Descartado']
Platform = Literal['Instagram','TikTok','YouTube']
Stage = Literal['Descoberto','Em análise','Qualificado','Contato pendente','Contatado','Respondeu','Em negociação','Parceria fechada','Parceria concluída','Descartado']

def public_url(value):
    if value is None:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,80,443):
        raise ValueError('Use URL HTTP(S) sem credenciais e com porta padrão')
    if len(value) > 2048:
        raise ValueError('URL muito longa')
    return value

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)

class Login(Input):
    email: str
    password: str

class InfluencerCreate(Input):
    name: str = Field(min_length=1, max_length=200)
    platform: Platform
    username: str = Field(min_length=1, max_length=200, pattern=r'^[\w.@-]+$')
    url: str
    photo_url: str | None = None
    biography: str | None = Field(default=None, max_length=10000)
    public_contact: str | None = Field(default=None, max_length=254)
    professional_category: str | None = None
    niches: list[str] = Field(default_factory=list, max_length=30)
    region: str | None = None
    language: str | None = None
    target_audience: str | None = None
    followers: int | None = Field(default=None, ge=0)
    engagement: float | None = Field(default=None, ge=0, le=100)
    average_views: int | None = Field(default=None, ge=0)
    posting_frequency: float | None = Field(default=None, ge=0)
    audience_countries: dict | None = None
    audience_demographics: dict | None = None
    evidence_urls: list[str] = Field(default_factory=list, max_length=30)
    relevant_posts: list[str] = Field(default_factory=list, max_length=30)
    previous_collaborations: list[str] = Field(default_factory=list, max_length=30)
    _url = field_validator('url', 'photo_url')(public_url)
    @field_validator('evidence_urls','relevant_posts')
    @classmethod
    def urls(cls, values):
        return [public_url(v) for v in values]
    @field_validator('username')
    @classmethod
    def normalize(cls, value):
        return value.lstrip('@').lower()

class InfluencerPatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    stage: Stage | None = None
    professional_category: str | None = None
    niches: list[str] | None = None
    region: str | None = None
    language: str | None = None
    target_audience: str | None = None
    notes: str | None = Field(default=None, max_length=20000)
    owner: str | None = Field(default=None, max_length=120)
    follow_up: datetime | None = None
    @model_validator(mode='after')
    def non_null(self):
        for key in ('name','stage','niches'):
            if key in self.model_fields_set and getattr(self,key) is None:
                raise ValueError(f'{key} não pode ser nulo')
        return self

class Discover(Input):
    query: str = Field(default='', max_length=2000)
    platform: Platform | None = None
    niche: str | None = None
    min_followers: int | None = Field(default=None, ge=0)
    max_followers: int | None = Field(default=None, ge=0)
    min_engagement: float | None = Field(default=None, ge=0, le=100)
    region: str | None = None
    language: str | None = None
    target_audience: str | None = None
    professional_category: str | None = None
    min_score: float | None = Field(default=None, ge=0, le=100)
    confirm: bool = False

class ScoreRequest(Input):
    campaign_type: Literal['B2B','B2C'] = 'B2B'
    weights: dict[str,float] | None = None
    manual_value: float | None = Field(default=None, ge=0, le=100)
    rationale: str | None = Field(default=None, max_length=5000)
    evidence_urls: list[str] = Field(default_factory=list)
    @model_validator(mode='after')
    def validate_score(self):
        expected = {'theme','audience','engagement','credibility','commercial'}
        if self.weights is not None and (set(self.weights) != expected or any(v < 0 or v > 100 for v in self.weights.values()) or abs(sum(self.weights.values())-100)>0.01):
            raise ValueError('Os cinco pesos devem somar 100')
        if self.manual_value is not None and (not self.rationale or not self.evidence_urls):
            raise ValueError('Avaliação manual exige justificativa e evidências públicas')
        for url in self.evidence_urls:
            public_url(url)
        return self

class CampaignCreate(Input):
    name: str = Field(min_length=1,max_length=200)
    objective: Literal['B2B','B2C']
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

class NegotiationCreate(Input):
    influencer_id: int
    campaign_id: int | None = None
    requested_value: float | None = Field(default=None,ge=0,le=9_999_999_999.99)
    agreed_value: float | None = Field(default=None,ge=0,le=9_999_999_999.99)
    partnership_type: str | None = None
    deliverables: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    campaign_code: str | None = None
    result: str | None = None

class NegotiationPatch(Input):
    campaign_id: int | None = None
    requested_value: float | None = Field(default=None,ge=0,le=9_999_999_999.99)
    agreed_value: float | None = Field(default=None,ge=0,le=9_999_999_999.99)
    partnership_type: str | None = None
    deliverables: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    campaign_code: str | None = None
    result: str | None = None

class ContactCreate(Input):
    channel: str = Field(min_length=1,max_length=60)
    notes: str = Field(min_length=1,max_length=10000)
    occurred_at: datetime | None = None

class SourceCreate(Input):
    url: str
    kind: Literal['rss','page'] = 'rss'
    enabled: bool = True
    access_confirmed: bool = False
    _url = field_validator('url')(public_url)

class CompetitorCreate(Input):
    name: str = Field(min_length=1,max_length=200)
    website: str
    description: str | None = None
    category: str | None = None
    social_urls: list[str] = Field(default_factory=list)
    blog_url: str | None = None
    keywords: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    priority: Literal['low','normal','high'] = 'normal'
    sources: list[SourceCreate] = Field(default_factory=list, max_length=20)
    _url = field_validator('website','blog_url')(public_url)
    @field_validator('social_urls')
    @classmethod
    def urls(cls, values):
        return [public_url(v) for v in values]

class CompetitorPatch(Input):
    name: str | None = Field(default=None,min_length=1,max_length=200)
    website: str | None = None
    description: str | None = None
    category: str | None = None
    social_urls: list[str] | None = None
    blog_url: str | None = None
    keywords: list[str] | None = None
    products: list[str] | None = None
    priority: Literal['low','normal','high'] | None = None
    _url = field_validator('website','blog_url')(public_url)
    @model_validator(mode='after')
    def required(self):
        for key in ('name','website','social_urls','keywords','products','priority'):
            if key in self.model_fields_set and getattr(self,key) is None:
                raise ValueError(f'{key} não pode ser nulo')
        if self.social_urls:
            for url in self.social_urls:
                public_url(url)
        return self

class ManualNews(Input):
    title: str = Field(min_length=1,max_length=500)
    source: str = Field(min_length=1,max_length=250)
    url: str
    summary: str | None = Field(default=None,max_length=20000)
    published_at: datetime | None = None
    competitor_id: int | None = None
    _url = field_validator('url')(public_url)

class NewsPatch(Input):
    read: bool | None = None
    watched: bool | None = None
    @model_validator(mode='after')
    def required(self):
        if any(getattr(self,k) is None for k in self.model_fields_set):
            raise ValueError('Use true ou false')
        return self

class LinkInfluencer(Input):
    influencer_id: int
    confirmed: bool

class AlertPatch(Input):
    read: bool

class JobPatch(Input):
    enabled: bool
    interval_hours: int = Field(default=24,ge=1,le=720)

class AlertConfig(Input):
    enabled: bool = True
    threshold: int = Field(default=70,ge=0,le=100)
    categories: list[str] = Field(default_factory=lambda: ['Lançamento de produto','Nova funcionalidade','Parceria','Alteração comercial'])

CUSTOMER_STAGES = ['Novo','Em análise','Qualificado','Contato pendente','Contatado','Demonstração','Em teste','Assinante','Descartado']
CustomerStage = Literal['Novo','Em análise','Qualificado','Contato pendente','Contatado','Demonstração','Em teste','Assinante','Descartado']

class CustomerLeadCreate(Input):
    name: str = Field(min_length=1,max_length=200)
    platform: Platform = 'Instagram'
    username: str = Field(min_length=1,max_length=200,pattern=r'^[\w.@-]+$')
    url: str
    professional_category: str | None = Field(default=None,max_length=200)
    biography: str | None = Field(default=None,max_length=10000)
    niches: list[str] = Field(default_factory=list,max_length=30)
    region: str | None = Field(default=None,max_length=200)
    public_contact: str | None = Field(default=None,max_length=254)
    evidence_urls: list[str] = Field(default_factory=list,max_length=30)
    source_url: str | None = None
    offers_consultations: bool | None = None
    expressed_interest: bool | None = None
    stage: CustomerStage = 'Novo'
    owner: str | None = Field(default=None,max_length=120)
    follow_up: datetime | None = None
    notes: str | None = Field(default=None,max_length=20000)
    _url = field_validator('url','source_url')(public_url)
    @field_validator('username')
    @classmethod
    def normalize_username(cls,value):
        result=value.lstrip('@').lower()
        if not result:
            raise ValueError('Username inválido')
        return result
    @field_validator('evidence_urls')
    @classmethod
    def urls(cls,values):
        return [public_url(v) for v in values]
    @model_validator(mode='after')
    def check_evidence(self):
        if (self.offers_consultations is not None or self.expressed_interest is not None) and not self.evidence_urls:
            raise ValueError('Sinais avaliados exigem ao menos um link público de evidência')
        return self

class CustomerLeadPatch(Input):
    name: str | None = Field(default=None,min_length=1,max_length=200)
    platform: Platform | None = None
    username: str | None = Field(default=None,min_length=1,max_length=200,pattern=r'^[\w.@-]+$')
    url: str | None = None
    professional_category: str | None = Field(default=None,max_length=200)
    biography: str | None = Field(default=None,max_length=10000)
    niches: list[str] | None = Field(default=None,max_length=30)
    region: str | None = Field(default=None,max_length=200)
    public_contact: str | None = Field(default=None,max_length=254)
    evidence_urls: list[str] | None = Field(default=None,max_length=30)
    source_url: str | None = None
    offers_consultations: bool | None = None
    expressed_interest: bool | None = None
    stage: CustomerStage | None = None
    owner: str | None = Field(default=None,max_length=120)
    follow_up: datetime | None = None
    notes: str | None = Field(default=None,max_length=20000)
    _url = field_validator('url','source_url')(public_url)
    @model_validator(mode='after')
    def validate_patch(self):
        for key in ('name','platform','username','url','niches','evidence_urls','stage'):
            if key in self.model_fields_set and getattr(self,key) is None:
                raise ValueError(f'{key} não pode ser nulo')
        if self.username is not None:
            self.username=self.username.lstrip('@').lower()
            if not self.username:
                raise ValueError('Username inválido')
        for url in self.evidence_urls or []:
            public_url(url)
        return self

class CustomerSearchRequest(Input):
    query: str = Field(min_length=2,max_length=1000)
