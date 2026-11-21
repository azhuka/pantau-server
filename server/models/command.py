from sqlalchemy import Column, Integer, String, Text, DateTime, TIMESTAMP, func
from core.database import Base

class Command(Base):
    __tablename__ = "commands"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    server_id = Column(Integer, index=True, nullable=False)
    service_id = Column(Integer, nullable=True)
    action = Column(String(20), nullable=False)
    params = Column(Text, nullable=True)
    issued_by = Column(String(100), nullable=True)
    status = Column(String(20), default="pending", index=True)  # pending, executed, failed, canceled
    result = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    executed_at = Column(TIMESTAMP, nullable=True)

class LogRequest(Base):
    __tablename__ = "log_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    server_id = Column(Integer, index=True, nullable=False)
    unit = Column(String(100), nullable=False)
    lines = Column(Integer, default=50)
    detail = Column(String(128), nullable=True)
    status = Column(String(20), default="pending", index=True)
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    input_data = Column(String(500), nullable=True)
    input_at = Column(DateTime, nullable=True)
    input_queue = Column(Text, nullable=True)
