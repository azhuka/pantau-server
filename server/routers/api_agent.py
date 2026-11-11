"""API endpoints for edge agent telemetry, command dispatching, and remote logs execution."""

import json
import logging
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException, Header, Body
from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session

try:
    from config import settings
    from models import (
        AuditLog, Command, LogRequest, Metric, Server, ServerExtras,
        ServerProblem, Service, SysSnapshotHour, SystemSnapshot, User,
    )
    from core.database import get_db
    from core.security import (
        hash_api_key, _agent_ip_tracker, _agent_tracker_lock,
        is_terminal_unlocked, _verify_csrf_header, require_user,
    )
    from core.utils import (
        _clean_str, _clamp_int, _clamp_float, _validate_ip, _is_agent_outdated,
        _clean_result, _clean_terminal, api_key_fingerprint,
    )
    from services.audit_service import _audit, tail_lines
    from services.server_service import _server_stale, _latest_metrics
    from services.problem_service import (
        sync_server_problems, _problem_instances, _build_problem_context, APT_TIP,
    )
    from services.system_service import _get_agent_code_and_sha256, _req_is_shell
except ImportError:
    from server.config import settings
    from server.models import (
        AuditLog, Command, LogRequest, Metric, Server, ServerExtras,
        ServerProblem, Service, SysSnapshotHour, SystemSnapshot, User,
    )
    from server.core.database import get_db
    from server.core.security import (
        hash_api_key, _agent_ip_tracker, _agent_tracker_lock,
        is_terminal_unlocked, _verify_csrf_header, require_user,
    )
    from server.core.utils import (
        _clean_str, _clamp_int, _clamp_float, _validate_ip, _is_agent_outdated,
        _clean_result, _clean_terminal, api_key_fingerprint,
    )
    from server.services.audit_service import _audit, tail_lines
    from server.services.server_service import _server_stale, _latest_metrics
    from server.services.problem_service import (
        sync_server_problems, _problem_instances, _build_problem_context, APT_TIP,
    )
    from server.services.system_service import _get_agent_code_and_sha256, _req_is_shell

logger = logging.getLogger("pantau.api_agent")
router = APIRouter(tags=["agent"])

VALID_UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:+-]{1,100}$")
APT_UNITS = ("APT_UPDATE", "APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE", "APT_FIX", "PKG_UPGRADE", "PKG_CLEAN")
SHELL_UNIT = "SHELL"
INTERACTIVE_UNITS = APT_UNITS + (SHELL_UNIT,)
SHELL_INPUT_MAX = 64 * 1024
SYSLOG_FILE = "/var/log/syslog"
AUTH_FILE = "/var/log/auth.log"
STALE_LOG_SECONDS = 600
APT_STREAM_MAXCHARS = 4_000_000
APT_STREAM_MAXLINES = 120_000
_CLEAN_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f]")

_last_metrics_prune = datetime.utcnow()
_prune_lock = threading.Lock()

PKG_SERVICE_MAP = {
    "openssh-server": "sshd",
    "openssh-client": "sshd",
    "nginx": "nginx",
    "nginx-core": "nginx",
    "mysql-server": "mysql",
    "mysql-client": "mysql",
    "mariadb-server": "mysql",
    "mariadb-client": "mysql",
    "mongodb-org-server": "mongod",
    "mongodb-org": "mongod",
    "postgresql": "postgresql",
    "redis-server": "redis",
    "docker.io": "docker",
    "docker-ce": "docker",
    "cockpit": "cockpit",
    "cockpit-ws": "cockpit-tls",
    "uvicorn": "uvicorn",
    "python3-uvicorn": "uvicorn",
    "zabbix-agent2": "zabbix_agent2",
    "google-chrome-stable": "chrome",
    "postfix": "postfix",
    "systemd": "systemd-resolve",
    "systemd-resolved": "systemd-resolve",
    "bind9": "named",
    "inetutils-syslogd": "syslog",
    "rsyslog": "syslog",
    "curl": "curl",
    "nodejs": "node",
    "nftables": "nft",
    "ufw": "ufw",
}


def _safe_json_get(raw: str | None, key: str, default=None):
    if not raw:
        return default
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data.get(key, default) if isinstance(data, dict) else default
    except Exception:
        return default


def _safe_json_loads(raw: str | None, default=None):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _normalize_unit_for_systemctl(name: str | None) -> str | None:
    if not name:
        return name
    mapping = {
        "zabbix_agent2": "zabbix-agent2",
        "zabbix_agent": "zabbix-agent",
        "sshd": "ssh",
        "mysqld": "mariadb",
        "mariadbd": "mariadb",
    }
    return mapping.get(name, name.replace("_", "-") if name.startswith("zabbix_") else name)


def _parse_iso_dt(value, default=None):
    """Parse ISO-8601 (opsional akhiran Z/offset) ke datetime naive UTC; fallback default."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return default
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return default


def _apt_pkg_services(pkg_name: str, services: list[str]) -> list[str]:
    """Service aktif (dari service_name) yang terdampak upgrade packages."""
    low = (pkg_name or "").lower()
    hits = set()
    mapped = PKG_SERVICE_MAP.get(low)
    if mapped:
        hits.add(mapped)
    for s in services:
        if not s:
            continue
        ls = s.lower()
        if ls == low:
            hits.add(s)
        elif len(ls) >= 3 and (low.startswith(ls) or ls in low.split("-")):
            hits.add(s)
    return sorted(hits)


def _sanitize_disk_list(raw) -> str | None:
    """Sanitasi list disk dari agen — validasi field dan tipe data."""
    if not isinstance(raw, list):
        return None
    cleaned = []
    for d in raw[:100]:
        if not isinstance(d, dict):
            continue
        cleaned.append({
            "mount": _clean_str(d.get("mount"), "", 255),
            "type": _clean_str(d.get("type"), "", 32),
            "total": _clamp_int(d.get("total"), 0, 0, 2 ** 63 - 1),
            "used": _clamp_int(d.get("used"), 0, 0, 2 ** 63 - 1),
            "pct": _clamp_float(d.get("pct"), 0.0, 0.0, 100.0),
            "is_ro": bool(d.get("is_ro")),
            "read_kb_s": _clamp_float(d.get("read_kb_s"), 0.0, 0.0, 1e9),
            "write_kb_s": _clamp_float(d.get("write_kb_s"), 0.0, 0.0, 1e9),
            "read_iops": _clamp_float(d.get("read_iops"), 0.0, 0.0, 1e7),
            "write_iops": _clamp_float(d.get("write_iops"), 0.0, 0.0, 1e7),
            "io_util": _clamp_float(d.get("io_util"), 0.0, 0.0, 100.0),
        })
    return json.dumps(cleaned) if cleaned else None


def _sanitize_net_list(raw) -> str | None:
    """Sanitasi list interface jaringan dari agen — validasi field dan tipe data."""
    if not isinstance(raw, list):
        return None
    cleaned = []
    for n in raw[:50]:
        if not isinstance(n, dict):
            continue
        raw_ips = n.get("ip_addrs") or []
        ip_addrs = [str(ip)[:50] for ip in raw_ips[:8] if isinstance(ip, str)]
        cleaned.append({
            "iface": _clean_str(n.get("iface"), "", 32),
            "rx": _clamp_int(n.get("rx"), 0, 0, 2 ** 63 - 1),
            "tx": _clamp_int(n.get("tx"), 0, 0, 2 ** 63 - 1),
            "rx_rate": _clamp_float(n.get("rx_rate"), 0.0, 0.0, 1e12),
            "tx_rate": _clamp_float(n.get("tx_rate"), 0.0, 0.0, 1e12),
            "is_up": bool(n.get("is_up")),
            "ip_addrs": ip_addrs,
            "mac": _clean_str(n.get("mac"), "", 32),
            "speed": _clean_str(n.get("speed"), "", 32),
        })
    return json.dumps(cleaned) if cleaned else None


def _rollup_sys_hours(db: Session, server_id: int):
    """Materialisasikan rollup per jam dari sys_snapshots (idempotent)."""
    global _last_metrics_prune
    now = datetime.utcnow()
    this_hour = now.replace(minute=0, second=0, microsecond=0)

    with _prune_lock:
        if now - _last_metrics_prune > timedelta(hours=24):
            mcut = now - timedelta(days=7)
            db.query(Metric).filter(Metric.timestamp < mcut).delete(synchronize_session=False)
            _last_metrics_prune = now

    latest = (
        db.query(func.max(SysSnapshotHour.bucket))
        .filter(SysSnapshotHour.server_id == server_id)
        .scalar()
    )
    bucket = latest + timedelta(hours=1) if latest else this_hour - timedelta(hours=24)
    while bucket < this_hour:
        nxt = bucket + timedelta(hours=1)
        agg = db.query(
            func.count(SystemSnapshot.id),
            func.avg(SystemSnapshot.cpu),
            func.max(SystemSnapshot.cpu),
            func.avg(SystemSnapshot.load1),
            func.avg(SystemSnapshot.load5),
            func.avg(SystemSnapshot.load15),
            func.max(SystemSnapshot.mem_total),
            func.avg(SystemSnapshot.mem_used),
            func.avg(SystemSnapshot.mem_avail),
            func.max(SystemSnapshot.swap_total),
            func.avg(SystemSnapshot.swap_used),
            func.avg(SystemSnapshot.procs),
        ).filter(
            SystemSnapshot.server_id == server_id,
            SystemSnapshot.timestamp >= bucket,
            SystemSnapshot.timestamp < nxt,
        ).one()
        if agg[0]:
            last_snap = (
                db.query(SystemSnapshot.disks)
                .filter(
                    SystemSnapshot.server_id == server_id,
                    SystemSnapshot.timestamp >= bucket,
                    SystemSnapshot.timestamp < nxt,
                )
                .order_by(desc(SystemSnapshot.timestamp))
                .first()
            )
            disk_max_pct = None
            if last_snap and last_snap.disks:
                try:
                    disks = json.loads(last_snap.disks)
                    disk_max_pct = max(
                        (d.get("pct") or 0) for d in disks if isinstance(d, dict)
                    ) or None
                except (TypeError, ValueError):
                    disk_max_pct = None
            db.add(SysSnapshotHour(
                server_id=server_id, bucket=bucket, samples=agg[0],
                cpu_avg=agg[1] or 0.0, cpu_max=agg[2] or 0.0,
                load1_avg=agg[3], load5_avg=agg[4], load15_avg=agg[5],
                mem_total=agg[6] or 0, mem_used_avg=agg[7] or 0,
                mem_avail_avg=agg[8] or 0, swap_total=agg[9] or 0,
                swap_used_avg=agg[10] or 0,
                procs_avg=int(agg[11]) if agg[11] is not None else None,
                disk_max_pct=disk_max_pct,
            ))
        bucket = nxt

    prune_h = now - timedelta(days=90)
    db.query(SysSnapshotHour).filter(
        SysSnapshotHour.server_id == server_id,
        SysSnapshotHour.bucket < prune_h,
    ).delete(synchronize_session=False)


def _expire_stale_logs(db: Session, server_id: int):
    """Expire permintaan log yang menggantung terlalu lama (agent offline)."""
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_LOG_SECONDS)
    stale = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == server_id,
            LogRequest.status.in_(["pending", "executing"]),
            LogRequest.unit.notin_(INTERACTIVE_UNITS),
            LogRequest.created_at < cutoff,
        )
        .all()
    )
    for r in stale:
        r.status = "failed"
        r.result = "timeout: agen tidak merespons"
        r.updated_at = datetime.utcnow()

    # Expire sesi SHELL yang sudah mati / agen tidak lagi polling input
    shell_cutoff = datetime.utcnow() - timedelta(seconds=25)
    stale_shells = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == server_id,
            LogRequest.unit == SHELL_UNIT,
            LogRequest.status.in_(["pending", "executing"]),
            (LogRequest.updated_at < shell_cutoff) | (LogRequest.created_at < shell_cutoff),
        )
        .all()
    )
    for r in stale_shells:
        r.status = "failed"
        r.result = (r.result or "").strip() + "\n[sesi shell terputus: tidak ada respons dari agen]"
        r.updated_at = datetime.utcnow()

    if stale or stale_shells:
        db.commit()


def _journal_tail(unit: str, lines: int) -> list:
    try:
        p = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return [f"[gagal membaca journal: {e}]"]
    out = p.stdout.rstrip().splitlines()
    if not out:
        msg = p.stderr.strip() or f"tidak ada entri untuk unit {unit}"
        return [f"[{msg}]"]
    return out[-lines:]


def _journal_boot_tail(lines: int) -> list:
    try:
        p = subprocess.run(
            ["journalctl", "-b", "-n", str(lines), "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return [f"[gagal membaca journal: {e}]"]
    return p.stdout.rstrip().splitlines()[-lines:] or ["[journal boot kosong]"]


# ===========================================================================
# 1. POST /api/report (Agent Telemetry Ingestion)
# ===========================================================================
@router.post("/api/report")
def agent_report(
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        logger.warning("[AUTH] /api/report 401: fp=%s", api_key_fingerprint(x_api_key))
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Pelacakan IP pelapor untuk mendeteksi konflik duplikasi agen / klon VM
    client_ip = request.client.host if request.client else ""
    body_ip = _clean_str(body.get("ip_address"), "", 45)
    reporter_ip = body_ip or client_ip or "unknown"
    now_epoch = time.time()

    with _agent_tracker_lock:
        server_ips = _agent_ip_tracker.setdefault(server.id, {})
        server_ips[reporter_ip] = now_epoch
        # Bersihkan IP yang tidak melapor lagi > 120 detik
        stale_ips = [ip for ip, ts in list(server_ips.items()) if (now_epoch - ts) > 120]
        for ip in stale_ips:
            del server_ips[ip]
        has_agent_conflict = len(server_ips) > 1
        active_conflict_ips = sorted(server_ips.keys()) if has_agent_conflict else []

    if has_agent_conflict:
        logger.warning(
            "[AGENT CONFLICT] Server ID %s (%s) menerima laporan simultan dari beberapa IP: %s",
            server.id, server.hostname, active_conflict_ips
        )

    server.hostname = _clean_str(body.get("hostname", server.hostname), server.hostname, 255)
    # Jangan flip-flop ip_address jika sedang konflik multi-IP
    if not has_agent_conflict or not server.ip_address:
        server.ip_address = _clean_str(body.get("ip_address", server.ip_address), server.ip_address, 45)[:45]
    server.last_seen = datetime.utcnow()
    db.flush()

    reported_service_ids = set()

    services = body.get("services")
    if not isinstance(services, list):
        services = []

    for svc in services:
        if not isinstance(svc, dict):
            continue
        service_name = _clean_str(svc.get("service_name"), "", 100)
        port = _clamp_int(svc.get("port"), 0, 1, 65535)
        if not service_name or not (1 <= port <= 65535):
            continue
        process_name = _clean_str(svc.get("process_name"), "", 100)
        low_svc = service_name.lower()
        low_proc = process_name.lower() if process_name else ""
        if any(ign in low_svc or ign in low_proc for ign in ("chrome", "chromedriver", "chromium", "selenium", "playwright", "pytest")):
            continue
        status = svc.get("status", "down")
        if status not in ("up", "down"):
            status = "down"
        active_connections = _clamp_int(svc.get("active_connections"), 0, 0, 10 ** 9)
        response_time_ms = _clamp_int(svc.get("response_time_ms"), None, 0, 10 ** 6)
        health_message = _clean_str(svc.get("health_message"), "", 255)

        service = (
            db.query(Service)
            .filter(Service.server_id == server.id, Service.service_name == service_name)
            .first()
        )
        if not service and port > 0:
            # Bila port sudah ada di server ini (mis. smtpd vs master), pakai service yang ada agar tidak duplikat
            service = (
                db.query(Service)
                .filter(Service.server_id == server.id, Service.port == port)
                .first()
            )
        if not service:
            service = Service(
                server_id=server.id, service_name=service_name,
                port=port, process_name=process_name,
            )
            db.add(service)
            db.flush()
        else:
            service.port = port
            service.process_name = process_name

        reported_service_ids.add(service.id)

        # Cek apakah ada perintah stop yang sedang pending/executing atau service sengaja dimatikan operator
        has_stop_in_flight = db.query(Command).filter(
            Command.server_id == server.id,
            Command.service_id == service.id,
            Command.action.in_(["stop", "service_stop"]),
            Command.status.in_(["pending", "executing"]),
        ).first() is not None
        is_op_stopped = bool(service.ignored_reason and "DIMATIKAN OLEH OPERATOR" in service.ignored_reason)

        if (has_stop_in_flight or is_op_stopped) and status == "up":
            status = "down"
            health_message = service.ignored_reason or "Service dihentikan oleh operator"

        # Ambil status metrik terakhir sebelum menambahkan metrik baru
        last_m = (
            db.query(Metric).filter(Metric.service_id == service.id)
            .order_by(desc(Metric.timestamp)).first()
        )
        prev_status = last_m.status if last_m else None

        db.add(Metric(
            service_id=service.id,
            status=status,
            active_connections=active_connections if status == "up" else 0,
            response_time_ms=response_time_ms if status == "up" else None,
            health_message=health_message or None,
        ))

        # Deteksi pemulihan / status aktif service
        if status == "up":
            # 1. Tutup masalah service_down seketika jika masih terbuka
            open_probs = db.query(ServerProblem).filter(
                ServerProblem.server_id == server.id,
                ServerProblem.key == f"service_down:{service.service_name}",
                ServerProblem.resolved_at.is_(None),
            ).all()
            for op in open_probs:
                op.resolved_at = datetime.utcnow()
                op.updated_at = datetime.utcnow()
                op.resolved_note = "auto"

            # 2. Jika sebelumnya bermasalah (down/offline), evaluasi pengabaian sesuai mode & catat audit
            if prev_status in ("down", "offline", "unknown"):
                svc_mode = getattr(service, "ignore_mode", None)
                if svc_mode == "incident":
                    # Mode insiden: hanya untuk satu insiden saat itu, reset ke normal saat service pulih
                    service.is_ignored = 0
                    service.ignored_until = None
                    service.ignored_reason = None
                    service.ignore_mode = None
                elif svc_mode == "duration":
                    # Mode durasi: jika batas waktu telah habis, kembalikan ke pemantauan normal
                    if not (service.ignored_until and service.ignored_until > datetime.utcnow()):
                        service.is_ignored = 0
                        service.ignored_until = None
                        service.ignored_reason = None
                        service.ignore_mode = None
                elif svc_mode == "permanent":
                    # Mode permanen: TETAP diabaikan (is_ignored = 1), tidak di-reset saat service pulih!
                    pass
                else:
                    if service.ignored_until and service.ignored_until <= datetime.utcnow():
                        service.is_ignored = 0
                        service.ignored_until = None
                        service.ignored_reason = None
                        service.ignore_mode = None

                try:
                    _audit(
                        db, "sistem", "service_recovered",
                        f"{server.hostname}:{service.service_name}",
                        "kembali aktif (pulih)",
                        server_id=server.id,
                    )
                except Exception as e:
                    logger.warning("[agent_report] Gagal catat audit service_recovered: %s", e)

    # Service yang sudah terdaftar tapi tidak dilaporkan lagi -> tandai down dengan redam flapping
    existing = (
        db.query(Service).filter(Service.server_id == server.id).all()
    )
    for svc in existing:
        if svc.id in reported_service_ids:
            continue
        # Cek status terakhir, jangan insert duplikat kalau sudah down
        last = (
            db.query(Metric).filter(Metric.service_id == svc.id)
            .order_by(desc(Metric.timestamp)).first()
        )
        if not last or last.status == "up":
            # 1. Bila terjadi konflik agen (multi-IP), tahan status DOWN jika host lain baru saja melapor UP
            if has_agent_conflict and last and last.status == "up":
                continue
            # 2. Transisi status seketika tanpa jeda agar kejadian eksternal (service crash / dimatikan) langsung terdeteksi
            is_op_shutdown = bool(svc.ignored_reason and "DIMATIKAN OLEH OPERATOR" in svc.ignored_reason)
            db.add(Metric(
                service_id=svc.id,
                status="down",
                active_connections=0,
                health_message="Service tidak terdeteksi listening pada port atau proses tidak berjalan" if not is_op_shutdown else svc.ignored_reason,
            ))

    db.commit()

    # ------------------------------------------------------------------
    # Data kinerja hardware/jaringan + akun + unit service (opsional)
    # ------------------------------------------------------------------
    sysd = body.get("system")
    if isinstance(sysd, dict):
        snap = SystemSnapshot(
            server_id=server.id,
            cpu=_clamp_float(sysd.get("cpu"), 0, 0, 100),
            load1=_clamp_float(sysd.get("load1"), 0, 0, 10 ** 9),
            load5=_clamp_float(sysd.get("load5"), 0, 0, 10 ** 9),
            load15=_clamp_float(sysd.get("load15"), 0, 0, 10 ** 9),
            mem_total=_clamp_int(sysd.get("mem_total"), 0, 0, 2 ** 63 - 1),
            mem_used=_clamp_int(sysd.get("mem_used"), 0, 0, 2 ** 63 - 1),
            mem_avail=_clamp_int(sysd.get("mem_avail"), 0, 0, 2 ** 63 - 1),
            swap_total=_clamp_int(sysd.get("swap_total"), 0, 0, 2 ** 63 - 1),
            swap_used=_clamp_int(sysd.get("swap_used"), 0, 0, 2 ** 63 - 1),
            procs=_clamp_int(sysd.get("procs"), None, 0, 2 ** 31 - 1),
            uptime_secs=_clamp_int(sysd.get("uptime"), None, 0, 2 ** 63 - 1),
            disks=_sanitize_disk_list(sysd.get("disks")),
            net=_sanitize_net_list(sysd.get("net")),
        )
        db.add(snap)
        # Prune snapshot > 24 jam (hemat disk)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        db.query(SystemSnapshot).filter(
            SystemSnapshot.server_id == server.id,
            SystemSnapshot.timestamp < cutoff,
        ).delete(synchronize_session=False)
        # Materialisasikan rollup per jam (idempotent, hanya jam yang sudah lewat)
        _rollup_sys_hours(db, server.id)

        # Heuristik Deteksi Otomatis Proxmox HA (Auto-Revive Heuristic)
        uptime_val = _clamp_int(sysd.get("uptime"), None, 0, 2 ** 63 - 1)
        if uptime_val is not None and uptime_val < 180 and getattr(server, "is_proxmox_ha", 0) == 0:
            recent_cutoff = datetime.utcnow() - timedelta(seconds=300)
            recent_poweroff = (
                db.query(Command)
                .filter(
                    Command.server_id == server.id,
                    Command.action == "poweroff_host",
                    Command.created_at >= recent_cutoff,
                )
                .order_by(desc(Command.created_at))
                .first()
            )
            if recent_poweroff:
                server.is_proxmox_ha = 1
                try:
                    _audit(
                        db,
                        "sistem",
                        "proxmox_ha_detected",
                        f"{server.hostname} ({server.ip_address})",
                        "Server terproteksi Proxmox HA.",
                        server_id=server.id,
                    )
                except Exception as exc:
                    logger.warning("[agent_report] Gagal catat audit proxmox_ha_detected: %s", exc)
                logger.info(
                    "[PROXMOX HA] Auto-revive terdeteksi pada server ID %s (%s) setelah poweroff (uptime: %ss). Otomatis set is_proxmox_ha=1.",
                    server.id, server.hostname, uptime_val
                )

    # Data berubah-sedikit: kernel, unit aktif, daftar akun
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
    if extras is None:
        extras = ServerExtras(server_id=server.id)
        db.add(extras)
    extras.kernel = _clean_str(body.get("kernel"), None, 100) or None
    extras.os_label = _clean_str(body.get("os_label"), None, 120) or None
    extras.arch = _clean_str(body.get("arch"), None, 24) or None
    extras.agent_version = _clean_str(body.get("agent_version"), None, 16) or None
    if "hardware_specs" in body and isinstance(body.get("hardware_specs"), dict):
        try:
            extras.hardware_specs = json.dumps(body["hardware_specs"])
        except Exception:
            pass

    if isinstance(sysd, dict) and isinstance(sysd.get("top_procs"), dict):
        top_p = sysd["top_procs"]
        clean_top = {"cpu": [], "mem": []}
        for item in (top_p.get("cpu") or [])[:20]:
            if isinstance(item, dict):
                clean_top["cpu"].append({
                    "pid": _clamp_int(item.get("pid"), 0, 0, 2 ** 31 - 1),
                    "user": _clean_str(item.get("user"), "", 32),
                    "comm": _clean_str(item.get("comm"), "", 64),
                    "cpu": _clamp_float(item.get("cpu"), 0.0, 0.0, 1000.0),
                    "mem": _clamp_float(item.get("mem"), 0.0, 0.0, 100.0),
                })
        for item in (top_p.get("mem") or [])[:20]:
            if isinstance(item, dict):
                clean_top["mem"].append({
                    "pid": _clamp_int(item.get("pid"), 0, 0, 2 ** 31 - 1),
                    "user": _clean_str(item.get("user"), "", 32),
                    "comm": _clean_str(item.get("comm"), "", 64),
                    "cpu": _clamp_float(item.get("cpu"), 0.0, 0.0, 1000.0),
                    "mem": _clamp_float(item.get("mem"), 0.0, 0.0, 100.0),
                })
        extras.top_procs = json.dumps(clean_top)

    _VALID_UNIT_RE = re.compile(r'^[A-Za-z0-9@_.\-:]{1,100}$')
    if isinstance(body.get("units"), list):
        clean_units = [
            str(u)[:100] for u in body["units"][:200]
            if isinstance(u, str) and _VALID_UNIT_RE.match(str(u))
        ]
        extras.units = json.dumps(clean_units)
    if isinstance(body.get("accounts"), list):
        clean_accounts = []
        for acc in body["accounts"][:300]:
            if isinstance(acc, dict):
                raw_sessions = acc.get("sessions")
                clean_sessions = []
                if isinstance(raw_sessions, list):
                    for s in raw_sessions[:5]:
                        if isinstance(s, dict):
                            clean_sessions.append({
                                "tty": _clean_str(s.get("tty"), "", 32),
                                "from": _clean_str(s.get("from"), "", 64),
                                "time": _clean_str(s.get("time"), "", 32),
                            })
                raw_groups = acc.get("groups")
                clean_groups_list = []
                if isinstance(raw_groups, list):
                    for g in raw_groups[:30]:
                        if isinstance(g, str) and g.strip():
                            clean_groups_list.append(_clean_str(g, "", 64))

                clean_accounts.append({
                    "user": _clean_str(acc.get("user"), "", 64),
                    "uid": _clamp_int(acc.get("uid"), None, 0, 2 ** 31),
                    "gid": _clamp_int(acc.get("gid"), None, 0, 2 ** 31),
                    "group": _clean_str(acc.get("group"), "", 64),
                    "groups": clean_groups_list,
                    "home": _clean_str(acc.get("home"), "", 128),
                    "shell": _clean_str(acc.get("shell"), "", 50),
                    "last_login": _clean_str(acc.get("last_login"), None, 64),
                    "sessions": clean_sessions,
                    "is_system": bool(acc.get("is_system")),
                    "is_sudo": bool(acc.get("is_sudo")),
                    "is_protected": bool(acc.get("is_protected")),
                    "is_locked": bool(acc.get("is_locked")),
                })
        extras.accounts = json.dumps(clean_accounts)
    if isinstance(body.get("groups"), list):
        clean_groups = []
        for grp_item in body["groups"][:300]:
            if isinstance(grp_item, dict):
                raw_mems = grp_item.get("members")
                clean_mems = []
                if isinstance(raw_mems, list):
                    for m in raw_mems[:50]:
                        if isinstance(m, str) and m.strip():
                            clean_mems.append(_clean_str(m, "", 64))
                clean_groups.append({
                    "group": _clean_str(grp_item.get("group"), "", 64),
                    "gid": _clamp_int(grp_item.get("gid"), None, 0, 2 ** 31),
                    "is_system": bool(grp_item.get("is_system")),
                    "is_privileged": bool(grp_item.get("is_privileged")),
                    "members": clean_mems,
                    "member_count": _clamp_int(grp_item.get("member_count"), len(clean_mems), 0, 10000),
                })
        extras.system_groups = json.dumps(clean_groups)

    # Info packages OS yang bisa di-upgrade (dari agen)
    if isinstance(body.get("apt"), dict):
        apt = body["apt"]
        if isinstance(apt.get("upgradable"), int):
            extras.apt_upgradable = max(0, apt["upgradable"])
            if extras.apt_upgradable == 0:
                extras.apt_packages = "[]"
                # Selesaikan masalah apt_updates seketika jika upgrade dilakukan langsung di server klien
                for prob in db.query(ServerProblem).filter(
                    ServerProblem.server_id == server.id,
                    ServerProblem.key == "apt_updates",
                    ServerProblem.resolved_at.is_(None)
                ).all():
                    prob.resolved_at = datetime.utcnow()
                    prob.resolved_note = _clean_str("auto (upgrade selesai di klien)", "auto", 100)
            else:
                if getattr(server, "is_isolated_net", 0) != 1:
                    upg_cnt = int(extras.apt_upgradable)
                    new_msg = f"{upg_cnt} packages menunggu upgrade"
                    new_ctx = _build_problem_context("apt_updates", server, upgradable=upg_cnt)
                    prob = db.query(ServerProblem).filter(
                        ServerProblem.server_id == server.id,
                        ServerProblem.key == "apt_updates",
                        ServerProblem.resolved_at.is_(None)
                    ).first()
                    if prob:
                        prob.message = new_msg
                        prob.context = new_ctx
                        prob.updated_at = datetime.utcnow()
                    else:
                        prob = ServerProblem(
                            server_id=server.id,
                            key="apt_updates",
                            severity="info",
                            message=new_msg,
                            tip=APT_TIP,
                            started_at=datetime.utcnow(),
                            last_active_at=datetime.utcnow(),
                            context=new_ctx
                        )
                        db.add(prob)
        if isinstance(apt.get("last_update"), str):
            last_upd = _parse_iso_dt(apt["last_update"], None)
            if last_upd is not None:
                extras.apt_last_update = last_upd
        if isinstance(apt.get("packages"), list):
            running = [
                s.service_name
                for s in db.query(Service).filter(Service.server_id == server.id).all()
                if s.service_name
            ]
            pkgs = []
            for p in apt["packages"]:
                if isinstance(p, str) and p.strip():
                    cfg = {"name": p.strip(), "version": "", "services": []}
                elif isinstance(p, dict) and p.get("name"):
                    cfg = {
                        "name": str(p["name"]).strip(),
                        "version": str(p.get("version") or "").strip(),
                        "services": [],
                    }
                else:
                    continue
                cfg["services"] = _apt_pkg_services(cfg["name"], running)
                if cfg["name"]:
                    pkgs.append(cfg)
            extras.apt_packages = json.dumps(pkgs) if (pkgs and (extras.apt_upgradable or 0) > 0) else "[]"

    if body.get("packages_changed"):
        # Otomatis jadwalkan pembaruan inventaris packages terpasang jika ada perubahan packages langsung di klien
        recent_pkg_req = (
            db.query(LogRequest)
            .filter(
                LogRequest.server_id == server.id,
                LogRequest.unit == "PKG_LIST",
                LogRequest.status == "pending"
            )
            .first()
        )
        if not recent_pkg_req:
            db.add(LogRequest(server_id=server.id, unit="PKG_LIST", status="pending"))
    if isinstance(body.get("security"), dict):
        sec = body["security"]
        _ls_raw = _clean_str(sec.get("last_seen"), None, 32)
        last_seen = None
        if _ls_raw:
            try:
                datetime.fromisoformat(_ls_raw)
                last_seen = _ls_raw
            except ValueError:
                last_seen = None
        clean = {
            "failed": _clamp_int(sec.get("failed"), 0, 0, 10 ** 9),
            "invalid_users": _clamp_int(sec.get("invalid_users"), 0, 0, 10 ** 9),
            "source_ips": {str(k)[:45]: _clamp_int(v, 0, 0, 10 ** 9)
                           for k, v in (sec.get("source_ips") or {}).items()
                           if isinstance(v, (int, float)) and _validate_ip(str(k))},
            "last_seen": last_seen,
        }
        extras.security = json.dumps(clean)

    # Validasi & Simpan Tugas Terjadwal (Cron Jobs & Timers)
    if isinstance(body.get("cron_jobs"), dict):
        cj = body["cron_jobs"]
        clean_cron = {
            "jobs": [
                {
                    "type": _clean_str(item.get("type"), "cron", 20),
                    "source": _clean_str(item.get("source"), "", 120),
                    "line": _clamp_int(item.get("line"), 0, 0, 100000),
                    "schedule": _clean_str(item.get("schedule"), "", 60),
                    "user": _clean_str(item.get("user"), "root", 64),
                    "command": _clean_str(item.get("command"), "", 500),
                    "is_managed": bool(item.get("is_managed")),
                    "ident": _clean_str(item.get("ident"), "", 64),
                    "is_enabled": bool(item.get("is_enabled", True)),
                }
                for item in (cj.get("jobs") or [])[:100]
                if isinstance(item, dict)
            ],
            "timers": [
                {
                    "timer": _clean_str(t.get("timer"), "", 100),
                    "activates": _clean_str(t.get("activates"), "", 100),
                    "raw": _clean_str(t.get("raw"), "", 200),
                }
                for t in (cj.get("timers") or [])[:50]
                if isinstance(t, dict)
            ]
        }
        extras.cron_jobs = json.dumps(clean_cron)

    # Validasi & Simpan Konfigurasi Firewall
    if isinstance(body.get("firewall"), dict):
        fw = body["firewall"]
        clean_fw = {
            "backend": _clean_str(fw.get("backend"), "unknown", 20),
            "status": _clean_str(fw.get("status"), "inactive", 20),
            "rules": [
                _clean_str(r, "", 150)
                for r in (fw.get("rules") or [])[:100]
                if isinstance(r, str)
            ],
            "blocked_ips": [
                {
                    "num": _clean_str(b.get("num"), "", 10),
                    "pkts": _clean_str(b.get("pkts"), "", 20),
                    "bytes": _clean_str(b.get("bytes"), "", 20),
                    "source": _clean_str(b.get("source"), "", 50),
                }
                for b in (fw.get("blocked_ips") or [])[:100]
                if isinstance(b, dict)
            ]
        }
        extras.firewall = json.dumps(clean_fw)

    # Validasi & Simpan Listening Ports (ss -tulpn)
    if isinstance(body.get("listening_ports"), list):
        clean_ports = [
            {
                "proto": _clean_str(p.get("proto"), "tcp", 10),
                "ip": _clean_str(p.get("ip"), "", 64),
                "port": _clamp_int(p.get("port"), 0, 1, 65535),
                "proc": _clean_str(p.get("proc"), "", 100),
                "pid": _clamp_int(p.get("pid"), None, 1, 4194304) if p.get("pid") else None,
                "pname": _clean_str(p.get("pname"), "", 50),
                "is_loopback": bool(p.get("is_loopback")),
                "is_public": bool(p.get("is_public")),
            }
            for p in body["listening_ports"][:100]
            if isinstance(p, dict)
        ]
        extras.listening_ports = json.dumps(clean_ports)

    # Validasi & Simpan Sertifikat SSL/TLS
    if isinstance(body.get("ssl_certs"), list):
        clean_certs = [
            {
                "path": _clean_str(c.get("path"), "", 200),
                "subject": _clean_str(c.get("subject"), "", 200),
                "domains": [_clean_str(d, "", 100) for d in (c.get("domains") or [])[:20] if isinstance(d, str)],
                "issuer": _clean_str(c.get("issuer"), "", 200),
                "not_after": _clean_str(c.get("not_after"), "", 40),
                "days_left": _clamp_int(c.get("days_left"), 0, -10000, 10000),
                "is_expired": bool(c.get("is_expired")),
                "is_critical": bool(c.get("is_critical")),
                "is_warning": bool(c.get("is_warning")),
                "is_custom": bool(c.get("is_custom")),
            }
            for c in body["ssl_certs"][:50]
            if isinstance(c, dict)
        ]
        extras.ssl_certs = json.dumps(clean_certs)

    # Validasi & Simpan System Logs (kegagalan sistem journalctl)
    if isinstance(body.get("system_logs"), list):
        clean_logs = [
            {
                "time": _clean_str(l.get("time"), "", 30),
                "unit": _clean_str(l.get("unit"), "-", 80),
                "message": _clean_str(l.get("message"), "", 400),
                "priority": _clamp_int(l.get("priority"), 3, 0, 7),
            }
            for l in body["system_logs"][:60]
            if isinstance(l, dict)
        ]
        extras.system_logs = json.dumps(clean_logs)

    # Validasi & Simpan Available Logs (Daftar sumber log yang nyata ada di klien)
    if isinstance(body.get("available_logs"), list):
        clean_avail_logs = [
            {
                "id": _clean_str(al.get("id"), "", 64),
                "group": _clean_str(al.get("group"), "Sistem", 64),
                "name": _clean_str(al.get("name"), "", 100),
                "desc": _clean_str(al.get("desc"), "", 150),
            }
            for al in body["available_logs"][:40]
            if isinstance(al, dict) and al.get("id")
        ]
        extras.available_logs = json.dumps(clean_avail_logs)

    # Validasi & Simpan Kernel Events (OOM killer, disk I/O error, segfault, panic)
    if isinstance(body.get("kernel_events"), dict):
        ke = body["kernel_events"]
        clean_events = []
        for ev in (ke.get("events") or [])[:40]:
            if not isinstance(ev, dict):
                continue
            clean_events.append({
                "type": _clean_str(ev.get("type"), "", 30),
                "time": _clean_str(ev.get("time"), "", 30),
                "epoch": float(ev.get("epoch") or 0.0),
                "proc": _clean_str(ev.get("proc"), "", 80),
                "pid": _clamp_int(ev.get("pid"), 0, 0, 4_194_304),
                "dev": _clean_str(ev.get("dev"), "", 30),
                "unit": _clean_str(ev.get("unit"), "", 80),
                "detail": _clean_str(ev.get("detail"), "", 100),
                "message": _clean_str(ev.get("message"), "", 400),
            })
        clean_ke = {
            "oom_kill_count": _clamp_int(ke.get("oom_kill_count"), 0, 0, 1_000_000_000),
            "events": clean_events,
        }
        extras.kernel_events = json.dumps(clean_ke)

    extras.updated_at = datetime.utcnow()
    db.commit()

    # Rekonsiliasi insiden server seketika pada saat laporan telemetri diterima
    try:
        services = db.query(Service).filter(Service.server_id == server.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        svc_data = [
            {
                "name": s.service_name,
                "status": latest_map[s.id].status if s.id in latest_map else "unknown",
                "port": s.port,
                "proc": s.process_name,
                "is_core": bool(getattr(s, "is_core", 1)),
                "health_msg": latest_map[s.id].health_message if s.id in latest_map else None,
            }
            for s in services
        ]
        sync_server_problems(db, server, _problem_instances(server, extras, svc_data, db))
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("[api_report] Error rekonsiliasi insiden untuk %s: %s", server.hostname, exc)

    return {"ok": True}


# ===========================================================================
# 2. Commands Polling & Result Processing
# ===========================================================================
@router.get("/api/commands")
def api_commands_pending(
    request: Request,
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent mem-poll command pending untuk servernya."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    pending = (
        db.query(Command)
        .filter(Command.server_id == server.id, Command.status == "pending")
        .order_by(Command.created_at)
        .all()
    )

    # Self-update OTA otomatis armada agen jika versi agen lebih lama dari berkas agen dashboard
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
    target_ver = getattr(settings, "APP_VERSION", "4.8.120")
    try:
        _, _, latest_agent_ver = _get_agent_code_and_sha256()
        if latest_agent_ver:
            target_ver = latest_agent_ver
    except Exception:
        pass
    if extras and extras.agent_version and _is_agent_outdated(extras.agent_version, target_ver):
        has_ota = any(c.action == "update_agent" for c in pending)
        if not has_ota:
            in_flight = (
                db.query(Command)
                .filter(Command.server_id == server.id, Command.action == "update_agent", Command.status == "executing")
                .first()
            )
            if not in_flight:
                # Cegah loop berulang: jika sudah ada perintah update dalam 5 menit terakhir, jangan dispatch lagi
                recent_cmd = (
                    db.query(Command)
                    .filter(
                        Command.server_id == server.id,
                        Command.action == "update_agent",
                        Command.created_at > datetime.utcnow() - timedelta(minutes=5)
                    )
                    .first()
                )
                if not recent_cmd:
                    try:
                        _, sha256_hash, file_ver = _get_agent_code_and_sha256()
                        if _is_agent_outdated(extras.agent_version, file_ver):
                            base_url = str(request.base_url).rstrip("/")
                            ota_params = {
                                "url": f"{base_url}/api/agent/latest-code",
                                "sha256": sha256_hash,
                                "version": file_ver,
                            }
                            auto_cmd = Command(
                                server_id=server.id,
                                action="update_agent",
                                params=json.dumps(ota_params),
                                issued_by="system (auto-update)",
                                status="pending",
                            )
                            db.add(auto_cmd)
                            db.commit()
                            pending.append(auto_cmd)
                            logger.info("[AUTO-OTA] Otomatis mendispatch self-update agen v%s ke %s (ID %s)", file_ver, server.hostname, server.id)
                    except Exception as ota_err:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        logger.warning("[AUTO-OTA] Gagal memproses auto-OTA untuk %s: %s", server.hostname, ota_err)

    return {
        "commands": [
            {
                "id": c.id,
                "action": c.action,
                "service_name": c.service.service_name if c.service else (_safe_json_get(c.params, "service_name")),
                "process_name": _normalize_unit_for_systemctl(c.service.process_name if c.service else (c.service.service_name if c.service else (_safe_json_get(c.params, "process_name")))),
                "port": c.service.port if c.service else None,
                "params": _safe_json_loads(c.params),
            }
            for c in pending
        ]
    }


@router.post("/api/commands/{cid}/status")
def api_command_status(
    cid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent menandai command sedang dieksekusi."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if body.get("status") != "executing":
        raise HTTPException(status_code=400, detail="Status must be 'executing'")
    cmd = db.query(Command).filter(
        Command.id == cid, Command.server_id == server.id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd.status = "executing"
    db.commit()
    return {"ok": True}


@router.post("/api/commands/{cid}/result")
def api_command_result(
    cid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent melaporkan hasil eksekusi command."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    status = body.get("status")
    if status not in ("success", "failed"):
        raise HTTPException(status_code=400, detail="Status must be 'success' or 'failed'")
    cmd = db.query(Command).filter(
        Command.id == cid, Command.server_id == server.id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd.status = status
    cmd.result = _clean_str(body.get("result"), "", 4000)
    cmd.executed_at = datetime.utcnow()

    # Jika agen menyertakan snapshot firewall terkini setelah eksekusi perintah, segera sinkronkan ke ServerExtras
    if isinstance(body.get("firewall"), dict):
        try:
            extra = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
            if extra:
                fw = body["firewall"]
                clean_fw = {
                    "backend": _clean_str(fw.get("backend"), "unknown", 20),
                    "status": _clean_str(fw.get("status"), "inactive", 20),
                    "rules": [
                        _clean_str(r, "", 150)
                        for r in (fw.get("rules") or [])[:100]
                        if isinstance(r, str)
                    ],
                    "blocked_ips": [
                        {
                            "num": str(b.get("num", "")),
                            "pkts": str(b.get("pkts", "")),
                            "bytes": str(b.get("bytes", "")),
                            "source": str(b.get("source", "")),
                        }
                        for b in (fw.get("blocked_ips") or [])[:100]
                        if isinstance(b, dict)
                    ]
                }
                extra.firewall = json.dumps(clean_fw)
                db.commit()
        except Exception as fw_err:
            logger.warning("[cmd_result] Gagal sinkronisasi data firewall agen: %s", fw_err)

    # Jika aksi service stop sukses, segera sisipkan metrik down agar data live langsung sinkron tanpa jeda
    if cmd.service_id and cmd.action in ("stop", "service_stop") and status == "success":
        try:
            m = Metric(
                service_id=cmd.service_id,
                status="down",
                response_time_ms=None,
                active_connections=0,
                timestamp=datetime.utcnow(),
                health_message="Service dihentikan oleh operator",
            )
            db.add(m)
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("[cmd_result] Gagal menambah metrik down seketika: %s", e)

    # Jika aksi service start / restart sukses, segera sisipkan metrik up & tutup masalah seketika
    if cmd.service_id and cmd.action in ("start", "restart", "service_start", "service_restart") and status == "success":
        try:
            m = Metric(
                service_id=cmd.service_id,
                status="up",
                response_time_ms=1.0,
                active_connections=0,
                timestamp=datetime.utcnow(),
                health_message="Service berhasil dimulai oleh operator",
            )
            db.add(m)
            svc_obj = db.query(Service).filter(Service.id == cmd.service_id).first()
            if svc_obj:
                for op in db.query(ServerProblem).filter(
                    ServerProblem.server_id == cmd.server_id,
                    ServerProblem.key == f"service_down:{svc_obj.service_name}",
                    ServerProblem.resolved_at.is_(None),
                ).all():
                    op.resolved_at = datetime.utcnow()
                    op.updated_at = datetime.utcnow()
                    op.resolved_note = "operator_start"
                if getattr(svc_obj, "ignore_mode", None) != "permanent":
                    svc_obj.is_ignored = 0
                    svc_obj.ignored_until = None
                    svc_obj.ignored_reason = None
                    svc_obj.ignore_mode = None
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("[cmd_result] Gagal update metrik/problem up seketika: %s", e)

    # Sinkronkan status tindakan ke AuditLog agar rekam jejak mencatat status riil (berhasil / gagal)
    try:
        recent_audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.server_id == server.id,
                AuditLog.created_at >= cmd.created_at - timedelta(seconds=30),
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        if recent_audit and recent_audit.result in ("dikirim ke agen", "diproses…"):
            if status == "success":
                recent_audit.result = "berhasil"
            else:
                err_line = cmd.result.splitlines()[0].strip() if cmd.result else "eksekusi gagal"
                if len(err_line) > 120:
                    err_line = err_line[:117] + "…"
                recent_audit.result = f"gagal: {err_line}"
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("[cmd_audit_sync] Gagal sinkronkan AuditLog: %s", exc)

    db.commit()
    return {"ok": True}


# ===========================================================================
# 3. Log Requests & Remote Commands (Agent & Operator)
# ===========================================================================
@router.get("/api/logs/services")
def api_logs_services(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Daftar unit service aktif + mode file untuk dropdown log."""
    units = []
    try:
        p = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=running",
             "--no-pager", "--no-legend"],
            capture_output=True, text=True, timeout=15,
        )
        for line in p.stdout.splitlines():
            s = line.split()
            if s and s[0].endswith(".service") and VALID_UNIT_RE.match(s[0][:-8]):
                units.append(s[0][:-8])
    except (subprocess.TimeoutExpired, OSError):
        pass
    return {"units": sorted(set(units)), "extras": ["SYSLOG", "AUTH", "SYSTEM"]}


@router.get("/api/logs/service")
def api_logs_service(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    unit: str = "mariadb",
    lines: int = 300,
):
    lines = max(10, min(lines, 2000))
    if unit == "SYSLOG":
        return {"unit": unit, "lines": tail_lines(SYSLOG_FILE, lines) or [f"[file {SYSLOG_FILE} tak dapat dibaca]"]}
    if unit == "AUTH":
        return {"unit": unit, "lines": tail_lines(AUTH_FILE, lines) or [f"[file {AUTH_FILE} tak dapat dibaca]"]}
    if unit == "SYSTEM":
        return {"unit": unit, "lines": _journal_boot_tail(lines)}
    if not VALID_UNIT_RE.match(unit):
        raise HTTPException(status_code=400, detail="Invalid unit name")
    return {"unit": unit, "lines": _journal_tail(unit, lines)}


@router.get("/api/logs/pending")
def api_logs_pending(
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent mem-poll permintaan log yang masih pending untuk servernya."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    _expire_stale_logs(db, server.id)

    pending = (
        db.query(LogRequest)
        .filter(LogRequest.server_id == server.id, LogRequest.status == "pending")
        .order_by(LogRequest.created_at)
        .limit(10)
        .all()
    )
    return {
        "requests": [
            {"id": r.id, "unit": r.unit, "lines": r.lines, "detail": r.detail} for r in pending
        ]
    }


@router.post("/api/logs/{rid}/status")
def api_logs_status(
    rid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent menandai permintaan log sedang diproses."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if body.get("status") != "executing":
        raise HTTPException(status_code=400, detail="Status must be 'executing'")
    req = db.query(LogRequest).filter(
        LogRequest.id == rid, LogRequest.server_id == server.id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")
    req.status = "executing"
    req.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/api/logs/{rid}/progress")
def api_logs_progress(
    rid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent mengirim chunk output saat proses panjang (apt update/upgrade)."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    chunk = body.get("chunk")
    if chunk is None:
        raise HTTPException(status_code=400, detail="chunk required")
    req = db.query(LogRequest).filter(
        LogRequest.id == rid, LogRequest.server_id == server.id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")
    if req.status != "executing":
        return {"ok": True, "ignored": True}

    new_result = str(chunk) if body.get("replace") else (req.result or "") + str(chunk)
    req.result = _clean_terminal(new_result, APT_STREAM_MAXCHARS, APT_STREAM_MAXLINES)
    req.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/api/logs/{rid}/input")
def api_logs_input(
    rid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    req = db.query(LogRequest).filter(LogRequest.id == rid).first()
    if not req:
        raise HTTPException(status_code=404, detail="Permintaan tidak ditemukan")
    if req.unit == SHELL_UNIT:
        if not user.has_perm("can_terminal"):
            raise HTTPException(status_code=403, detail="Akses ditolak: izin terminal diperlukan")
    elif req.unit in APT_UNITS:
        if not user.has_perm("can_apt"):
            raise HTTPException(status_code=403, detail="Akses ditolak: izin APT diperlukan")
    else:
        if not (user.is_master_admin() or user.is_operator()):
            raise HTTPException(status_code=403, detail="Akses ditolak")
    if req.status != "executing" or req.unit not in INTERACTIVE_UNITS:
        raise HTTPException(status_code=409, detail="Proses tidak sedang berjalan")

    raw = body.get("data")
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="data harus string")

    if req.unit == SHELL_UNIT:
        raw = "".join(ch for ch in raw if ch != "\x00" and not "\x80" <= ch <= "\x9f")
        if len(raw) > SHELL_INPUT_MAX:
            raw = raw[-SHELL_INPUT_MAX:]
        if not raw:
            return {"ok": True}
        db.execute(
            text(
                "UPDATE log_requests SET input_queue = CONCAT("
                "COALESCE(input_queue, ''), :chunk) "
                "WHERE id = :rid AND CHAR_LENGTH(COALESCE(input_queue, '')) "
                "+ CHAR_LENGTH(:chunk) <= :cap"
            ),
            {"chunk": raw, "rid": rid, "cap": SHELL_INPUT_MAX},
        )
    else:
        cleaned = _CLEAN_CTRL_RE.sub("", raw.replace("\r", ""))
        cleaned = cleaned.replace("\n", "").replace("\t", " ")[:200].strip()
        req.input_data = (cleaned + "\n") if cleaned else "\n"
    req.input_at = datetime.utcnow()
    req.updated_at = req.input_at
    db.commit()
    return {"ok": True}


@router.get("/api/logs/{rid}/input")
def api_logs_input_take(
    rid: int,
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Ambil input admin (sekali ambil lalu dikosongkan). Dipanggil agent."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if _req_is_shell(db, rid, server.id):
        row = db.execute(
            text("SELECT input_queue FROM log_requests WHERE id=:rid FOR UPDATE"),
            {"rid": rid},
        ).first()
        data = row[0] if row and row[0] else None
        if data:
            db.execute(text("UPDATE log_requests SET input_queue=NULL, input_at=NULL WHERE id=:rid"),
                       {"rid": rid})
            db.commit()
        return {"data": data}

    req = db.query(LogRequest).filter(
        LogRequest.id == rid, LogRequest.server_id == server.id
    ).first()
    if not req or not req.input_data or req.status != "executing":
        return {"data": None}
    data = req.input_data
    req.input_data = None
    req.input_at = None
    db.commit()
    return {"data": data}


@router.post("/api/logs/{rid}/result")
def api_logs_result(
    rid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent melaporkan hasil pembacaan log untuk satu permintaan."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    status = body.get("status")
    if status not in ("success", "failed"):
        raise HTTPException(status_code=400, detail="Status must be 'success' or 'failed'")
    req = db.query(LogRequest).filter(
        LogRequest.id == rid, LogRequest.server_id == server.id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")

    req.status = status
    if req.unit in ("PKG_LIST", "SYSTEMD_LIST"):
        raw_res = str(body.get("result") or "").strip()
        if raw_res.startswith("[") and raw_res.endswith("]"):
            req.result = raw_res
        else:
            if raw_res.startswith("-- No entries"):
                req.status = "failed"
                req.result = "Agen pada server belum mendukung pemindaian ini (perlu update agen)."
            else:
                req.result = raw_res or "[]"
    else:
        clean = _clean_terminal if req.unit in INTERACTIVE_UNITS else _clean_result
        req.result = clean(body.get("result"), APT_STREAM_MAXCHARS, APT_STREAM_MAXLINES)
    req.updated_at = datetime.utcnow()

    # Sesi shell ditutup: jangan simpan sisa input tak terpakai
    if req.unit == SHELL_UNIT and (req.input_data or req.input_queue):
        req.input_data = None
        req.input_queue = None
        req.input_at = None

    db.commit()

    if req.unit == "PKG_LIST" and req.status == "success":
        try:
            if req.result and req.result.startswith("[") and req.result.endswith("]"):
                extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
                if not extras:
                    extras = ServerExtras(server_id=server.id)
                    db.add(extras)
                extras.installed_packages = req.result
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("[PKG_LIST] Gagal simpan extras.installed_packages: %s", e)

    if req.unit == "SYSTEMD_LIST" and req.status == "success":
        try:
            if req.result and req.result.startswith("[") and req.result.endswith("]"):
                extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
                if not extras:
                    extras = ServerExtras(server_id=server.id)
                    db.add(extras)
                extras.systemd_units = req.result
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("[SYSTEMD_LIST] Gagal simpan extras.systemd_units: %s", e)

    # Segera sinkronkan status apt ke ServerExtras
    if req.unit in ("APT_UPDATE", "APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE", "APT_FIX", "PKG_UPGRADE") and status == "success":
        try:
            raw_res = body.get("result", "")
            parsed = None
            try:
                parsed = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
            except Exception:
                parsed = None

            extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
            if not extras:
                extras = ServerExtras(server_id=server.id)
                db.add(extras)

            if req.unit in ("APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE"):
                if isinstance(parsed, dict) and isinstance(parsed.get("apt"), dict):
                    apt_info = parsed["apt"]
                    extras.apt_upgradable = _clamp_int(apt_info.get("upgradable"), 0)
                    pkgs = apt_info.get("packages") if isinstance(apt_info.get("packages"), list) else []
                    extras.apt_packages = json.dumps(pkgs[:200]) if extras.apt_upgradable > 0 else "[]"
                else:
                    extras.apt_upgradable = 0
                    extras.apt_packages = "[]"
                extras.apt_last_update = datetime.utcnow()
                recent_pkg_req = db.query(LogRequest).filter(
                    LogRequest.server_id == server.id,
                    LogRequest.unit == "PKG_LIST",
                    LogRequest.status == "pending"
                ).first()
                if not recent_pkg_req:
                    db.add(LogRequest(server_id=server.id, unit="PKG_LIST", status="pending"))
            elif req.unit == "APT_UPDATE":
                if isinstance(parsed, dict) and isinstance(parsed.get("apt"), dict):
                    apt_info = parsed["apt"]
                    extras.apt_upgradable = _clamp_int(apt_info.get("upgradable"), 0)
                    pkgs = apt_info.get("packages") if isinstance(apt_info.get("packages"), list) else []
                    extras.apt_packages = json.dumps(pkgs[:200])
                    if not parsed.get("has_fetch_err"):
                        extras.apt_last_update = datetime.utcnow()
            elif req.unit == "PKG_UPGRADE":
                if extras.apt_upgradable and extras.apt_upgradable > 0:
                    extras.apt_upgradable = max(0, extras.apt_upgradable - 1)
                if req.detail and extras.apt_packages:
                    try:
                        pkgs = json.loads(extras.apt_packages)
                        if isinstance(pkgs, list):
                            pkgs = [p for p in pkgs if (p if isinstance(p, str) else p.get("name")) != req.detail]
                            extras.apt_packages = json.dumps(pkgs)
                            extras.apt_upgradable = len(pkgs)
                    except Exception:
                        pass
                extras.apt_last_update = datetime.utcnow()
                recent_pkg_req = db.query(LogRequest).filter(
                    LogRequest.server_id == server.id,
                    LogRequest.unit == "PKG_LIST",
                    LogRequest.status == "pending"
                ).first()
                if not recent_pkg_req:
                    db.add(LogRequest(server_id=server.id, unit="PKG_LIST", status="pending"))

            # Sinkronkan masalah apt_updates secara riil seketika ke database
            if (extras.apt_upgradable or 0) == 0:
                for p in db.query(ServerProblem).filter(
                    ServerProblem.server_id == server.id,
                    ServerProblem.key == "apt_updates",
                    ServerProblem.resolved_at.is_(None)
                ).all():
                    p.resolved_at = datetime.utcnow()
                    p.resolved_note = _clean_str("auto (upgrade selesai)", "auto", 100)
            else:
                upg_cnt = int(extras.apt_upgradable)
                new_msg = f"{upg_cnt} packages menunggu upgrade"
                new_ctx = _build_problem_context("apt_updates", server, upgradable=upg_cnt)
                prob = db.query(ServerProblem).filter(
                    ServerProblem.server_id == server.id,
                    ServerProblem.key == "apt_updates",
                    ServerProblem.resolved_at.is_(None)
                ).first()
                if prob:
                    prob.message = new_msg
                    prob.context = new_ctx
                    prob.updated_at = datetime.utcnow()
                else:
                    prob = ServerProblem(
                        server_id=server.id,
                        key="apt_updates",
                        severity="info",
                        message=new_msg,
                        tip=APT_TIP,
                        started_at=datetime.utcnow(),
                        last_active_at=datetime.utcnow(),
                        context=new_ctx
                    )
                    db.add(prob)
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("[apt_result_sync] Gagal sinkronkan ServerExtras: %s", exc)

    # Sinkronkan status akhir tindakan ke AuditLog
    try:
        audit_act = f"apt_{req.unit.removeprefix('APT_').lower()}"
        recent_audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.server_id == server.id,
                AuditLog.action == audit_act,
                AuditLog.created_at >= req.created_at - timedelta(seconds=15)
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        if recent_audit:
            if status == "success":
                recent_audit.result = f"berhasil ({req.detail})" if req.detail else "berhasil"
            else:
                err_snip = [line.strip() for line in (req.result or "").splitlines() if line.strip() and not line.strip().startswith("────")]
                err_line = err_snip[0] if err_snip else "eksekusi gagal"
                if len(err_line) > 120:
                    err_line = err_line[:117] + "…"
                recent_audit.result = f"gagal: {err_line}"
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("[audit_sync] Gagal sinkronkan AuditLog: %s", exc)

    db.commit()
    return {"ok": True}


@router.post("/api/logs/request")
def api_logs_request(
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Buat permintaan log service (dieksekusi agent klien)."""
    _verify_csrf_header(request)
    sid = _clamp_int(body.get("server_id"), None, 0, 2 ** 31 - 1)
    unit = _clean_str(body.get("unit"), "", 100)
    lines = _clamp_int(body.get("lines"), 200, 10, 2000)
    detail = _clean_str(body.get("detail"), "", 128)
    if detail and not VALID_UNIT_RE.match(detail):
        raise HTTPException(status_code=400, detail="Invalid detail")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    if _server_stale(server):
        raise HTTPException(status_code=409, detail="Server sedang offline. Permintaan eksekusi atau log dinonaktifkan.")
    if not VALID_UNIT_RE.match(unit):
        raise HTTPException(status_code=400, detail="Invalid unit name")

    is_apt = unit in APT_UNITS or unit in ("PKG_CLEAR_CACHE",)
    is_shell = unit == SHELL_UNIT
    if is_apt and not user.has_perm("can_apt"):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda tidak memiliki wewenang Update/Upgrade OS (APT)",
        )
    if is_shell and not user.has_perm("can_terminal"):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda tidak memiliki wewenang Terminal Shell Web",
        )
    if is_shell and getattr(server, "allow_web_terminal", 0) == 0:
        raise HTTPException(
            status_code=403,
            detail="Akses Terminal Web dinonaktifkan untuk server ini sesuai kebijakan keamanan",
        )
    if is_shell and not is_terminal_unlocked(user.id, sid):
        raise HTTPException(
            status_code=403,
            detail="Terminal terkunci: Memerlukan otentikasi password untuk membuka sesi",
        )
    if is_apt:
        busy = (
            db.query(LogRequest)
            .filter(
                LogRequest.server_id == sid,
                LogRequest.unit.in_(APT_UNITS),
                LogRequest.status.in_(["pending", "executing"]),
            )
            .first()
        )
        if busy:
            raise HTTPException(status_code=409, detail="Proses apt lain masih berjalan")
    if is_shell:
        busy = (
            db.query(LogRequest)
            .filter(
                LogRequest.server_id == sid,
                LogRequest.unit == SHELL_UNIT,
                LogRequest.status.in_(["pending", "executing"]),
            )
            .first()
        )
        if busy:
            stale_limit = datetime.utcnow() - timedelta(seconds=20)
            is_stale = (busy.updated_at and busy.updated_at < stale_limit) or (busy.created_at < stale_limit and busy.status == "pending")
            if is_stale or body.get("force"):
                busy.status = "failed"
                busy.result = (busy.result or "").strip() + "\n[sesi shell lama ditutup untuk membuka sesi baru]"
                busy.updated_at = datetime.utcnow()
                db.commit()
            else:
                raise HTTPException(status_code=409, detail="Sesi shell sudah terbuka di server ini")

    _expire_stale_logs(db, sid)

    logreq = LogRequest(server_id=sid, unit=unit, lines=lines, detail=detail or None)
    db.add(logreq)
    if is_apt:
        _audit(db, user.username, f"apt_{unit.removeprefix('APT_').lower()}",
               server.hostname, "dikirim ke agen", server_id=sid)
    elif is_shell:
        _audit(db, user.username, "terminal_shell_open", server.hostname,
               "membuka Terminal Bawaan (shell root)", server_id=sid)
    db.commit()
    db.refresh(logreq)

    # Bersihkan permintaan lama yang sudah selesai (maks 100/server)
    done = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == sid,
            LogRequest.status.in_(["success", "failed"]),
        )
        .order_by(desc(LogRequest.created_at))
        .offset(100)
        .all()
    )
    for d in done:
        db.delete(d)
    db.commit()
    return {"id": logreq.id}


@router.get("/api/logs/request/{rid}")
def api_logs_request_status(
    rid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Status & hasil permintaan log untuk polling UI."""
    logreq = db.query(LogRequest).filter(LogRequest.id == rid).first()
    if not logreq:
        raise HTTPException(status_code=404, detail="Log request tidak ditemukan")
    server = db.query(Server.id).filter(Server.id == logreq.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    return {
        "id": logreq.id,
        "status": logreq.status,
        "result": logreq.result,
    }
