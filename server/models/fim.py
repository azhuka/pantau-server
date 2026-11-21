from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, SmallInteger, func
from core.database import Base

class FIMPath(Base):
    __tablename__ = "fim_paths"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    server_id = Column(Integer, index=True, nullable=False)
    path = Column(String(500), nullable=False)
    category = Column(String(20), default="config")
    scope = Column(String(30), default="system")
    status = Column(String(20), default="SAFE")
    size_bytes = Column(BigInteger, default=0)
    size_human = Column(String(50), nullable=True)
    size_detail = Column(String(100), nullable=True)
    sha256_hash = Column(String(64), nullable=True)
    last_sha256_hash = Column(String(64), nullable=True)
    mtime = Column(DateTime, nullable=True)
    permissions = Column(String(30), nullable=True)
    owner_group = Column(String(60), nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    is_active = Column(SmallInteger, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(64), nullable=True)

class FIMEvent(Base):
    __tablename__ = "fim_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    server_id = Column(Integer, index=True, nullable=False)
    path = Column(String(500), nullable=False)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), default="warning")
    details = Column(Text, nullable=True)
    detected_at = Column(DateTime, server_default=func.now(), index=True)
    acknowledged = Column(SmallInteger, default=0)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
