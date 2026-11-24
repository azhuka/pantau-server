import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_VERSION: str = "0.1.58"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "pantau_db"
    DB_PASS: str = "pantau_server"
    DB_NAME: str = "pantau_db"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8401
    SECRET_KEY: str = "default_secret_key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    class Config:
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        extra = "allow"

settings = Settings()
