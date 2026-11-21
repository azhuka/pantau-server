from sqlalchemy import Column, Integer, String, Text, DateTime, SmallInteger, func
from core.database import Base

class ServerProblem(Base):
    __tablename__ = "server_problems"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    server_id = Column(Integer, index=True, nullable=True)
    probe_id = Column(Integer, index=True, nullable=True)
    key = Column(String(160), nullable=False, index=True)
    severity = Column(String(10), nullable=False)  # danger, warning, info
    message = Column(String(255), nullable=False)
    tip = Column(String(500), nullable=True)
    started_at = Column(DateTime, nullable=False, default=func.now())
    resolved_at = Column(DateTime, nullable=True, index=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    last_active_at = Column(DateTime, nullable=True)
    resolved_note = Column(String(100), nullable=True)
    is_ignored = Column(SmallInteger, default=0)
    ignored_until = Column(DateTime, nullable=True)
    ignored_by = Column(String(100), nullable=True)
    ignored_reason = Column(String(255), nullable=True)
    context = Column(Text, nullable=True)
    ignore_mode = Column(String(20), default="permanent")

    @property
    def is_active(self) -> bool:
        return self.resolved_at is None
