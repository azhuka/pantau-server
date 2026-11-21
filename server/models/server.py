from sqlalchemy import Column, Integer, BigInteger, Float, String, Text, DateTime, TIMESTAMP, SmallInteger, func
from core.database import Base

class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=True)
    api_key = Column(String(80), unique=True, index=True, nullable=False)
    is_active = Column(SmallInteger, default=1)
    is_maintenance = Column(SmallInteger, default=0)
    maintenance_until = Column(DateTime, nullable=True)
    maintenance_reason = Column(String(255), nullable=True)
    last_seen = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    group_name = Column(String(64), nullable=True)
    tier = Column(SmallInteger, default=1)
    tags = Column(String(255), nullable=True)
    custom_thresholds = Column(Text, nullable=True)
    is_proxmox_ha = Column(SmallInteger, default=0)
    platform_override = Column(String(20), nullable=True)
    is_isolated_net = Column(SmallInteger, default=0)
    allow_web_terminal = Column(SmallInteger, default=1)
    notes = Column(Text, nullable=True)

class ServerExtras(Base):
    __tablename__ = "server_extras"

    server_id = Column(Integer, primary_key=True)
    kernel = Column(String(100), nullable=True)
    os_label = Column(String(120), nullable=True)
    arch = Column(String(24), nullable=True)
    units = Column(Text, nullable=True)
    accounts = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    apt_upgradable = Column(Integer, default=0)
    apt_last_update = Column(DateTime, nullable=True)
    apt_packages = Column(Text, nullable=True)
    security = Column(Text, nullable=True)
    top_procs = Column(Text, nullable=True)
    agent_version = Column(String(16), nullable=True)
    cron_jobs = Column(Text, nullable=True)
    firewall = Column(Text, nullable=True)
    listening_ports = Column(Text, nullable=True)
    ssl_certs = Column(Text, nullable=True)
    system_logs = Column(Text, nullable=True)
    hardware_specs = Column(Text, nullable=True)
    installed_packages = Column(Text, nullable=True)
    systemd_units = Column(Text, nullable=True)
    backup_status = Column(Text, nullable=True)
    system_groups = Column(Text, nullable=True)
    kernel_events = Column(Text, nullable=True)
    available_logs = Column(Text, nullable=True)

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, index=True, nullable=False)
    service_name = Column(String(100), nullable=False)
    port = Column(Integer, nullable=True)
    process_name = Column(String(100), nullable=True)
    is_core = Column(SmallInteger, default=0)
    is_ignored = Column(SmallInteger, default=0)
    ignored_until = Column(DateTime, nullable=True)
    ignored_by = Column(String(100), nullable=True)
    ignored_reason = Column(String(255), nullable=True)
    ignore_mode = Column(String(20), default="permanent")

class SystemSnapshot(Base):
    __tablename__ = "sys_snapshots"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    server_id = Column(Integer, index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    cpu = Column(Float, nullable=True)
    load1 = Column(Float, nullable=True)
    load5 = Column(Float, nullable=True)
    load15 = Column(Float, nullable=True)
    mem_total = Column(BigInteger, nullable=True)
    mem_used = Column(BigInteger, nullable=True)
    mem_avail = Column(BigInteger, nullable=True)
    swap_total = Column(BigInteger, nullable=True)
    swap_used = Column(BigInteger, nullable=True)
    procs = Column(Integer, nullable=True)
    uptime_secs = Column(BigInteger, nullable=True)
    disks = Column(Text, nullable=True)
    net = Column(Text, nullable=True)

class SysSnapshotHour(Base):
    __tablename__ = "sys_snapshots_hourly"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    server_id = Column(Integer, index=True, nullable=False)
    bucket = Column(DateTime, index=True, nullable=False)
    samples = Column(Integer, default=1)
    cpu_avg = Column(Float, nullable=True)
    cpu_max = Column(Float, nullable=True)
    load1_avg = Column(Float, nullable=True)
    load5_avg = Column(Float, nullable=True)
    load15_avg = Column(Float, nullable=True)
    mem_total = Column(BigInteger, nullable=True)
    mem_used_avg = Column(BigInteger, nullable=True)
    mem_avail_avg = Column(BigInteger, nullable=True)
    swap_total = Column(BigInteger, nullable=True)
    swap_used_avg = Column(BigInteger, nullable=True)
    procs_avg = Column(Integer, nullable=True)
    disk_max_pct = Column(Float, nullable=True)

class Metric(Base):
    __tablename__ = "metrics"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    service_id = Column(Integer, index=True, nullable=True)
    timestamp = Column(TIMESTAMP, server_default=func.now(), index=True)
    status = Column(String(20), nullable=True)
    active_connections = Column(Integer, default=0)
    response_time_ms = Column(Integer, default=0)
    health_message = Column(String(255), nullable=True)
