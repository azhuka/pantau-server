from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, Float, String, Text, DateTime, SmallInteger
from core.database import Base

class ProbeTarget(Base):
    __tablename__ = "probe_targets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    probe_type = Column(String(20), nullable=False)  # http, tcp, icmp, dns
    target = Column(String(255), nullable=False)
    port = Column(Integer, nullable=True)
    server_id = Column(Integer, index=True, nullable=True)
    tier = Column(SmallInteger, default=1)
    interval_seconds = Column(Integer, default=60)
    timeout_seconds = Column(Integer, default=5)
    http_method = Column(String(10), default="GET")
    http_headers = Column(Text, nullable=True)
    http_body = Column(Text, nullable=True)
    expected_status = Column(String(50), default="200")
    keyword_match = Column(String(255), nullable=True)
    ssl_verify = Column(SmallInteger, default=1)
    ssl_expiry_threshold_days = Column(Integer, default=14)
    latency_threshold_ms = Column(Integer, default=1000)
    consecutive_threshold = Column(Integer, default=3)
    is_active = Column(SmallInteger, default=1)
    status = Column(String(20), default="unknown")
    last_checked_at = Column(DateTime, nullable=True)
    last_latency_ms = Column(Float, nullable=True)
    last_status_code = Column(Integer, nullable=True)
    last_error = Column(String(255), nullable=True)
    ssl_expires_at = Column(DateTime, nullable=True)
    ssl_days_remaining = Column(Integer, nullable=True)
    consecutive_failures = Column(Integer, default=0)
    consecutive_successes = Column(Integer, default=0)
    uptime_24h = Column(Float, default=100.0)
    uptime_30d = Column(Float, default=100.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)

class ProbeLog(Base):
    __tablename__ = "probe_logs"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    probe_id = Column(Integer, index=True, nullable=False)
    checked_at = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String(20), nullable=False)
    latency_ms = Column(Float, nullable=True)
    status_code = Column(Integer, nullable=True)
    error_message = Column(String(255), nullable=True)
