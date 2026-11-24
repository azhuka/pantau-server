from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, SmallInteger, func
from core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    target = Column(String(255), nullable=True)
    result = Column(String(500), nullable=True)
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), index=True)
    server_id = Column(Integer, index=True, nullable=True)

class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    scope_type = Column(String(30), default="single")
    server_id = Column(Integer, nullable=True)
    server_ids = Column(Text, nullable=True)
    server_group = Column(String(64), nullable=True)
    schedule_type = Column(String(30), default="once")
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    repeat_days = Column(String(50), nullable=True)
    repeat_time_start = Column(String(10), nullable=True)
    repeat_time_end = Column(String(10), nullable=True)
    is_active = Column(SmallInteger, default=1)
    status = Column(String(30), default="scheduled")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(64), nullable=True)

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
