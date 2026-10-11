from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='../.env', extra='ignore')
    environment: str = 'development'
    database_url: str = 'sqlite:///./papaia.db'
    secret_key: str = ''
    admin_email: str = 'admin@papaia.local'
    admin_password: str = ''
    cookie_secure: bool = False
    allowed_origin: str = 'http://localhost:5173'
    apify_token: str = ''
    apify_dataset_id: str = ''
    apify_field_map: str = '{}'
    provider_daily_limit: int = 20
    scheduler_enabled: bool = False
    schedule_hour: int = 6
    demo_enabled: bool = False
    fetch_max_bytes: int = 2_000_000

@lru_cache
def settings():
    return Settings()
