import os
import secrets
from pydantic_settings import BaseSettings

_RUNTIME_SECRET = secrets.token_hex(32)


class Settings(BaseSettings):
    APP_VERSION: str = "0.1.74"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "pantau_db"
    DB_PASS: str = "pantau_server"
    DB_NAME: str = "pantau_db"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8400
    SECRET_KEY: str = ""
    ALLOWED_ORIGINS: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    @property
    def effective_secret_key(self) -> str:
        key = (self.SECRET_KEY or "").strip()
        if not key or key == "default_secret_key":
            return _RUNTIME_SECRET
        return key

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in (self.ALLOWED_ORIGINS or "").split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    class Config:
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        extra = "allow"


settings = Settings()
if not settings.SECRET_KEY or settings.SECRET_KEY == "default_secret_key":
    settings.SECRET_KEY = settings.effective_secret_key
