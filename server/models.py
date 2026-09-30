from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text,
    BigInteger, SmallInteger,
)
from sqlalchemy.dialects.mysql import INTEGER as MYSQL_INTEGER, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, relationship

# Kolom foreign key type-nya harus sama persis dengan servers.id (INT UNSIGNED)
INTEGER_UNSIGNED = MYSQL_INTEGER(unsigned=True)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum("admin", "viewer", name="user_role"), nullable=False, default="admin")
    created_at = Column(DateTime, default=datetime.utcnow)


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    # Menyimpan sha256(key) berprefix "sha256:" agar raw key tidak bocor bila DB diretas
    api_key = Column(String(80), nullable=False, unique=True)
    is_active = Column(SmallInteger, nullable=False, default=1)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    services = relationship("Service", back_populates="server", cascade="all, delete-orphan")
    commands = relationship("Command", back_populates="server", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    service_name = Column(String(100), nullable=False)
    port = Column(Integer, nullable=False)
    process_name = Column(String(100), nullable=False)

    server = relationship("Server", back_populates="services")
    metrics = relationship("Metric", back_populates="service", cascade="all, delete-orphan")
    commands = relationship("Command", back_populates="service", cascade="all, delete-orphan")

    __table_args__ = (
        Index("uk_server_service", "server_id", "service_name", unique=True),
    )


class Metric(Base):
    __tablename__ = "metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum("up", "down", name="service_status"), nullable=False, default="down")
    active_connections = Column(Integer, nullable=False, default=0)
    response_time_ms = Column(Integer, nullable=True)
    health_message = Column(String(255), nullable=True)

    service = relationship("Service", back_populates="metrics")

    __table_args__ = (
        Index("idx_metrics_service_ts", "service_id", "timestamp"),
    )


class Command(Base):
    __tablename__ = "commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=True)
    action = Column(String(20), nullable=False)  # restart/start/stop/block_ip/restart_agent
    params = Column(Text, nullable=True)         # JSON utk aksi non-service (blokir IP dll.)
    issued_by = Column(String(100), nullable=True)  # username admin yang mengeluarkan
    status = Column(
        Enum("pending", "executing", "success", "failed", name="command_status"),
        nullable=False, default="pending",
    )
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)

    server = relationship("Server", back_populates="commands")
    service = relationship("Service", back_populates="commands")

    __table_args__ = (
        Index("idx_commands_status", "status"),
    )


class SystemSnapshot(Base):
    """Snapshot kinerja perangkat keras + jaringan (dilaporkan agent tiap siklus)."""

    __tablename__ = "sys_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    cpu = Column(Float, nullable=False, default=0)
    load1 = Column(Float, nullable=True)
    load5 = Column(Float, nullable=True)
    load15 = Column(Float, nullable=True)
    mem_total = Column(BigInteger, nullable=False, default=0)
    mem_used = Column(BigInteger, nullable=False, default=0)
    mem_avail = Column(BigInteger, nullable=False, default=0)
    swap_total = Column(BigInteger, nullable=False, default=0)
    swap_used = Column(BigInteger, nullable=False, default=0)
    procs = Column(Integer, nullable=True)
    uptime_secs = Column(BigInteger, nullable=True)
    disks = Column(Text, nullable=True)  # JSON: [{"mount","type","total","used","pct"}]
    net = Column(Text, nullable=True)    # JSON: [{"iface","rx","tx","rx_rate","tx_rate","is_up"}]

    __table_args__ = (
        Index("idx_sys_snapshots_server_ts", "server_id", "timestamp"),
    )


class SysSnapshotHour(Base):
    """Rollup per jam kinerja sistem per server (retensi panjang, 90 hari).

    Disi idempotent dari sys_snapshots untuk jam yang sudah selesai; grafik
    rentang panjang (>24 jam) mengambil dari tabel ini sehingga ramah disk.
    """

    __tablename__ = "sys_snapshots_hourly"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    bucket = Column(DateTime, nullable=False)          # awal jam (UTC)
    samples = Column(Integer, nullable=False, default=0)
    cpu_avg = Column(Float, nullable=False, default=0)
    cpu_max = Column(Float, nullable=False, default=0)
    load1_avg = Column(Float, nullable=True)
    load5_avg = Column(Float, nullable=True)
    load15_avg = Column(Float, nullable=True)
    mem_total = Column(BigInteger, nullable=False, default=0)
    mem_used_avg = Column(BigInteger, nullable=False, default=0)
    mem_avail_avg = Column(BigInteger, nullable=False, default=0)
    swap_total = Column(BigInteger, nullable=False, default=0)
    swap_used_avg = Column(BigInteger, nullable=False, default=0)
    procs_avg = Column(Integer, nullable=True)
    disk_max_pct = Column(Float, nullable=True)         # maks pct disk pada jam itu

    __table_args__ = (
        Index("uk_sys_hour_server_bucket", "server_id", "bucket", unique=True),
    )


class ServerExtras(Base):
    """Data berubah-sedikit per server: kernel, unit layanan aktif, daftar akun."""

    __tablename__ = "server_extras"

    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True)
    kernel = Column(String(100), nullable=True)
    os_label = Column(String(120), nullable=True)   # nama distro + versi (mis. "Ubuntu 22.04.3 LTS")
    arch = Column(String(24), nullable=True)        # arsitektur (mis. x86_64, aarch64)
    agent_version = Column(String(16), nullable=True)  # versi agen yang melapor (mis. "3.4")
    units = Column(Text, nullable=True)    # JSON: ["sshd","mariadb",...]
    accounts = Column(Text, nullable=True) # JSON: [{"user","uid","shell","last_login","sessions"}]
    apt_upgradable = Column(Integer, nullable=True)      # jumlah paket OS yang dapat di-upgrade
    apt_last_update = Column(DateTime, nullable=True)    # kapan apt-get update terakhir di jalankan (per mtime list)
    apt_packages = Column(Text, nullable=True)           # JSON: daftar nama paket yang bisa di-upgrade
    security = Column(Text, nullable=True)               # JSON: ringkasan keamanan auth.log (brute force dll.)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ServerProblem(Base):
    """Masalah terpantau per server (mirip problem list Zabbix).

    Satu baris per masalah (key) yang sedang/ pernah terbuka. resolved_at tidak
    kosong menandakan masalah sudah teratasi (riwayat tetap tersimpan).
    """

    __tablename__ = "server_problems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(160), nullable=False)          # id masalah (mis. service_down:sshd)
    severity = Column(String(10), nullable=False)      # info | warning | danger
    message = Column(String(255), nullable=False)
    tip = Column(String(500), nullable=True)
    started_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)      # None = masih terbuka
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)  # diakui manusia (popup DANGER)
    acknowledged_by = Column(String(100), nullable=True)
    last_active_at = Column(DateTime, nullable=True)   # deteksi/kejadian terakhir (utk jendela tenang)
    resolved_note = Column(String(30), nullable=True)  # 'auto' = ditutup otomatis (tenang)

    __table_args__ = (
        Index("idx_problems_open", "server_id", "resolved_at"),
    )


class LogRequest(Base):
    """Permintaan tampil log layanan klien (dieksekusi agent, hasil dikembalikan)."""

    __tablename__ = "log_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    unit = Column(String(100), nullable=False)
    lines = Column(Integer, nullable=False, default=200)
    detail = Column(String(128), nullable=True)   # ekstra untuk unit khusus (mis. nama user)
    status = Column(
        Enum("pending", "executing", "success", "failed", name="log_request_status"),
        nullable=False, default="pending",
    )
    result = Column(MEDIUMTEXT, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        # Poll agen & cek busy umumnya: server_id → status → urutan pembuatan
        Index("idx_log_requests_server_status", "server_id", "status", "created_at"),
    )


class AuditLog(Base):
    """Jejak aksi admin terhadap sistem (siapa, kapan, aksi apa, target, hasil)."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    target = Column(String(255), nullable=True)
    result = Column(String(500), nullable=True)
    meta = Column(Text, nullable=True)          # JSON tambahan (opsional)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_created", "created_at"),
        Index("idx_audit_username", "username"),
    )


class AppSession(Base):
    """Sesi login persisten di DB (aman terhadap restart server).

    Bukan cookie-session: server hanya menyimpan token acak di cookie, data
    sesi (user, masa berlaku) dicatat di DB sehingga bisa dicabut per-sesi.
    """

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sid = Column(String(64), nullable=False, unique=True)
    user_id = Column(INTEGER_UNSIGNED, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class LoginAttempt(Base):
    """Penghitung gagal login per IP (rate-limit, di DB agar persisten)."""

    __tablename__ = "login_attempts"

    ip_address = Column(String(45), primary_key=True)
    fails = Column(Integer, nullable=False, default=0)
    lock_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)