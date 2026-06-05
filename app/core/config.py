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
    API_SECRET_KEY: str = ""
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_PUBLIC_KEY_PATH: str = ""
    JWT_AUDIENCE: str = ""
    JWT_ISSUER: str = ""
    JWT_LEEWAY_SECONDS: int = 30
    JWT_EMPLOYEE_ID_CLAIM: str = "employee_id"
    JWT_EMAIL_CLAIM: str = "email"
    JWT_SUB_CLAIM: str = "sub"
    
    # ERP
    ERP_BASE_URL: str
    ERP_API_KEY: str
    ERP_API_SECRET: str = ""
    ERP_AUTH_MODE: str = "auto"
    ERP_AUTH_HEADER: str = ""
    ERP_SITE_NAME: str = ""
    ERP_VERIFY_SSL: bool = True
    ERP_TIMEOUT_SECONDS: float = 15.0
    ERP_WEBHOOK_SECRET: str = ""
    
    # LLM
    GOOGLE_API_KEY: str
    GOOGLE_EMBEDDING_MODEL: str = "models/text-embedding-004"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True)

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
