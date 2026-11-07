"""Database connection and session factory for Pantau Server."""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

try:
    from config import settings
    from models import Base
except ImportError:
    from server.config import settings
    from server.models import Base

engine = create_engine(
    settings.database_url,
    pool_size=settings.POOL_SIZE,
    max_overflow=settings.POOL_MAX_OVERFLOW,
    pool_timeout=settings.POOL_TIMEOUT,
    pool_recycle=settings.POOL_RECYCLE,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI: menghasilkan sesi basis data per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
