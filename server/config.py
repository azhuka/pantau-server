from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent

PLACEHOLDER_PASSWORDS = {"", "CHANGE_ME_STRONG_PASSWORD"}


class Settings(BaseSettings):
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "monitor_user"
    DB_PASS: str = "CHANGE_ME_STRONG_PASSWORD"
    DB_NAME: str = "server_monitor"

    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8400

    LOG_FILE: str = "/tmp/uvicorn-pantau.log"

    POOL_SIZE: int = 10
    POOL_MAX_OVERFLOW: int = 20
    POOL_RECYCLE: int = 3600

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"

    @property
    def templates_dir(self) -> str:
        return str(BASE_DIR / "templates")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{quote_plus(self.DB_PASS)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    def validate_secrets(self) -> None:
        if self.DB_PASS in PLACEHOLDER_PASSWORDS:
            raise RuntimeError(
                "DB_PASS belum diganti dari nilai awal — isi .env dengan "
                "password kuat sebelum server dijalankan."
            )


settings = Settings()
settings.validate_secrets()