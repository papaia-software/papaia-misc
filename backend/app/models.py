from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, CheckConstraint, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc)

class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class User(Record, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(120), default='Equipe Papaia')

class Influencer(Record, Base):
    __tablename__ = 'influencers'
    name: Mapped[str] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(40), default='Descoberto', index=True)
    professional_category: Mapped[str | None] = mapped_column(String(200))
    niches: Mapped[list] = mapped_column(JSON, default=list)
    region: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str | None] = mapped_column(String(50))
    target_audience: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120))
    follow_up: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("stage IN ('Descoberto','Em análise','Qualificado','Contato pendente','Contatado','Respondeu','Em negociação','Parceria fechada','Parceria concluída','Descartado')", name='valid_stage'),)

class InfluencerProfile(Record, Base):
    __tablename__ = 'influencer_profiles'
    influencer_id: Mapped[int] = mapped_column(ForeignKey('influencers.id', ondelete='CASCADE'), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    username: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    biography: Mapped[str | None] = mapped_column(Text)
    public_contact: Mapped[str | None] = mapped_column(String(254))
    provider: Mapped[str] = mapped_column(String(40), default='manual')
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    relevant_posts: Mapped[list] = mapped_column(JSON, default=list)
    previous_collaborations: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint('platform', 'username', name='uq_profile_identity'), CheckConstraint("platform IN ('Instagram','TikTok','YouTube')", name='valid_platform'))

class InfluencerMetric(Record, Base):
    __tablename__ = 'influencer_metrics'
    profile_id: Mapped[int] = mapped_column(ForeignKey('influencer_profiles.id', ondelete='CASCADE'), index=True)
    followers: Mapped[int | None] = mapped_column(Integer)
    engagement: Mapped[float | None] = mapped_column(Float)
    average_views: Mapped[int | None] = mapped_column(Integer)
    posting_frequency: Mapped[float | None] = mapped_column(Float)
    audience_countries: Mapped[dict | None] = mapped_column(JSON)
    audience_demographics: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (CheckConstraint('followers IS NULL OR followers >= 0', name='positive_followers'), CheckConstraint('engagement IS NULL OR (engagement >= 0 AND engagement <= 100)', name='engagement_range'))

class InfluencerScore(Record, Base):
    __tablename__ = 'influencer_scores'
    influencer_id: Mapped[int] = mapped_column(ForeignKey('influencers.id', ondelete='CASCADE'), index=True)
    campaign_type: Mapped[str] = mapped_column(String(3))
    value: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    weights: Mapped[dict] = mapped_column(JSON)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint('value >= 0 AND value <= 100', name='score_range'),)

class ScoreEvidence(Record, Base):
    __tablename__ = 'influencer_score_evidence'
    score_id: Mapped[int] = mapped_column(ForeignKey('influencer_scores.id', ondelete='CASCADE'), index=True)
    criterion: Mapped[str] = mapped_column(String(100))
    points: Mapped[float] = mapped_column(Float)
    available: Mapped[bool] = mapped_column(Boolean)
    explanation: Mapped[str] = mapped_column(Text)
    urls: Mapped[list] = mapped_column(JSON, default=list)

class InfluencerTag(Record, Base):
    __tablename__ = 'influencer_tags'
    influencer_id: Mapped[int] = mapped_column(ForeignKey('influencers.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint('influencer_id','name'),)

class Campaign(Record, Base):
    __tablename__ = 'campaigns'
    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(String(3))
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("objective IN ('B2B','B2C')", name='campaign_objective'),)

class CampaignInfluencer(Record, Base):
    __tablename__ = 'campaign_influencers'
    campaign_id: Mapped[int] = mapped_column(ForeignKey('campaigns.id', ondelete='CASCADE'), index=True)
    influencer_id: Mapped[int] = mapped_column(ForeignKey('influencers.id', ondelete='CASCADE'), index=True)
    campaign_code: Mapped[str | None] = mapped_column(String(200))
    result: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint('campaign_id', 'influencer_id'),)

class Negotiation(Record, Base):
    __tablename__ = 'negotiations'
    influencer_id: Mapped[int] = mapped_column(ForeignKey('influencers.id', ondelete='CASCADE'), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey('campaigns.id', ondelete='SET NULL'), index=True)
    requested_value: Mapped[float | None] = mapped_column(Numeric(12,2))
    agreed_value: Mapped[float | None] = mapped_column(Numeric(12,2))
    partnership_type: Mapped[str | None] = mapped_column(String(100))
    deliverables: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign_code: Mapped[str | None] = mapped_column(String(200))
    result: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint('requested_value IS NULL OR requested_value >= 0', name='requested_positive'), CheckConstraint('agreed_value IS NULL OR agreed_value >= 0', name='agreed_positive'))

class ContactInteraction(Record, Base):
    __tablename__ = 'contact_interactions'
    influencer_id: Mapped[int] = mapped_column(ForeignKey('influencers.id', ondelete='CASCADE'), index=True)
    channel: Mapped[str] = mapped_column(String(60))
    notes: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Competitor(Record, Base):
    __tablename__ = 'competitors'
    name: Mapped[str] = mapped_column(String(200), unique=True)
    website: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(200))
    social_urls: Mapped[list] = mapped_column(JSON, default=list)
    blog_url: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    products: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[str] = mapped_column(String(20), default='normal')
    demo: Mapped[bool] = mapped_column(Boolean, default=False)

class CompetitorSource(Record, Base):
    __tablename__ = 'competitor_sources'
    competitor_id: Mapped[int] = mapped_column(ForeignKey('competitors.id', ondelete='CASCADE'), index=True)
    url: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default='rss')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    access_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('competitor_id','url'),)

class News(Record, Base):
    __tablename__ = 'news'
    title: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(250))
    url: Mapped[str] = mapped_column(Text, unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80), default='Outros', index=True)
    relevance: Mapped[int] = mapped_column(Integer, default=0, index=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    analysis: Mapped[dict | None] = mapped_column(JSON)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    watched: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint('relevance >= 0 AND relevance <= 100', name='news_relevance'),)

class NewsCompetitor(Record, Base):
    __tablename__ = 'news_competitors'
    news_id: Mapped[int] = mapped_column(ForeignKey('news.id', ondelete='CASCADE'), index=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey('competitors.id', ondelete='CASCADE'), index=True)
    __table_args__ = (UniqueConstraint('news_id','competitor_id'),)

class NewsInfluencer(Record, Base):
    __tablename__ = 'news_influencers'
    news_id: Mapped[int] = mapped_column(ForeignKey('news.id', ondelete='CASCADE'), index=True)
    influencer_id: Mapped[int] = mapped_column(ForeignKey('influencers.id', ondelete='CASCADE'), index=True)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    __table_args__ = (UniqueConstraint('news_id','influencer_id'),)

class MonitoringJob(Record, Base):
    __tablename__ = 'monitoring_jobs'
    key: Mapped[str] = mapped_column(String(100), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class MonitoringSnapshot(Record, Base):
    __tablename__ = 'monitoring_snapshots'
    source_id: Mapped[int] = mapped_column(ForeignKey('competitor_sources.id', ondelete='CASCADE'), index=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    diff: Mapped[str | None] = mapped_column(Text)

class Alert(Record, Base):
    __tablename__ = 'alerts'
    news_id: Mapped[int | None] = mapped_column(ForeignKey('news.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(80))
    read: Mapped[bool] = mapped_column(Boolean, default=False)

class ProviderConfig(Record, Base):
    __tablename__ = 'provider_configs'
    name: Mapped[str] = mapped_column(String(80), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

class CollectionRun(Record, Base):
    __tablename__ = 'collection_runs'
    provider: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class AuditLog(Record, Base):
    __tablename__ = 'audit_logs'
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[int | None] = mapped_column(Integer)

class CustomerLead(Record, Base):
    """Subscription prospects have a CRM independent of influencer partnerships."""
    __tablename__ = 'customer_leads'
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(20))
    username: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    professional_category: Mapped[str | None] = mapped_column(String(200))
    biography: Mapped[str | None] = mapped_column(Text)
    niches: Mapped[list] = mapped_column(JSON, default=list)
    region: Mapped[str | None] = mapped_column(String(200))
    public_contact: Mapped[str | None] = mapped_column(String(254))
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    source_url: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(30), default='manual')
    offers_consultations: Mapped[bool | None] = mapped_column(Boolean)
    expressed_interest: Mapped[bool | None] = mapped_column(Boolean)
    stage: Mapped[str] = mapped_column(String(40), default='Novo', index=True)
    owner: Mapped[str | None] = mapped_column(String(120))
    follow_up: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    influencer_id: Mapped[int | None] = mapped_column(ForeignKey('influencers.id', ondelete='SET NULL'), index=True)
    score: Mapped[float] = mapped_column(Float, default=0, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    score_evidence: Mapped[list] = mapped_column(JSON, default=list)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint('platform','username',name='uq_customer_profile'),
        CheckConstraint("platform IN ('Instagram','TikTok','YouTube')",name='customer_platform'),
        CheckConstraint("stage IN ('Novo','Em análise','Qualificado','Contato pendente','Contatado','Demonstração','Em teste','Assinante','Descartado')",name='customer_stage'),
        CheckConstraint('score >= 0 AND score <= 100',name='customer_score_range'),
        CheckConstraint('confidence >= 0 AND confidence <= 100',name='customer_confidence_range'),
    )
