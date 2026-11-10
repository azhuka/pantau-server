"""Audit logging service for tracking administrative actions and system history."""

import json
import os
from datetime import datetime, timedelta
from typing import Any, List, Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session

try:
    from models import AuditLog, Command, Server, Service
    from core.utils import _clean_str
except ImportError:
    from server.models import AuditLog, Command, Server, Service
    from server.core.utils import _clean_str


def record_audit(
    db: Session,
    username: str,
    action: str,
    target: Optional[str] = None,
    result: Optional[str] = None,
    meta: Optional[Any] = None,
    server_id: Optional[int] = None,
) -> None:
    """Catat jejak aksi admin pada tabel audit_logs (dicommit oleh pemanggil)."""
    db.add(
        AuditLog(
            server_id=server_id,
            username=_clean_str(username, "-", 100),
            action=_clean_str(action, "", 50),
            target=_clean_str(target, None, 255),
            result=_clean_str(result, None, 500),
            meta=json.dumps(meta) if meta else None,
        )
    )


_audit = record_audit

AUDIT_ACTION_LABELS = {
    "login": "Login",
    "login_2fa": "Login 2FA",
    "logout": "Logout",
    "server_add": "Tambah Server",
    "server_edit": "Ubah Server",
    "server_delete": "Hapus Server",
    "key_regenerate": "Regenerasi Key",
    "service_add": "Tambah Service",
    "service_delete": "Hapus Service",
    "user_add": "Tambah Pengguna",
    "user_delete": "Hapus Pengguna",
    "apt_update": "Update Packages OS (apt)",
    "apt_upgrade": "Upgrade Packages OS (apt)",
    "apt_upgrade_interact": "APT Upgrade (Interaktif)",
    "apt_fix": "APT Fix",
    "alert_ack": "Tangani Insiden",
    "restart": "Restart Service",
    "cmd:restart": "Restart Service",
    "start": "Mulai Service",
    "cmd:start": "Mulai Service",
    "stop": "Hentikan Service",
    "cmd:stop": "Hentikan Service",
    "block_ip": "Blokir IP",
    "cmd:block_ip": "Blokir IP",
    "unblock_ip": "Buka Blokir IP",
    "cmd:unblock_ip": "Buka Blokir IP",
    "firewall_block": "Blokir IP",
    "firewall_unblock": "Buka Blokir IP",
    "firewall_enable": "Aktifkan Firewall",
    "firewall_disable": "Nonaktifkan Firewall",
    "firewall_reload": "Muat Ulang Firewall",
    "cmd:firewall_enable": "Aktifkan Firewall",
    "cmd:firewall_disable": "Nonaktifkan Firewall",
    "cmd:firewall_reload": "Muat Ulang Firewall",
    "kill_process": "Hentikan Proses (Kill)",
    "cmd:kill_process": "Hentikan Proses (Kill)",
    "restart_agent": "Restart Agen",
    "cmd:restart_agent": "Restart Agen",
    "agent_update": "Pembaruan Agen (OTA)",
    "cmd:update_agent": "Pembaruan Agen (OTA)",
    "reboot_host": "Reboot Server",
    "cmd:reboot_host": "Reboot Server",
    "poweroff_host": "Power Off Server",
    "cmd:poweroff_host": "Power Off Server",
    "problem_ignore": "Abaikan Insiden",
    "problem_unignore": "Pantau Kembali Insiden",
    "problem_resolve": "Selesaikan Insiden",
    "maintenance_mode": "Mode Pemeliharaan",
    "maintenance_create": "Buat Jadwal Pemeliharaan",
    "maintenance_cancel": "Batalkan Jadwal Pemeliharaan",
    "maintenance_complete": "Selesaikan Jadwal Pemeliharaan",
    "maintenance_delete": "Hapus Jadwal Pemeliharaan",
    "terminal_shell_open": "Buka Terminal Root",
    "terminal_open": "Buka Terminal",
    "terminal_close": "Tutup Terminal",
    "terminal_unlock": "Buka Kunci Terminal",
    "terminal_unlock_fail": "Gagal Buka Kunci Terminal",
    "terminal_lock": "Kunci Terminal",
    "file_manager_unlock": "Buka Kunci File Manager",
    "file_manager_unlock_fail": "Gagal Buka Kunci File Manager",
    "file_manager_lock": "Kunci File Manager",
    "file_save": "Simpan / Edit Berkas",
    "file_upload": "Unggah Berkas",
    "file_rm": "Hapus Berkas / Folder",
    "file_mkdir": "Buat Folder",
    "file_touch": "Buat Berkas",
    "file_rename": "Ubah Nama",
    "file_chmod": "Ubah Izin (chmod)",
    "file_chown": "Ubah Pemilik (chown)",
    "user_create": "Buat Pengguna Sistem",
    "user_lock": "Kunci Akun Pengguna",
    "user_unlock": "Buka Kunci Akun",
    "user_delete": "Hapus Pengguna",
    "session_terminate": "Putus Sesi Terminal",
    "cmd:user_create": "Buat Pengguna Sistem",
    "cmd:user_lock": "Kunci Akun Pengguna",
    "cmd:user_unlock": "Buka Kunci Akun",
    "cmd:user_delete": "Hapus Pengguna",
    "cmd:session_terminate": "Putus Sesi Terminal",
    "cron_add": "Tambah Cron Job",
    "cron_toggle": "Ubah Status Cron Job",
    "cron_delete": "Hapus Cron Job",
    "cron_run_now": "Jalankan Cron Job Instan",
    "cmd:cron_add": "Tambah Cron Job",
    "cmd:cron_toggle": "Ubah Status Cron Job",
    "cmd:cron_delete": "Hapus Cron Job",
    "cmd:cron_run_now": "Jalankan Cron Job Instan",
    "firewall_port_rule": "Aturan Port Firewall",
    "cmd:firewall_port_rule": "Aturan Port Firewall",
    "ssl_path_add": "Tambah Lokasi SSL",
    "ssl_path_remove": "Hapus Lokasi SSL",
    "cmd:ssl_path_add": "Tambah Lokasi SSL",
    "cmd:ssl_path_remove": "Hapus Lokasi SSL",
    "service_start": "Mulai Service",
    "service_stop": "Hentikan Service",
    "masalah_selesai": "Insiden Selesai",
    "masalah_pulih": "Insiden Selesai",
    "masalah_warning": "Peringatan Insiden",
    "masalah_danger": "Bahaya Insiden",
    "masalah_info": "Informasi Insiden",
    "branding_update": "Setel Organisasi",
    "probe_add": "Tambah Endpoint Pantau",
    "probe_edit": "Ubah Endpoint Pantau",
    "probe_delete": "Hapus Endpoint Pantau",
    "probe_toggle": "Jeda / Lanjutkan Pemantauan",
    "probe_test": "Uji Endpoint Manual",
}

AUDIT_CATEGORIES = [
    {
        "id": "cat:auth",
        "name": "Autentikasi & Akun",
        "name_en": "Auth & User Accounts",
        "keys": [
            "login",
            "login_2fa",
            "logout",
            "user_create",
            "cmd:user_create",
            "user_lock",
            "cmd:user_lock",
            "user_unlock",
            "cmd:user_unlock",
            "user_delete",
            "cmd:user_delete",
            "session_terminate",
            "cmd:session_terminate",
            "user_add",
            "branding_update",
        ],
        "actions": [
            ("login", "Login", "Login"),
            ("login_2fa", "Login 2FA", "2FA Login"),
            ("logout", "Logout", "Logout"),
            ("user_create", "Buat Pengguna Sistem", "Create System User"),
            ("user_lock", "Kunci Akun Pengguna", "Lock User Account"),
            ("user_unlock", "Buka Kunci Akun", "Unlock User Account"),
            ("user_delete", "Hapus Pengguna", "Delete User"),
            ("session_terminate", "Putus Sesi Terminal", "Terminate Terminal Session"),
            ("user_add", "Tambah Akun Web", "Add Web User"),
            ("branding_update", "Setel Organisasi", "Set Organization"),
        ],
    },
    {
        "id": "cat:service",
        "name": "Services & Proses",
        "name_en": "Services & Processes",
        "keys": [
            "service_add",
            "service_delete",
            "restart",
            "cmd:restart",
            "start",
            "cmd:start",
            "stop",
            "cmd:stop",
            "kill_process",
            "cmd:kill_process",
        ],
        "actions": [
            ("restart", "Restart Service", "Restart Service"),
            ("start", "Mulai Service", "Start Service"),
            ("stop", "Hentikan Service", "Stop Service"),
            ("service_add", "Tambah Service", "Add Service"),
            ("service_delete", "Hapus Service", "Delete Service"),
            ("kill_process", "Hentikan Proses (Kill)", "Kill Process"),
        ],
    },
    {
        "id": "cat:firewall",
        "name": "Firewall & Keamanan",
        "name_en": "Firewall & Security",
        "keys": [
            "firewall_block",
            "cmd:block_ip",
            "firewall_unblock",
            "cmd:unblock_ip",
            "firewall_enable",
            "cmd:firewall_enable",
            "firewall_disable",
            "cmd:firewall_disable",
            "firewall_reload",
            "cmd:firewall_reload",
            "firewall_port_rule",
            "cmd:firewall_port_rule",
        ],
        "actions": [
            ("firewall_block", "Blokir IP", "Block IP"),
            ("firewall_unblock", "Buka Blokir IP", "Unblock IP"),
            ("firewall_enable", "Aktifkan Firewall", "Enable Firewall"),
            ("firewall_disable", "Nonaktifkan Firewall", "Disable Firewall"),
            ("firewall_reload", "Muat Ulang Firewall", "Reload Firewall"),
            ("firewall_port_rule", "Aturan Port Firewall", "Port Rule"),
        ],
    },
    {
        "id": "cat:files",
        "name": "Berkas & File Manager",
        "name_en": "Files & File Manager",
        "keys": [
            "file_manager_unlock",
            "file_manager_lock",
            "file_save",
            "file_upload",
            "file_rm",
            "file_mkdir",
            "file_rename",
            "file_chmod",
            "file_chown",
        ],
        "actions": [
            ("file_manager_unlock", "Buka Kunci File Manager", "Unlock File Manager"),
            ("file_manager_lock", "Kunci File Manager", "Lock File Manager"),
            ("file_save", "Simpan / Edit Berkas", "Save / Edit File"),
            ("file_upload", "Unggah Berkas", "Upload File"),
            ("file_rm", "Hapus Berkas / Folder", "Delete File / Folder"),
            ("file_mkdir", "Buat Folder", "Create Folder"),
            ("file_rename", "Ubah Nama", "Rename File"),
            ("file_chmod", "Ubah Izin (chmod)", "Change Permissions"),
            ("file_chown", "Ubah Pemilik (chown)", "Change Owner"),
        ],
    },
    {
        "id": "cat:cron",
        "name": "Tugas Terjadwal (Cron)",
        "name_en": "Cron Jobs",
        "keys": [
            "cron_add",
            "cmd:cron_add",
            "cron_toggle",
            "cmd:cron_toggle",
            "cron_delete",
            "cmd:cron_delete",
            "cron_run_now",
            "cmd:cron_run_now",
        ],
        "actions": [
            ("cron_add", "Tambah Tugas Cron", "Add Cron Job"),
            ("cron_toggle", "Ubah Status Cron", "Toggle Cron Job"),
            ("cron_delete", "Hapus Tugas Cron", "Delete Cron Job"),
            ("cron_run_now", "Uji Jalankan Cron", "Run Cron Now"),
        ],
    },
    {
        "id": "cat:ssl",
        "name": "Sertifikat SSL",
        "name_en": "SSL Certificates",
        "keys": ["ssl_path_add", "cmd:ssl_path_add", "ssl_path_remove", "cmd:ssl_path_remove"],
        "actions": [
            ("ssl_path_add", "Tambah Lokasi SSL", "Add SSL Path"),
            ("ssl_path_remove", "Hapus Lokasi SSL", "Remove SSL Path"),
        ],
    },
    {
        "id": "cat:apt",
        "name": "Pembaruan Packages OS (APT)",
        "name_en": "OS Updates (APT)",
        "keys": ["apt_update", "apt_upgrade", "apt_upgrade_interact"],
        "actions": [
            ("apt_update", "Update Packages OS (apt)", "Update Packages (apt)"),
            ("apt_upgrade", "Upgrade Packages OS (apt)", "Upgrade Packages (apt)"),
        ],
    },
    {
        "id": "cat:server",
        "name": "Server & Pemeliharaan",
        "name_en": "Server & Maintenance",
        "keys": [
            "server_add",
            "server_edit",
            "server_delete",
            "key_regenerate",
            "reboot_host",
            "cmd:reboot_host",
            "poweroff_host",
            "cmd:poweroff_host",
            "restart_agent",
            "cmd:restart_agent",
            "agent_update",
            "cmd:update_agent",
            "terminal_shell_open",
            "maintenance_mode",
            "alert_ack",
            "problem_ignore",
            "problem_unignore",
            "problem_resolve",
        ],
        "actions": [
            ("server_add", "Tambah Server", "Add Server"),
            ("server_edit", "Ubah Server", "Edit Server"),
            ("server_delete", "Hapus Server", "Delete Server"),
            ("key_regenerate", "Regenerasi Key", "Regenerate Key"),
            ("reboot_host", "Reboot Server", "Reboot Server"),
            ("poweroff_host", "Power Off Server", "Power Off Server"),
            ("restart_agent", "Restart Agen", "Restart Agent"),
            ("agent_update", "Pembaruan Agen (OTA)", "Agent Update (OTA)"),
            ("terminal_shell_open", "Buka Terminal Root", "Open Root Terminal"),
            ("maintenance_mode", "Mode Pemeliharaan", "Maintenance Mode"),
            ("alert_ack", "Akui Peringatan (Alert)", "Acknowledge Alert"),
            ("problem_ignore", "Abaikan Insiden", "Ignore Incident"),
            ("problem_unignore", "Pantau Kembali Insiden", "Cancel Ignore Incident"),
        ],
    },
    {
        "id": "cat:probing",
        "name": "Pemantauan Endpoint",
        "name_en": "Endpoint Monitoring",
        "keys": ["probe_add", "probe_edit", "probe_delete", "probe_toggle", "probe_test"],
        "actions": [
            ("probe_add", "Tambah Endpoint Pantau", "Add Endpoint Monitor"),
            ("probe_edit", "Ubah Endpoint Pantau", "Edit Endpoint Monitor"),
            ("probe_delete", "Hapus Endpoint Pantau", "Delete Endpoint Monitor"),
            ("probe_toggle", "Jeda / Lanjutkan", "Pause / Resume"),
            ("probe_test", "Uji Endpoint Manual", "Manual Test Endpoint"),
        ],
    },
]

AUDIT_ACTION_SET = dict(AUDIT_ACTION_LABELS)


def tail_lines(path: str, n: int = 200) -> list:
    """Baca n baris terakhir dari berkas log secara efisien."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            lines = []
            buf = b""
            while size > 0 and len(lines) <= n:
                step = min(block, size)
                size -= step
                f.seek(size)
                buf = f.read(step) + buf
                lines = buf.split(b"\n")
            lines = [l.decode("utf-8", errors="replace") for l in lines if l]
            return lines[-n:]
    except OSError:
        return []


def _audit_rows(
    db: Session,
    limit: int = 500,
    q: str = "",
    action: str = "",
    user_filter: str = "",
    period: str = "",
    server_id: Optional[int] = None,
    status_filter: str = "",
    start_date: str = "",
    end_date: str = "",
) -> List[dict]:
    rows: List[dict] = []
    now_utc = datetime.utcnow()
    cutoff = None
    cutoff_end = None

    if period == "custom":
        if start_date:
            try:
                cutoff = datetime.strptime(start_date, "%Y-%m-%d")
            except Exception:
                cutoff = None
        if end_date:
            try:
                cutoff_end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            except Exception:
                cutoff_end = None
    elif period == "today":
        cutoff = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "24h":
        cutoff = now_utc - timedelta(hours=24)
    elif period == "7d":
        cutoff = now_utc - timedelta(days=7)
    elif period == "30d":
        cutoff = now_utc - timedelta(days=30)

    server_map = {s.id: s.hostname for s in db.query(Server).all()}
    svc_map = {s.id: s.service_name for s in db.query(Service).all()}

    audit_query = db.query(AuditLog)
    if cutoff is not None:
        audit_query = audit_query.filter(AuditLog.created_at >= cutoff)
    if cutoff_end is not None:
        audit_query = audit_query.filter(AuditLog.created_at <= cutoff_end)
    if server_id is not None:
        audit_query = audit_query.filter(AuditLog.server_id == server_id)

    items = audit_query.order_by(desc(AuditLog.created_at)).limit(limit).all()
    for a in items:
        srv_name = server_map.get(a.server_id) or ""
        tgt = (a.target or "").strip()
        if not srv_name and ":" in tgt:
            possible_host = tgt.split(":", 1)[0].strip()
            if any(possible_host == h for h in server_map.values()):
                srv_name = possible_host
                tgt = tgt.split(":", 1)[1].strip()
        elif srv_name and tgt.startswith(f"{srv_name}:"):
            tgt = tgt[len(srv_name) + 1 :].strip()
        elif tgt.startswith("Server "):
            possible_host = tgt[7:].strip()
            if possible_host in server_map.values():
                if not srv_name:
                    srv_name = possible_host
                tgt = "-"

        for pfx in (
            "blokir ",
            "buka blokir ",
            "buat user ",
            "kunci user ",
            "buka kunci user ",
            "hapus user ",
            "tambah cron ",
            "hapus cron ",
            "tambah path ssl ",
            "hapus path ssl ",
        ):
            if tgt.lower().startswith(pfx):
                tgt = tgt[len(pfx) :].strip()
                break

        if not tgt:
            tgt = "-"

        log_res = (a.result or "").lower()
        if "gagal" in log_res or "failed" in log_res or "error" in log_res or "ditolak" in log_res:
            log_st = "FAILED"
        elif "dikirim" in log_res or "menunggu" in log_res or "proses" in log_res:
            log_st = "PENDING"
        elif a.result:
            log_st = "SUCCESS"
        else:
            log_st = None

        rows.append(
            {
                "t": a.created_at,
                "user": a.username,
                "kind": "log",
                "label": AUDIT_ACTION_LABELS.get(a.action, a.action),
                "key": a.action,
                "server": srv_name or "-",
                "server_id": a.server_id,
                "target": tgt,
                "status": log_st,
                "result": a.result or "",
            }
        )

    cmd_query = db.query(Command)
    if cutoff is not None:
        cmd_query = cmd_query.filter(Command.created_at >= cutoff)
    if cutoff_end is not None:
        cmd_query = cmd_query.filter(Command.created_at <= cutoff_end)
    if server_id is not None:
        cmd_query = cmd_query.filter(Command.server_id == server_id)

    cmds = cmd_query.order_by(desc(Command.created_at)).limit(limit).all()
    label_map = {
        "restart": "cmd:restart",
        "start": "cmd:start",
        "stop": "cmd:stop",
        "block_ip": "cmd:block_ip",
        "unblock_ip": "cmd:unblock_ip",
        "restart_agent": "cmd:restart_agent",
        "update_agent": "cmd:update_agent",
        "reboot_host": "cmd:reboot_host",
        "poweroff_host": "cmd:poweroff_host",
        "firewall_enable": "cmd:firewall_enable",
        "firewall_disable": "cmd:firewall_disable",
        "firewall_reload": "cmd:firewall_reload",
        "kill_process": "cmd:kill_process",
        "user_create": "cmd:user_create",
        "user_lock": "cmd:user_lock",
        "user_unlock": "cmd:user_unlock",
        "user_delete": "cmd:user_delete",
        "session_terminate": "cmd:session_terminate",
        "cron_add": "cmd:cron_add",
        "cron_toggle": "cmd:cron_toggle",
        "cron_delete": "cmd:cron_delete",
        "cron_run_now": "cmd:cron_run_now",
        "firewall_port_rule": "cmd:firewall_port_rule",
        "ssl_path_add": "cmd:ssl_path_add",
        "ssl_path_remove": "cmd:ssl_path_remove",
    }
    for c in cmds:
        key = label_map.get(c.action, f"cmd:{c.action}")
        srv_name = server_map.get(c.server_id, f"server#{c.server_id}")
        tgt_parts = []
        if c.service_id and c.service_id in svc_map:
            tgt_parts.append(svc_map[c.service_id])
        if c.params:
            try:
                ps = json.loads(c.params)
                if isinstance(ps, dict):
                    if ps.get("ips"):
                        tgt_parts.append(
                            f"{', '.join(str(i) for i in ps['ips'][:3])}{'…' if len(ps['ips']) > 3 else ''}"
                        )
                    elif ps.get("ip"):
                        tgt_parts.append(str(ps["ip"]))
                    elif ps.get("username"):
                        tgt_parts.append(str(ps["username"]))
                    elif ps.get("tty"):
                        tgt_parts.append(f"{ps['tty']}" + (f" ({ps['username']})" if ps.get("username") else ""))
                    elif ps.get("path"):
                        tgt_parts.append(str(ps["path"]))
                    elif ps.get("cron_id"):
                        tgt_parts.append(str(ps["cron_id"]))
                    elif ps.get("port"):
                        tgt_parts.append(str(ps["port"]))
                    elif c.action == "update_agent":
                        ver = ps.get("version") or ""
                        h = ps.get("sha256") or ""
                        h_short = f" (SHA: {h[:8]}…)" if h else ""
                        tgt_parts.append(
                            f"OTA v{ver}{h_short}" if ver else (f"OTA{h_short}" if h_short else "Agen Pantau")
                        )
            except (TypeError, ValueError):
                pass
        if not tgt_parts and c.action in ("restart_agent", "update_agent"):
            tgt = "Agen Pantau"
        else:
            tgt = " · ".join(tgt_parts) if tgt_parts else "-"
        status = (c.status or "").upper()
        short = (c.result or "").strip()
        if len(short) > 160:
            short = short[:160] + "…"
        rows.append(
            {
                "t": c.created_at,
                "user": c.issued_by or "-",
                "kind": "cmd",
                "key": key,
                "label": AUDIT_ACTION_LABELS.get(key, AUDIT_ACTION_LABELS.get(c.action, c.action)),
                "server": srv_name,
                "server_id": c.server_id,
                "target": tgt,
                "status": status,
                "result": short,
            }
        )

    if q:
        rows = [
            r
            for r in rows
            if q in " ".join([r["user"], r["label"], r.get("server", ""), r["target"], r["result"]]).lower()
        ]

    if action:
        matched_keys = set()
        for cat in AUDIT_CATEGORIES:
            if cat["id"] == action:
                matched_keys.update(cat["keys"])
                break
        if not matched_keys:
            matched_keys.add(action)
            matched_keys.add(f"cmd:{action}")
            if action == "firewall_block":
                matched_keys.add("cmd:block_ip")
            elif action == "firewall_unblock":
                matched_keys.add("cmd:unblock_ip")
        rows = [r for r in rows if r["key"] in matched_keys or r["key"].replace("cmd:", "") == action]

    if user_filter:
        rows = [r for r in rows if r["user"].lower() == user_filter.lower()]

    if status_filter:
        rows = [r for r in rows if (r.get("status") or "").upper() == status_filter]

    rows.sort(key=lambda r: r["t"], reverse=True)
    return rows[:limit]
