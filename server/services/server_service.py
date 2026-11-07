"""Server status, stale evaluation, and grouping services."""

from datetime import datetime, timezone, timedelta
import json
import time
from typing import Dict, List, Optional, Tuple, Any
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

try:
    from models import Metric, Server, Service, ServerProblem, Command, AuditLog
except ImportError:
    from server.models import Metric, Server, Service, ServerProblem, Command, AuditLog

OFFLINE_AFTER_SECONDS = 15

_UPTIME_CACHE_TTL = 60.0  # 1 menit cache in-memory
_uptime_stats_cache: dict[tuple[int, int], tuple[float, dict]] = {}


def get_uptime_stats(db: Session, service_id: int, hours: int = 24) -> dict:
    """Uptime stats untuk service dalam rentang waktu (teroptimasi event-based & in-memory cache)."""
    now_ts = time.time()
    cache_key = (service_id, hours)
    cached = _uptime_stats_cache.get(cache_key)
    if cached and (now_ts - cached[0]) < _UPTIME_CACHE_TTL:
        return cached[1]

    svc = db.query(Service).filter(Service.id == service_id).first()
    if not svc:
        return {"uptime_pct": None, "downtime_seconds": 0, "samples": 0}

    now_utc = datetime.utcnow()
    since = now_utc - timedelta(hours=hours)
    down_sec = 0.0
    if svc.server_id and svc.service_name:
        down_probs = (
            db.query(ServerProblem)
            .filter(
                ServerProblem.server_id == svc.server_id,
                ServerProblem.key == f"service_down:{svc.service_name}",
                (ServerProblem.resolved_at.is_(None)) | (ServerProblem.resolved_at >= since),
                ServerProblem.started_at <= now_utc,
            )
            .all()
        )
        for prob in down_probs:
            p_start = max(since, prob.started_at)
            p_end = prob.resolved_at or now_utc
            if p_end > p_start:
                down_sec += (p_end - p_start).total_seconds()

    total_sec = float(hours * 3600)
    pct = round(max(0.0, min(100.0, ((total_sec - down_sec) / total_sec) * 100.0)), 1)
    res = {
        "uptime_pct": pct,
        "downtime_seconds": int(down_sec),
        "samples": 1 if down_sec == 0 else int(down_sec // 10) + 1,
    }
    _uptime_stats_cache[cache_key] = (now_ts, res)
    return res



def get_existing_groups_and_tags(db: Session) -> Tuple[List[str], List[str]]:
    """Ambil daftar grup dan tag unik dari semua server untuk auto-complete / chips."""
    servers = db.query(Server).all()
    groups = set()
    tags = set()
    for s in servers:
        if s.group_name and s.group_name.strip() and s.group_name.strip().lower() != "default":
            groups.add(s.group_name.strip())
        if s.tags:
            for t in s.tags.split(","):
                t_clean = t.strip()
                if t_clean:
                    tags.add(t_clean)
    return sorted(list(groups)), sorted(list(tags))


def _server_stale(srv: Optional[Server]) -> bool:
    """True bila server belum melapor terlalu lama / tidak pernah melapor / nonaktif."""
    if not srv or not getattr(srv, "is_active", 1):
        return True
    ls = getattr(srv, "last_seen", None)
    if ls is None:
        return True
    if ls.tzinfo is None:
        ls = ls.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ls).total_seconds() > OFFLINE_AFTER_SECONDS


def _check_server_online(db: Session, sid: int, is_json: bool = False, redirect_tab: str = ""):
    """Validasi server ada, aktif, dan online (agen terhubung). Tolak bila offline."""
    server = db.query(Server).filter(Server.id == sid).first()
    if not server or not getattr(server, "is_active", 1):
        if is_json:
            return None, JSONResponse({"ok": False, "detail": "Server tidak ditemukan atau dinonaktifkan"}, status_code=404)
        return None, RedirectResponse("/servers", status_code=303)
    if _server_stale(server):
        msg = "Server sedang offline. Aksi remote dinonaktifkan."
        if is_json:
            return None, JSONResponse({"ok": False, "detail": msg}, status_code=409)
        tab_param = f"?tab={redirect_tab}&error=server_offline" if redirect_tab else "?error=server_offline"
        return None, RedirectResponse(f"/servers/{sid}{tab_param}", status_code=303)
    return server, None



def _server_status(
    srv: Server,
    stale: bool,
    has_services: bool = False,
    any_up: bool = False,
    has_unignored_down: bool = True,
    is_ignored_stale: bool = False,
) -> Tuple[str, str]:
    """Status server dalam satu kosakata untuk semua halaman: (label, kelas_badge)."""
    if not srv.is_active:
        return "nonaktif", "badge-muted"
    if getattr(srv, "is_maintenance", 0):
        return "pemeliharaan", "badge-warn"
    if stale:
        return ("offline", "badge-down") if srv.last_seen else ("-", "badge-muted")
    return "online", "badge-up"


def _latest_metrics(db: Session, service_ids) -> Dict[int, Metric]:
    """Satu query SQL utk metric terbaru per service (hindari N+1)."""
    sids = list(service_ids)
    if not sids:
        return {}
    sub = (
        db.query(Metric.service_id.label("service_id"), func.max(Metric.timestamp).label("max_ts"))
        .filter(Metric.service_id.in_(sids))
        .group_by(Metric.service_id)
        .subquery()
    )
    rows = (
        db.query(Metric)
        .join(sub, (Metric.service_id == sub.c.service_id) & (Metric.timestamp == sub.c.max_ts))
        .all()
    )
    return {m.service_id: m for m in rows}


def _get_server_actions(db: Session, sid: int, limit: int = 50) -> list[dict]:
    """Mengambil riwayat tindakan terpadu (commands + audit_logs) untuk server tertentu."""
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return []

    services = db.query(Service).filter(Service.server_id == sid).all()
    svc_map = {s.id: s.service_name for s in services}

    rows = []

    # 1. Commands dari tabel commands
    cmds = (
        db.query(Command)
        .filter(Command.server_id == sid)
        .order_by(desc(Command.created_at))
        .limit(limit)
        .all()
    )
    for c in cmds:
        tgt_name = svc_map.get(c.service_id)
        if not tgt_name and c.params:
            try:
                p_dict = json.loads(c.params)
                uname = p_dict.get("username")
                if uname:
                    tgt_name = f"Akun {uname}"
                elif p_dict.get("service_name") or p_dict.get("unit"):
                    tgt_name = p_dict.get("service_name") or p_dict.get("unit")
                elif p_dict.get("pname") or p_dict.get("process_name") or p_dict.get("pid"):
                    pname = p_dict.get("pname") or p_dict.get("process_name")
                    pid = p_dict.get("pid")
                    tgt_name = f"PID {pid} ({pname})" if pid and pname else (f"PID {pid}" if pid else pname)
                elif p_dict.get("tty"):
                    tgt_name = f"Sesi {p_dict['tty']}"
                elif p_dict.get("ips"):
                    tgt_name = f"IP {', '.join(p_dict['ips'])}"
                elif p_dict.get("ident"):
                    tgt_name = f"Cron {p_dict['ident']}"
                elif p_dict.get("path"):
                    tgt_name = f"SSL {p_dict['path']}"
                elif p_dict.get("port"):
                    tgt_name = f"Port {p_dict['port']}"
                elif c.action == "update_agent":
                    ver = p_dict.get("version") or ""
                    h = p_dict.get("sha256") or ""
                    h_short = f" (SHA: {h[:8]}…)" if h else ""
                    tgt_name = f"OTA v{ver}{h_short}" if ver else (f"OTA{h_short}" if h_short else "Agen Pantau")
            except Exception:
                pass
        if not tgt_name:
            if c.action in ("restart_agent", "update_agent"):
                tgt_name = "Agen Pantau"
            elif c.action in ("reboot_host", "poweroff_host"):
                tgt_name = server.hostname
            else:
                tgt_name = "—"

        act_label = {
            "restart": "Restart Layanan",
            "stop": "Hentikan Layanan",
            "start": "Jalankan Layanan",
            "reload": "Muat Ulang Layanan",
            "enable": "Aktifkan Boot (Systemd)",
            "disable": "Nonaktifkan Boot (Systemd)",
            "service_restart": "Restart Layanan",
            "service_stop": "Hentikan Layanan",
            "service_start": "Jalankan Layanan",
            "kill_process": "Hentikan Proses (Kill)",
            "block_ip": "Blokir IP",
            "unblock_ip": "Buka Blokir IP",
            "restart_agent": "Restart Agen",
            "update_agent": "Pembaruan Agen (OTA)",
            "reboot_host": "Reboot Host",
            "poweroff_host": "Power Off Host",
            "user_create": "Buat Pengguna",
            "user_lock": "Kunci Akun",
            "user_unlock": "Buka Kunci Akun",
            "user_delete": "Hapus Pengguna",
            "session_terminate": "Putus Sesi Terminal",
            "cron_add": "Tambah Cron Job",
            "cron_toggle": "Ubah Status Cron",
            "cron_delete": "Hapus Cron Job",
            "firewall_enable": "Aktifkan Firewall",
            "firewall_disable": "Nonaktifkan Firewall",
            "firewall_reload": "Muat Ulang Firewall",
            "firewall_port_rule": "Aturan Port Firewall",
            "ssl_path_add": "Tambah Path SSL",
            "ssl_path_remove": "Hapus Path SSL",
        }.get(c.action, c.action.replace("_", " ").capitalize())

        status_cls = {
            "pending": "muted",
            "executing": "warn",
            "success": "up",
            "failed": "danger",
        }.get(c.status, "muted")

        status_label = {
            "pending": "menunggu…",
            "executing": "dieksekusi…",
            "success": "berhasil",
            "failed": "gagal",
        }.get(c.status, c.status)

        rows.append({
            "id": f"cmd-{c.id}",
            "time": c.created_at,
            "user": c.issued_by or "admin",
            "action": c.action,
            "action_label": act_label,
            "target": tgt_name,
            "status": c.status,
            "status_cls": status_cls,
            "status_label": status_label,
            "result": c.result or "—",
        })

    # 2. Audit logs dari tabel audit_logs
    audit_q = (
        db.query(AuditLog)
        .filter(
            (AuditLog.server_id == sid) |
            (AuditLog.target.like(f"%{server.hostname}%")) |
            (AuditLog.target.like(f"%ID {sid}%"))
        )
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
        .all()
    )
    for a in audit_q:
        if a.action in (
            "service_restart", "service_stop", "service_start", "login",
            "server_add", "server_delete", "user_add", "user_delete",
            "user_create", "user_lock", "user_unlock", "user_delete", "session_terminate", "block_ip", "unblock_ip",
            "reboot_host", "poweroff_host", "restart_agent", "agent_update", "update_agent",
            "kill_process",
        ) or a.action.startswith("masalah_") or a.action.startswith("systemd_"):
            continue

        act_label = {
            "problem_ignore": "Abaikan Insiden",
            "problem_unignore": "Pantau Kembali",
            "alert_ack": "Tandai Ditangani",
            "problem_resolve": "Selesaikan Insiden",
            "service_recovered": "Layanan Pulih",
            "maintenance_mode": "Mode Pemeliharaan",
            "maintenance_create": "Buat Jadwal Pemeliharaan",
            "maintenance_cancel": "Batalkan Jadwal Pemeliharaan",
            "maintenance_complete": "Selesaikan Jadwal Pemeliharaan",
            "maintenance_delete": "Hapus Jadwal Pemeliharaan",
            "service_add": "Tambah Layanan",
            "service_delete": "Hapus Layanan",
            "host_reboot": "Reboot OS",
            "host_poweroff": "Power Off",
            "apt_update": "Update OS (apt)",
            "apt_upgrade": "Upgrade OS (apt)",
            "apt_upgrade_interact": "Upgrade OS (interaktif)",
            "terminal_shell_open": "Buka Terminal Root",
            "file_save": "Simpan Berkas",
            "file_upload": "Unggah Berkas",
            "file_rm": "Hapus Berkas",
            "file_mkdir": "Buat Folder",
            "file_rename": "Ubah Nama Berkas",
            "file_chmod": "Ubah Izin Berkas",
            "file_chown": "Ubah Pemilik Berkas",
        }.get(a.action, a.action.replace("_", " ").capitalize())

        res_lower = (a.result or "").lower()
        if "gagal" in res_lower or "failed" in res_lower or "error" in res_lower or "ditolak" in res_lower or "rusak" in res_lower:
            status_cls = "danger"
            status_label = "gagal"
        elif "dikirim" in res_lower or "menunggu" in res_lower or "proses" in res_lower:
            status_cls = "warn"
            status_label = "diproses…"
        else:
            status_cls = "up"
            status_label = "berhasil"

        target_str = a.target or "—"
        if ":" in target_str:
            target_str = target_str.split(":", 1)[1]
        elif target_str == server.hostname or target_str == f"Server {server.hostname}":
            target_str = "—"

        rows.append({
            "id": f"audit-{a.id}",
            "time": a.created_at,
            "user": a.username,
            "action": a.action,
            "action_label": act_label,
            "target": target_str,
            "status": "failed" if status_label == "gagal" else "success",
            "status_cls": status_cls,
            "status_label": status_label,
            "result": a.result or "—",
        })

    rows.sort(key=lambda r: r["time"], reverse=True)
    return rows[:limit]

