from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    PROJECT_NAME: str = "Nexus HR"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment variables
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security Auth
    API_SECRET_KEY: str
    
    # ERP
    ERP_BASE_URL: str
    ERP_API_KEY: str
    ERP_API_SECRET: str = ""
    ERP_VERIFY_SSL: bool = True
    ERP_TIMEOUT_SECONDS: float = 15.0
    ERP_WEBHOOK_SECRET: str = ""
    
    # LLM
    GOOGLE_API_KEY: str
    GOOGLE_EMBEDDING_MODEL: str = "models/text-embedding-004"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
