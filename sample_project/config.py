import os
from pydantic import BaseModel


class Settings(BaseModel):
    PROJECT_NAME: str = "ShopFlow API"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-shopflow-jwt-key-32chars")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./shopflow.db")


settings = Settings()
