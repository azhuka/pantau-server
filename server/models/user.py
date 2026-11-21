from sqlalchemy import Column, Integer, String, Text, DateTime, TIMESTAMP, SmallInteger, func
from core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="operator")  # master_admin, operator, viewer
    is_active = Column(SmallInteger, default=1)
    password_changed_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)
    totp_secret = Column(String(64), nullable=True)
    totp_enabled = Column(SmallInteger, default=0)
    recovery_codes = Column(Text, nullable=True)
    permissions = Column(Text, nullable=True)  # JSON or comma-separated permissions
    created_at = Column(TIMESTAMP, server_default=func.now())
    created_by = Column(String(100), nullable=True)
    allowed_server_ids = Column(Text, nullable=True)

    @property
    def is_master_admin(self) -> bool:
        return self.role == "master_admin"

    def can_access_server(self, server_id: int) -> bool:
        if self.is_master_admin:
            return True
        if not self.allowed_server_ids:
            return True
        try:
            import json
            ids = json.loads(self.allowed_server_ids)
            return server_id in ids
        except Exception:
            return True

class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    ip_address = Column(String(45), primary_key=True)
    fails = Column(Integer, default=0)
    lock_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class AppSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    sid = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
