import os
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

# Load .env as early as possible and search upwards for robustness
load_dotenv(find_dotenv(), override=False)


class Settings(BaseModel):
    database_url: str = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
    jwt_secret: str = os.environ.get("JWT_SECRET", "dev-secret-change-me")
    jwt_algorithm: str = os.environ.get("JWT_ALGORITHM", "HS256")
    access_token_expires_minutes: int = int(os.environ.get("ACCESS_TOKEN_EXPIRES_MINUTES", "30"))
    refresh_token_expires_days: int = int(os.environ.get("REFRESH_TOKEN_EXPIRES_DAYS", "30"))


settings = Settings()
