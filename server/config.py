import os
import secrets
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

PLACEHOLDER_PASSWORDS = {"", "CHANGE_ME_STRONG_PASSWORD"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
    )

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "monitor_user"
    DB_PASS: str = "CHANGE_ME_STRONG_PASSWORD"
    DB_NAME: str = "server_monitor"

    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8400
    APP_VERSION: str = "3.18.0"

    # Setel True bila dashboard diakses via HTTPS (reverse proxy) agar cookie
    # sesi hanya dikirim lewat koneksi terenkripsi. Default True untuk keamanan.
    SESSION_COOKIE_SECURE: bool = False

    # Kunci rahasia untuk CSRF token dan keamanan lainnya.
    # Jika kosong, akan digenerate otomatis saat startup (tidak persisten antar restart).
    # Untuk produksi, isi dengan nilai acak yang kuat di .env:
    # SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    SECRET_KEY: str = ""

    # IP proxy terpercaya (pisahkan dengan koma) untuk membaca X-Forwarded-For.
    # Contoh: "127.0.0.1,10.0.0.1"
    TRUSTED_PROXY_IPS: str = "127.0.0.1,::1"

    LOG_FILE: str = "/tmp/uvicorn-pantau.log"

    POOL_SIZE: int = 10
    POOL_MAX_OVERFLOW: int = 20
    POOL_RECYCLE: int = 3600

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

    @property
    def trusted_proxy_set(self) -> set:
        return {ip.strip() for ip in self.TRUSTED_PROXY_IPS.split(",") if ip.strip()}

    def validate_secrets(self) -> None:
        if self.DB_PASS in PLACEHOLDER_PASSWORDS:
            raise RuntimeError(
                "DB_PASS belum diganti dari nilai awal — isi .env dengan "
                "password kuat sebelum server dijalankan."
            )

    def resolve_secret_key(self) -> str:
        """Kembalikan SECRET_KEY, generate sementara jika kosong."""
        if self.SECRET_KEY:
            return self.SECRET_KEY
        generated = secrets.token_hex(32)
        print(
            "[PERINGATAN] SECRET_KEY tidak diset di .env — menggunakan kunci sementara. "
            "Token CSRF akan berubah setiap restart. "
            f"Tambahkan SECRET_KEY={generated} ke /opt/pantau/server/.env untuk produksi.",
            flush=True,
        )
        return generated


settings = Settings()
settings.validate_secrets()