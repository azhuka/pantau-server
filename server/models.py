import json
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

    id = Column(INTEGER_UNSIGNED, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="viewer")  # master_admin | operator | viewer
    is_active = Column(SmallInteger, nullable=False, default=1)   # 1=aktif, 0=nonaktif
    password_changed_at = Column(DateTime, nullable=True)         # waktu terakhir ganti password
    last_login_at = Column(DateTime, nullable=True)               # waktu login terakhir
    last_login_ip = Column(String(45), nullable=True)             # IP asal login terakhir
    totp_secret = Column(String(64), nullable=True)               # Base32 TOTP secret key
    totp_enabled = Column(SmallInteger, nullable=False, default=0)# 1=aktif, 0=nonaktif
    recovery_codes = Column(Text, nullable=True)                  # JSON list SHA-256 backup codes
    permissions = Column(Text, nullable=True)                     # JSON dict granular permissions (operator)
    created_at = Column(DateTime, default=datetime.utcnow)

    def is_master_admin(self) -> bool:
        return self.role in ("master_admin", "admin")

    def is_operator(self) -> bool:
        return self.role == "operator"

    def is_viewer(self) -> bool:
        return self.role == "viewer"

    def role_display(self) -> str:
        if self.is_master_admin():
            return "Master Admin"
        if self.is_operator():
            return "Operator"
        return "Viewer"

    def get_permissions(self) -> dict:
        if self.is_master_admin():
            return {
                "can_terminal": True,
                "can_file_manager": True,
                "can_services": True,
                "can_processes": True,
                "can_firewall": True,
                "can_users_sys": True,
                "can_cron": True,
                "can_ssl": True,
                "can_server_control": True,
                "can_apt": True,
                "can_ota": True,
                "can_manage_servers": True,
                "can_audit": True,
                "can_manage_users": True,
                "can_manage_viewers": True,
                "can_probing": True,
            }
        if self.is_viewer():
            return {}
        if not self.permissions:
            return {}
        try:
            return json.loads(self.permissions)
        except Exception:
            return {}

    def has_perm(self, perm: str) -> bool:
        if not self.is_active:
            return False
        if self.is_master_admin():
            return True
        if self.is_viewer():
            return False
        perms = self.get_permissions()
        if perm == "can_manage_viewers" and perms.get("can_manage_users"):
            return True
        return bool(perms.get(perm, False))



class Server(Base):
    __tablename__ = "servers"

    id = Column(INTEGER_UNSIGNED, primary_key=True, autoincrement=True)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    # Menyimpan sha256(key) berprefix "sha256:" agar raw key tidak bocor bila DB diretas
    api_key = Column(String(80), nullable=False, unique=True)
    is_active = Column(SmallInteger, nullable=False, default=1)
    is_maintenance = Column(SmallInteger, nullable=False, default=0)
    maintenance_until = Column(DateTime, nullable=True)
    maintenance_reason = Column(String(255), nullable=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    group_name = Column(String(64), nullable=True, default=None, index=True)
    tier = Column(SmallInteger, nullable=False, default=2)  # 1=Tier 1 (Kritis), 2=Tier 2 (Pendukung), 3=Tier 3 (Eksperimen/Clone)
    tags = Column(String(255), nullable=True)
    custom_thresholds = Column(Text, nullable=True)  # JSON: ambang batas CPU, RAM, Disk per-server
    is_proxmox_ha = Column(SmallInteger, nullable=False, default=0)
    platform_override = Column(String(20), nullable=True, default=None)  # 'baremetal', 'vm', 'lxc', atau None/auto
    is_isolated_net = Column(SmallInteger, nullable=False, default=0)    # 1=jaringan lokal/terisolasi, 0=standar
    allow_web_terminal = Column(SmallInteger, nullable=False, default=0) # 1=izinkan terminal root web, 0=blokir
    notes = Column(Text, nullable=True)                                  # Deskripsi/catatan operasional server

    services = relationship("Service", back_populates="server", cascade="all, delete-orphan")
    commands = relationship("Command", back_populates="server", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    service_name = Column(String(100), nullable=False)
    port = Column(Integer, nullable=False)
    process_name = Column(String(100), nullable=False)
    is_core = Column(SmallInteger, nullable=False, default=1)  # 1=Layanan Utama (Core), 0=Layanan Pendukung (Secondary)
    is_ignored = Column(SmallInteger, nullable=False, default=0)
    ignored_until = Column(DateTime, nullable=True)
    ignored_by = Column(String(100), nullable=True)
    ignored_reason = Column(String(255), nullable=True)
    ignore_mode = Column(String(20), nullable=True, default="permanent")

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
    accounts = Column(MEDIUMTEXT, nullable=True) # JSON: [{"user","uid","gid","group","groups","home","shell","last_login","sessions"}]
    system_groups = Column(MEDIUMTEXT, nullable=True) # JSON: [{"group","gid","is_system","is_privileged","members","member_count"}]
    apt_upgradable = Column(Integer, nullable=True)      # jumlah paket OS yang dapat di-upgrade
    apt_last_update = Column(DateTime, nullable=True)    # kapan apt-get update terakhir di jalankan (per mtime list)
    apt_packages = Column(Text, nullable=True)           # JSON: daftar nama paket yang bisa di-upgrade
    security = Column(Text, nullable=True)               # JSON: ringkasan keamanan auth.log (brute force dll.)
    top_procs = Column(Text, nullable=True)              # JSON: {"cpu": [...], "mem": [...]} proses teratas
    cron_jobs = Column(Text, nullable=True)              # JSON: daftar tugas terjadwal (crontab & systemd timers)
    firewall = Column(Text, nullable=True)               # JSON: status firewall (ufw/iptables) & rules
    listening_ports = Column(Text, nullable=True)        # JSON: daftar port listening & proses (ss -tulpn)
    ssl_certs = Column(Text, nullable=True)              # JSON: sertifikat SSL/TLS & masa kedaluwarsa
    system_logs = Column(Text, nullable=True)            # JSON: log kegagalan sistem penting (journalctl err/crit)
    kernel_events = Column(MEDIUMTEXT, nullable=True)    # JSON: event fatal kernel (OOM killer, disk I/O error, segfault, panic)
    hardware_specs = Column(Text, nullable=True)         # JSON: spesifikasi hardware & platform server (CPU, RAM, Disks, Board, BIOS)
    installed_packages = Column(MEDIUMTEXT, nullable=True) # JSON: inventaris paket sistem terpasang (dpkg-query)
    systemd_units = Column(MEDIUMTEXT, nullable=True)      # JSON: inventaris unit service systemd (systemctl list-units)
    backup_status = Column(MEDIUMTEXT, nullable=True)      # JSON: telemetri status berkas cadangan database & sistem
    updated_at = Column(DateTime, default=datetime.utcnow)


class ProbeTarget(Base):
    """Target Synthetic Probing (HTTP/HTTPS, ICMP Ping, TCP Port).

    Dapat ditautkan ke salah satu server yang terdaftar di Pantau atau berdiri sendiri
    sebagai endpoint independen (misal: router, switch, API gateway, atau layanan cloud).
    """

    __tablename__ = "probe_targets"

    id = Column(INTEGER_UNSIGNED, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)                    # Nama ramah manusia, mis. "Portal Web Utama"
    probe_type = Column(String(20), nullable=False)               # 'http', 'https', 'ping', 'tcp'
    target = Column(String(255), nullable=False)                  # URL (http/https) atau Host/IP (ping/tcp)
    port = Column(Integer, nullable=True)                         # Port target khusus TCP (mis. 3306, 5432, 22)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True)
    tier = Column(SmallInteger, nullable=False, default=2)        # 1=Tier 1 (Kritis / Vital), 2=Tier 2 (Standar), 3=Tier 3 (Non-Kritis)

    interval_seconds = Column(Integer, nullable=False, default=60)# Frekuensi pengecekan (detik, default 60s)
    timeout_seconds = Column(Integer, nullable=False, default=5)  # Batas waktu respons (detik, default 5s)

    # Opsi Khusus HTTP / HTTPS
    http_method = Column(String(10), nullable=False, default="GET")# GET, POST, HEAD
    http_headers = Column(Text, nullable=True)                    # JSON string: {"Authorization": "..."}
    http_body = Column(Text, nullable=True)                       # Payload untuk POST/PUT
    expected_status = Column(String(50), nullable=True, default="200") # Format "200" atau "200,201,204" atau "2xx"
    keyword_match = Column(String(255), nullable=True)            # String yang wajib ada dalam response body
    ssl_verify = Column(SmallInteger, nullable=False, default=1)  # 1=validasi SSL, 0=izinkan self-signed
    ssl_expiry_threshold_days = Column(Integer, nullable=False, default=14) # Peringatan jika SSL tersisa < N hari

    # Ambang Batas Kinerja & Anti-Flapping
    latency_threshold_ms = Column(Integer, nullable=True, default=2000) # Batas latensi dianggap degraded (ms)
    consecutive_threshold = Column(Integer, nullable=False, default=2)  # Kegagalan berturut-turut sebelum alarm DOWN

    # Status Operasional & Hasil Telemetri Terkini
    is_active = Column(SmallInteger, nullable=False, default=1)   # 1=aktif berjalan, 0=dijeda (paused)
    status = Column(String(20), nullable=False, default="unknown")# 'up', 'down', 'degraded', 'paused', 'unknown'
    last_checked_at = Column(DateTime, nullable=True)
    last_latency_ms = Column(Float, nullable=True)
    last_status_code = Column(Integer, nullable=True)
    last_error = Column(String(255), nullable=True)
    ssl_expires_at = Column(DateTime, nullable=True)
    ssl_days_remaining = Column(Integer, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    consecutive_successes = Column(Integer, nullable=False, default=0)
    uptime_24h = Column(Float, nullable=False, default=100.0)
    uptime_30d = Column(Float, nullable=False, default=100.0)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)

    server = relationship("Server", backref="probes")
    logs = relationship("ProbeLog", back_populates="probe", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_probe_active_next", "is_active", "last_checked_at"),
        Index("idx_probe_type_status", "probe_type", "status"),
    )


class ProbeLog(Base):
    """Riwayat hasil eksekusi synthetic probing untuk grafik latensi & kalkulasi SLA."""

    __tablename__ = "probe_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    probe_id = Column(INTEGER_UNSIGNED, ForeignKey("probe_targets.id", ondelete="CASCADE"), nullable=False, index=True)
    checked_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    status = Column(String(20), nullable=False)                   # 'up', 'down', 'degraded'
    latency_ms = Column(Float, nullable=True)
    status_code = Column(Integer, nullable=True)
    error_message = Column(String(255), nullable=True)

    probe = relationship("ProbeTarget", back_populates="logs")

    __table_args__ = (
        Index("idx_probe_logs_probe_time", "probe_id", "checked_at"),
    )


class ServerProblem(Base):
    """Masalah terpantau per server (mirip problem list Zabbix).

    Satu baris per masalah (key) yang sedang/ pernah terbuka. resolved_at tidak
    kosong menandakan masalah sudah teratasi (riwayat tetap tersimpan).
    """

    __tablename__ = "server_problems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=True, index=True)
    probe_id = Column(INTEGER_UNSIGNED, ForeignKey("probe_targets.id", ondelete="CASCADE"), nullable=True, index=True)
    key = Column(String(160), nullable=False)          # id masalah (mis. service_down:sshd, probe_down:1)
    severity = Column(String(10), nullable=False)      # info | warning | danger
    message = Column(String(255), nullable=False)
    tip = Column(String(500), nullable=True)
    started_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)      # None = masih terbuka
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)  # ditangani operator (popup DANGER)
    acknowledged_by = Column(String(100), nullable=True)
    last_active_at = Column(DateTime, nullable=True)   # deteksi/kejadian terakhir (utk jendela tenang)
    resolved_note = Column(String(100), nullable=True) # 'auto' = ditutup otomatis (tenang)
    is_ignored = Column(SmallInteger, default=0)       # 1 = masalah diabaikan (tidak memicu alarm/banner)
    ignored_until = Column(DateTime, nullable=True)    # batas waktu abaikan (None jika permanen / tidak diabaikan)
    ignored_by = Column(String(100), nullable=True)    # user yang mengabaikan
    ignored_reason = Column(String(255), nullable=True)# catatan alasan pengabaian
    ignore_mode = Column(String(20), nullable=True, default="permanent")
    context = Column(Text, nullable=True)              # JSON data konteks diagnostik / log snapshot saat insiden terjadi

    __table_args__ = (
        Index("idx_problems_open", "server_id", "resolved_at"),
        Index("idx_problems_probe", "probe_id", "resolved_at"),
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
    # Jalur interaktif: jawaban admin (mis. "N\n" saat dpkg menanyakan file
    # konfigurasi) disimpan di sini lalu diambil agent lewat /api/logs/{id}/input.
    input_data = Column(String(500), nullable=True)
    input_at = Column(DateTime, nullable=True)
    # Antrean mentah ketikan untuk sesi Terminal Bawaan (shell pty). Berbeda
    # dengan input_data yang "satu-slot cukup" untuk jawaban dpkg, shell
    # mengirim banyak byte kecil berurutan (tiap tombol) sehingga harus
    # ditumpuk, kalau tidak ada ketikan yang saling menimpa.
    input_queue = Column(Text, nullable=True)
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
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True)
    username = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    target = Column(String(255), nullable=True)
    result = Column(String(500), nullable=True)
    meta = Column(Text, nullable=True)          # JSON tambahan (opsional)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_created", "created_at"),
        Index("idx_audit_username", "username"),
        Index("idx_audit_server", "server_id"),
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


class SystemSetting(Base):
    """Pengaturan sistem dan ambang batas global (kunci-nilai persisten)."""

    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MaintenanceWindow(Base):
    """Jendela Pemeliharaan Terjadwal (Scheduled Maintenance Windows).

    Digunakan untuk merencanakan periode pemeliharaan sistem terencana (one-time atau recurring),
    secara otomatis menekan eskalasi alarm kritis, menyematkan lencana status pemeliharaan,
    dan memulihkan pengawasan normal saat jendela berakhir.
    """

    __tablename__ = "maintenance_windows"

    id = Column(INTEGER_UNSIGNED, primary_key=True, autoincrement=True)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    scope_type = Column(String(30), nullable=False, default="server")  # 'all', 'group', 'server'
    server_id = Column(INTEGER_UNSIGNED, ForeignKey("servers.id", ondelete="CASCADE"), nullable=True, index=True)
    server_ids = Column(Text, nullable=True)  # Comma-separated server IDs, e.g. '1,4,7' (Multi-Select Server)
    server_group = Column(String(64), nullable=True, index=True)

    schedule_type = Column(String(30), nullable=False, default="once")  # 'once', 'daily', 'weekly'
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)

    repeat_days = Column(String(50), nullable=True)      # 'mon,tue,wed,thu,fri,sat,sun'
    repeat_time_start = Column(String(10), nullable=True) # 'HH:MM'
    repeat_time_end = Column(String(10), nullable=True)   # 'HH:MM'

    is_active = Column(SmallInteger, nullable=False, default=1, index=True)
    status = Column(String(30), nullable=False, default="scheduled")  # 'scheduled', 'active', 'completed', 'cancelled'

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(64), nullable=True)

    server = relationship("Server")

    __table_args__ = (
        Index("idx_mw_scope", "scope_type", "server_id", "server_group"),
        Index("idx_mw_time", "is_active", "start_time", "end_time"),
        Index("idx_mw_status", "status"),
    )
