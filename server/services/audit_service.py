"""Domain service for audit log filtering, command audit merging, and RBAC masking."""

import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from models.command import Command
from models.misc import AuditLog
from models.server import Server, Service
from models.user import User

AUDIT_ACTION_LABELS = {
    "login": "Login",
    "user_login": "Login",
    "login_2fa": "2FA Login",
    "user_login_2fa": "2FA Login",
    "2fa_enable": "Enable 2FA",
    "2fa_disable": "Disable 2FA",
    "2fa_regen_recovery": "Regenerate 2FA Recovery",
    "logout": "Logout",
    "user_logout": "Logout",
    "server_add": "Add Server",
    "server_edit": "Edit Server",
    "update_server": "Edit Server",
    "update_server_note": "Update Server Note",
    "server_notes_update": "Update Server Note",
    "inject_key": "Inject SSH Key",
    "server_delete": "Delete Server",
    "delete_server": "Delete Server",
    "key_regenerate": "Regenerate Key",
    "service_add": "Add Service",
    "service_delete": "Delete Service",
    "service_core_toggle": "Toggle Core Service",
    "service_recovered": "Service Recovered",
    "user_add": "Add User",
    "user_create": "Add User",
    "cmd:user_create": "Add User",
    "user_delete": "Delete User",
    "cmd:user_delete": "Delete User",
    "user_update": "Update User",
    "user_edit": "Update User",
    "user_edit_perms": "Update User Permissions",
    "user_toggle_active": "Toggle User Status",
    "user_lock": "Lock User",
    "cmd:user_lock": "Lock User",
    "user_unlock": "Unlock User",
    "cmd:user_unlock": "Unlock User",
    "change_password": "Change Password",
    "user_password_change": "Change Password",
    "user_password_reset": "Reset User Password",
    "user_2fa_reset": "Reset User 2FA",
    "settings_update": "Update Settings",
    "settings_reset": "Reset Settings",
    "branding_update": "Update Branding",
    "db_optimize": "Optimize Database",
    "apt_update": "Update OS Packages (apt)",
    "cmd:apt_update": "Update OS Packages (apt)",
    "apt_upgrade": "Upgrade OS Packages (apt)",
    "cmd:apt_upgrade": "Upgrade OS Packages (apt)",
    "apt_upgrade_interact": "Interactive OS Upgrade (apt)",
    "apt_pkg_upgrade": "Upgrade Specific Package (apt)",
    "apt_pkg_clear_cache": "Clear APT Cache",
    "apt_fix": "Repair APT/DPKG",
    "alert_ack": "Acknowledge Incident",
    "alert_unack": "Reopen Incident",
    "ack_problem": "Acknowledge Incident",
    "problem_ack": "Acknowledge Incident",
    "problem_unack": "Reopen Incident",
    "problem_ignore": "Ignore Incident",
    "problem_unignore": "Cancel Ignore Incident",
    "problem_resolve": "Resolve Incident",
    "incident_detected": "Incident Detected",
    "incident_resolved": "Incident Resolved",
    "masalah_terdeteksi": "Incident Detected",
    "masalah_selesai": "Incident Resolved",
    "masalah_pulih": "Incident Resolved",
    "masalah_danger": "Danger Incident",
    "masalah_average": "Critical Incident",
    "masalah_warning": "Warning Incident",
    "masalah_info": "Info Incident",
    "eskalasi_insiden": "Incident Escalated",
    "proxmox_ha_detected": "Proxmox HA Detected",
    "probe_add": "Add Endpoint Probe",
    "custom_check": "Custom Check",
    "cmd:custom_check": "Custom Check",
    "update_thresholds": "Update Thresholds",
    "maintenance_mode": "Maintenance Mode",
    "maintenance_create": "Create Maintenance Window",
    "maintenance_complete": "Complete Maintenance Window",
    "maintenance_delete": "Delete Maintenance Window",
    "restart": "Restart Service",
    "restart_service": "Restart Service",
    "cmd:restart": "Restart Service",
    "cmd:restart_service": "Restart Service",
    "start": "Start Service",
    "start_service": "Start Service",
    "service_start": "Start Service",
    "systemd_start": "Start Service",
    "cmd:start": "Start Service",
    "cmd:start_service": "Start Service",
    "stop": "Stop Service",
    "stop_service": "Stop Service",
    "service_stop": "Stop Service",
    "systemd_stop": "Stop Service",
    "cmd:stop": "Stop Service",
    "cmd:stop_service": "Stop Service",
    "reload": "Reload Service",
    "cmd:reload": "Reload Service",
    "reload_service": "Reload Service",
    "systemd_reload": "Reload Service",
    "cmd:reload_service": "Reload Service",
    "block_ip": "Block IP",
    "firewall_block": "Block IP",
    "cmd:block_ip": "Block IP",
    "unblock_ip": "Unblock IP",
    "firewall_unblock": "Unblock IP",
    "cmd:unblock_ip": "Unblock IP",
    "toggle_ufw": "Toggle Firewall (UFW)",
    "ufw_enable": "Enable Firewall",
    "cmd:ufw_enable": "Enable Firewall",
    "ufw_disable": "Disable Firewall",
    "cmd:ufw_disable": "Disable Firewall",
    "ufw_reload": "Reload Firewall",
    "cmd:ufw_reload": "Reload Firewall",
    "kill_process": "Signal / Kill Process",
    "cmd:kill_process": "Signal / Kill Process",
    "terminate_ssh_session": "Terminate SSH Session",
    "cmd:terminate_ssh_session": "Terminate SSH Session",
    "terminate_session": "Terminate SSH Session",
    "cmd:terminate_session": "Terminate SSH Session",
    "putus_sesi_ssh": "Terminate SSH Session",
    "terminal_exec": "Terminal Command",
    "terminal_open": "Open Terminal",
    "terminal_close": "Close Terminal",
    "terminal_detach": "Detach Terminal",
    "terminal_reconnect": "Reconnect Terminal",
    "terminal_shell_open": "Open Root Terminal",
    "terminal_unlock": "Unlock Terminal",
    "terminal_unlock_fail": "Terminal Unlock Failed",
    "terminal_lock": "Lock Terminal",
    "terminal_connect": "Terminal Connected",
    "terminal_disconnect": "Terminal Disconnected",
    "file_manager_unlock": "Unlock File Manager",
    "file_manager_unlock_fail": "File Manager Unlock Failed",
    "file_manager_lock": "Lock File Manager",
    "file_save": "Save / Edit File",
    "file_touch": "Create File",
    "file_upload": "Upload File",
    "file_rm": "Delete File / Folder",
    "file_batch_rm": "Batch Delete Files",
    "file_delete": "Delete File / Folder",
    "file_mkdir": "Create Folder",
    "file_rename": "Rename File",
    "file_chmod": "Change Permissions",
    "file_chown": "Change Owner",
    "file_copy": "Copy File",
    "file_move": "Move File",
    "file_duplicate": "Duplicate File",
    "cron_run": "Run Cron Job",
    "cmd:cron_run": "Run Cron Job",
    "cron_run_now": "Run Cron Job",
    "cmd:cron_run_now": "Run Cron Job",
    "cron_add": "Add Cron Job",
    "cmd:cron_add": "Add Cron Job",
    "cron_toggle": "Toggle Cron Job",
    "cmd:cron_toggle": "Toggle Cron Job",
    "cron_delete": "Delete Cron Job",
    "cmd:cron_delete": "Delete Cron Job",
    "fim_scan": "FIM Verification Scan",
    "cmd:fim_scan": "FIM Verification Scan",
    "fim_rebaseline": "FIM Rebaseline",
    "cmd:fim_rebaseline": "FIM Rebaseline",
    "fim_path_add": "Add FIM Path",
    "cmd:fim_path_add": "Add FIM Path",
    "fim_path_remove": "Remove FIM Path",
    "cmd:fim_path_remove": "Remove FIM Path",
    "fim_event_ack_all": "Acknowledge All FIM Events",
    "reboot_host": "Reboot Host",
    "cmd:reboot_host": "Reboot Host",
    "poweroff_host": "Power Off Host",
    "cmd:poweroff_host": "Power Off Host",
    "update_agent": "Agent Update (OTA)",
    "cmd:update_agent": "Agent Update (OTA)",
    "agent_update": "Agent Update (OTA)",
    "ota_update": "Agent Update (OTA)",
    "cmd:ota_update": "Agent Update (OTA)",
    "ota_upgrade": "Agent Upgrade (OTA)",
    "cmd:ota_upgrade": "Agent Upgrade (OTA)",
    "restart_agent": "Restart Agent",
    "cmd:restart_agent": "Restart Agent",
}

AUDIT_CATEGORIES = [
    {
        "id": "cat:auth",
        "name": "Auth & User Accounts",
        "keys": [
            "login", "user_login", "login_2fa", "user_login_2fa", "logout", "user_logout",
            "user_add", "user_update", "user_delete", "user_password_change",
            "user_password_reset", "user_2fa_reset",
            "user_create", "cmd:user_create", "user_lock", "cmd:user_lock",
            "user_unlock", "cmd:user_unlock", "terminate_ssh_session", "cmd:terminate_ssh_session",
            "session_terminate", "cmd:session_terminate", "terminate_session", "cmd:terminate_session",
            "putus_sesi_ssh",
        ],
        "actions": [
            ("login", "Login"),
            ("login_2fa", "2FA Login"),
            ("logout", "Logout"),
            ("user_add", "Add User"),
            ("user_update", "Update User"),
            ("user_delete", "Delete User"),
            ("user_password_change", "Change Password"),
            ("user_password_reset", "Reset User Password"),
            ("user_2fa_reset", "Reset User 2FA"),
            ("terminate_ssh_session", "Terminate SSH Session"),
        ],
    },
    {
        "id": "cat:service",
        "name": "Services & Processes",
        "keys": [
            "restart", "restart_service", "cmd:restart", "cmd:restart_service",
            "start", "start_service", "cmd:start", "cmd:start_service",
            "stop", "stop_service", "cmd:stop", "cmd:stop_service",
            "reload_service", "cmd:reload_service",
            "service_add", "service_delete", "kill_process", "cmd:kill_process",
        ],
        "actions": [
            ("restart_service", "Restart Service"),
            ("start_service", "Start Service"),
            ("stop_service", "Stop Service"),
            ("reload_service", "Reload Service"),
            ("kill_process", "Signal / Kill Process"),
        ],
    },
    {
        "id": "cat:firewall",
        "name": "Firewall & Security",
        "keys": [
            "block_ip", "firewall_block", "cmd:block_ip",
            "unblock_ip", "firewall_unblock", "cmd:unblock_ip",
            "toggle_ufw", "ufw_enable", "cmd:ufw_enable", "ufw_disable", "cmd:ufw_disable",
            "ufw_reload", "cmd:ufw_reload",
            "fim_scan", "cmd:fim_scan", "fim_rebaseline", "cmd:fim_rebaseline",
        ],
        "actions": [
            ("block_ip", "Block IP"),
            ("unblock_ip", "Unblock IP"),
            ("ufw_enable", "Enable Firewall"),
            ("ufw_disable", "Disable Firewall"),
            ("ufw_reload", "Reload Firewall"),
            ("fim_scan", "FIM Verification Scan"),
            ("fim_rebaseline", "FIM Rebaseline"),
        ],
    },
    {
        "id": "cat:files",
        "name": "Files & File Manager",
        "keys": [
            "file_manager_unlock", "file_manager_lock", "file_save", "file_touch",
            "file_upload", "file_rm", "file_delete", "file_mkdir", "file_rename",
            "file_chmod", "file_chown", "file_copy", "file_move", "file_duplicate",
        ],
        "actions": [
            ("file_save", "Save / Edit File"),
            ("file_touch", "Create File"),
            ("file_upload", "Upload File"),
            ("file_delete", "Delete File / Folder"),
            ("file_mkdir", "Create Folder"),
            ("file_rename", "Rename File"),
            ("file_chmod", "Change Permissions"),
            ("file_copy", "Copy File"),
            ("file_move", "Move File"),
        ],
    },
    {
        "id": "cat:cron",
        "name": "Cron Jobs",
        "keys": [
            "cron_run", "cmd:cron_run", "cron_add", "cmd:cron_add",
            "cron_toggle", "cmd:cron_toggle", "cron_delete", "cmd:cron_delete",
        ],
        "actions": [
            ("cron_run", "Run Cron Job"),
            ("cron_add", "Add Cron Job"),
            ("cron_toggle", "Toggle Cron Job"),
            ("cron_delete", "Delete Cron Job"),
        ],
    },
    {
        "id": "cat:apt",
        "name": "OS Updates (APT)",
        "keys": ["apt_update", "cmd:apt_update", "apt_upgrade", "cmd:apt_upgrade"],
        "actions": [
            ("apt_update", "Update OS Packages (apt)"),
            ("apt_upgrade", "Upgrade OS Packages (apt)"),
        ],
    },
    {
        "id": "cat:server",
        "name": "Server, Terminal & Incidents",
        "keys": [
            "server_add", "server_edit", "update_server", "update_server_note", "inject_key",
            "server_delete", "delete_server", "key_regenerate",
            "maintenance_mode", "update_thresholds", "alert_ack", "ack_problem",
            "problem_ack", "problem_unack", "problem_ignore", "problem_unignore",
            "masalah_terdeteksi", "masalah_selesai",
            "terminal_exec", "terminal_unlock", "terminal_unlock_fail", "terminal_lock",
            "terminal_connect", "terminal_disconnect",
            "reboot_host", "cmd:reboot_host", "poweroff_host", "cmd:poweroff_host",
            "update_agent", "cmd:update_agent", "restart_agent", "cmd:restart_agent",
        ],
        "actions": [
            ("update_server", "Edit Server"),
            ("update_server_note", "Update Server Note"),
            ("inject_key", "Inject SSH Key"),
            ("delete_server", "Delete Server"),
            ("maintenance_mode", "Maintenance Mode"),
            ("update_thresholds", "Update Thresholds"),
            ("alert_ack", "Acknowledge Incident"),
            ("problem_unack", "Reopen Incident"),
            ("problem_ignore", "Ignore Incident"),
            ("problem_unignore", "Cancel Ignore Incident"),
            ("masalah_terdeteksi", "Incident Detected"),
            ("masalah_selesai", "Incident Resolved"),
            ("terminal_connect", "Terminal Connected"),
            ("terminal_exec", "Terminal Command"),
            ("reboot_host", "Reboot Host"),
            ("poweroff_host", "Power Off Host"),
            ("update_agent", "Agent Update (OTA)"),
            ("restart_agent", "Restart Agent"),
        ],
    },
    {
        "id": "cat:system",
        "name": "System & Settings",
        "keys": ["settings_update", "settings_reset", "db_optimize"],
        "actions": [
            ("settings_update", "Update Settings"),
            ("settings_reset", "Reset Settings"),
            ("db_optimize", "Optimize Database"),
        ],
    },
]

_ACTION_ALIASES = {
    "restart_service": {"restart", "restart_service", "cmd:restart", "cmd:restart_service"},
    "start_service": {"start", "start_service", "cmd:start", "cmd:start_service"},
    "stop_service": {"stop", "stop_service", "cmd:stop", "cmd:stop_service"},
    "reload_service": {"reload_service", "cmd:reload_service"},
    "block_ip": {"block_ip", "firewall_block", "cmd:block_ip"},
    "unblock_ip": {"unblock_ip", "firewall_unblock", "cmd:unblock_ip"},
    "update_server": {"server_edit", "update_server"},
    "delete_server": {"server_delete", "delete_server"},
    "file_delete": {"file_rm", "file_delete"},
    "alert_ack": {"alert_ack", "ack_problem", "problem_ack"},
    "terminate_ssh_session": {
        "terminate_ssh_session", "cmd:terminate_ssh_session",
        "session_terminate", "cmd:session_terminate",
        "terminate_session", "cmd:terminate_session", "putus_sesi_ssh",
    },
}


def _compute_time_window(period: str, start_date: str, end_date: str):
    """Compute UTC lower and upper bounds from period or custom YYYY-MM-DD dates."""
    now_utc = datetime.utcnow()
    cutoff_start: Optional[datetime] = None
    cutoff_end: Optional[datetime] = None

    p = (period or "all").strip().lower()
    if start_date or end_date:
        try:
            if start_date:
                cutoff_start = datetime.fromisoformat(start_date.strip()[:10])
            if end_date:
                cutoff_end = datetime.fromisoformat(end_date.strip()[:10]).replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            return cutoff_start, cutoff_end
        except ValueError:
            pass

    if p == "24h":
        cutoff_start = now_utc - timedelta(hours=24)
    elif p == "today":
        cutoff_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    elif p == "7d":
        cutoff_start = now_utc - timedelta(days=7)
    elif p == "30d":
        cutoff_start = now_utc - timedelta(days=30)
    return cutoff_start, cutoff_end


def _normalize_status(raw_result: Optional[str], raw_cmd_status: Optional[str] = None) -> str:
    """Normalize result/command status into SUCCESS, FAILED, EXECUTING, or PENDING."""
    if raw_cmd_status:
        st = raw_cmd_status.strip().lower()
        if st in ("executed", "success"):
            return "SUCCESS"
        if st in ("failed", "canceled", "cancelled", "error"):
            return "FAILED"
        if st == "executing":
            return "EXECUTING"
        if st in ("pending", "queued"):
            return "PENDING"

    res_low = (raw_result or "").strip().lower()
    if any(w in res_low for w in ("gagal", "fail", "error", "ditolak", "denied")):
        return "FAILED"
    if "executing" in res_low or "proses" in res_low:
        return "EXECUTING"
    if any(w in res_low for w in ("pending", "antre", "menunggu", "queued")):
        return "PENDING"
    return "SUCCESS"


def _extract_command_target(cmd: Command, svc_map: Optional[dict[int, str]] = None) -> str:
    """Extract readable target parameter from Command service relation and JSON params."""
    parts: list[str] = []
    if svc_map and cmd.service_id and cmd.service_id in svc_map:
        parts.append(svc_map[cmd.service_id])

    if cmd.params:
        try:
            ps = json.loads(cmd.params)
            if isinstance(ps, dict):
                if ps.get("ips") and isinstance(ps["ips"], list):
                    ips = [str(i) for i in ps["ips"][:3]]
                    parts.append(", ".join(ips) + ("..." if len(ps["ips"]) > 3 else ""))
                elif ps.get("pid") is not None:
                    pid_str = f"PID {ps['pid']}" + (f" ({ps['pname']})" if ps.get("pname") else "")
                    if ps.get("signal"):
                        pid_str += f" [{ps['signal']}]"
                    parts.append(pid_str)
                elif ps.get("tty"):
                    tty_str = str(ps["tty"]) + (f" ({ps['username']})" if ps.get("username") else "")
                    parts.append(tty_str)
                elif ps.get("port"):
                    proto = f"/{ps['proto']}" if ps.get("proto") else ""
                    parts.append(f"{ps['port']}{proto}")
                elif cmd.action == "update_agent":
                    ver = ps.get("version") or ""
                    parts.append(f"OTA v{ver}" if ver else "Pantau Agent")
                else:
                    for key in ("name", "unit", "ip", "username", "path", "command", "cron_id", "version"):
                        val = ps.get(key)
                        if val is not None and str(val).strip():
                            val_s = str(val).strip()
                            if val_s not in parts:
                                parts.append(val_s)
                            break
            if not parts and cmd.action not in ("restart_agent", "update_agent"):
                return "-"
        except (TypeError, ValueError):
            if not parts:
                return str(cmd.params)[:120]

    if not parts and cmd.action in ("restart_agent", "update_agent"):
        return "Pantau Agent"
    return " · ".join(parts) if parts else "-"


_LEGACY_RESULT_MAP = {
    "kembali aktif (pulih)": "Service recovered (active)",
    "berhasil": "Success",
    "gagal": "Failed",
    "selesai": "Completed",
    "antre": "Queued",
    "terdeteksi": "Detected",
    "aktif": "Active",
    "dikirim ke agen": "Dispatched to agent",
    "diselesaikan manual": "Manually resolved",
    "pemantauan diaktifkan kembali": "Monitoring resumed",
    "mode pemeliharaan dinonaktifkan": "Maintenance mode disabled",
    "ditolak: terdaftar di proxmox ha": "Rejected: Protected by Proxmox HA",
    "berhasil (sesi lain dicabut)": "Success (other sessions revoked)",
}


def _translate_legacy_result(raw: Optional[str]) -> str:
    """Normalize historical or agent-emitted Indonesian audit strings into English."""
    text = (raw or "").strip()
    if not text:
        return "SUCCESS"
    low = text.lower()
    if low in _LEGACY_RESULT_MAP:
        return _LEGACY_RESULT_MAP[low]
    if low.startswith("aksi tidak dikenal oleh agen ini"):
        m = re.search(r"\('([^']+)'\)", text)
        act = m.group(1) if m else "action"
        return f"Unsupported action '{act}' on installed agent version — upgrade agent required"
    if low.startswith("restart agen"):
        return "Agent restart scheduled (systemd will restart daemon)"
    if low.startswith("mode pemeliharaan diaktifkan"):
        return re.sub(r"(?i)^mode pemeliharaan diaktifkan", "Maintenance mode enabled", text).replace("alasan:", "reason:")
    if low.startswith("perintah diterima: server akan di-matikan"):
        return "Command accepted: host power off scheduled in ~4s"
    if low.startswith("perintah diterima: server akan di-reboot"):
        return "Command accepted: host reboot scheduled in ~4s"
    if low.startswith("perintah reboot dibatalkan"):
        return "Reboot cancelled: systemd is not running as PID 1"
    if low.startswith("perintah poweroff dibatalkan"):
        return "Power off cancelled: systemd is not running as PID 1"
    if low.startswith("optimasi ") and low.endswith(" selesai"):
        return re.sub(r"(?i)^optimasi (.+) selesai$", r"Optimized \1", text)
    if low.startswith("push ota sukses ke "):
        m = re.search(r"v([\d.]+)", text)
        ver = m.group(1) if m else ""
        return f"OTA push to v{ver} succeeded (SHA-256 verified). Agent restart scheduled."
    if low.startswith("pembaruan agen ke ") and "terverifikasi" in low:
        m = re.search(r"v([\d.]+)", text)
        ver = m.group(1) if m else ""
        return f"Agent update to v{ver} verified via telemetry."
    if low.startswith("gagal:"):
        return "Failed:" + text[6:]
    if low.startswith("berhasil (") and text.endswith(")"):
        return "Success " + text[9:]
    return text


def _resolve_action_keys(action: str) -> set[str]:
    """Expand category IDs (cat:*) or action keys into matching action keys."""
    act = (action or "").strip()
    if not act:
        return set()
    for cat in AUDIT_CATEGORIES:
        if cat["id"] == act:
            return set(cat["keys"])
    if act in _ACTION_ALIASES:
        return set(_ACTION_ALIASES[act])
    return {act, f"cmd:{act}", act.removeprefix("cmd:")}


def _mask_master_admin(items: list[dict], master_names: set[str]) -> list[dict]:
    """Apply Zero-Knowledge Master Admin masking across all returned audit fields."""
    patterns = [re.compile(re.escape(m), re.IGNORECASE) for m in master_names if m]
    role_re = re.compile(r"master[-_]admin", re.IGNORECASE)
    lower_masters = {m.lower() for m in master_names if m}

    for item in items:
        if (item.get("username") or "").lower() in lower_masters:
            item["username"] = "System"
        for field in ("target", "result_detail", "meta"):
            val = item.get(field)
            if not val:
                continue
            text = str(val)
            for pat in patterns:
                text = pat.sub("System", text)
            text = role_re.sub("system", text)
            item[field] = text
    return items


def query_audit_entries_with_meta(
    db: Session,
    user_actor: User,
    q: str = "",
    action: str = "",
    user_filter: str = "",
    period: str = "24h",
    start_date: str = "",
    end_date: str = "",
    server_id: Optional[int] = None,
    status_filter: str = "",
    limit: int = 200,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Query AuditLog + Command history with SQL push-down, RBAC isolation, and count metadata."""
    allowed_sids = user_actor.get_allowed_server_ids()
    if allowed_sids is not None and server_id is not None and server_id not in allowed_sids:
        return [], 0, False

    master_names: set[str] = set()
    if not user_actor.is_master_admin:
        master_names = {
            u.username for u in db.query(User).filter(User.role.in_(["master_admin", "master-admin"])).all()
        }
        if user_filter.strip().lower() in {m.lower() for m in master_names}:
            return [], 0, False

    cutoff_start, cutoff_end = _compute_time_window(period, start_date, end_date)
    server_map = {s.id: s.hostname for s in db.query(Server).all()}
    svc_map = {s.id: s.service_name for s in db.query(Service).all()}

    kw = q.strip().lower()
    matching_sids = [sid for sid, hname in server_map.items() if kw and kw in (hname or "").lower()]
    push_kw_sql = bool(kw and kw not in "system" and (user_actor.is_master_admin or not any(kw in m.lower() for m in master_names)))

    # 1. AuditLog rows
    log_q = db.query(AuditLog)
    if cutoff_start:
        log_q = log_q.filter(AuditLog.created_at >= cutoff_start)
    if cutoff_end:
        log_q = log_q.filter(AuditLog.created_at <= cutoff_end)
    if allowed_sids is not None:
        log_q = log_q.filter(AuditLog.server_id.in_(allowed_sids))
    if server_id is not None:
        log_q = log_q.filter(AuditLog.server_id == server_id)
    if user_filter.strip() and user_filter.strip().lower() not in ("system", "sistem"):
        log_q = log_q.filter(func.lower(AuditLog.username) == user_filter.strip().lower())
    if action.strip():
        matched_keys = _resolve_action_keys(action)
        plain_keys = [k.removeprefix("cmd:") for k in matched_keys]
        log_q = log_q.filter(AuditLog.action.in_(matched_keys | set(plain_keys)))
    if push_kw_sql:
        like_pat = f"%{kw}%"
        log_conds = [
            AuditLog.username.ilike(like_pat),
            AuditLog.action.ilike(like_pat),
            AuditLog.target.ilike(like_pat),
            AuditLog.result.ilike(like_pat),
        ]
        if matching_sids:
            log_conds.append(AuditLog.server_id.in_(matching_sids))
        log_q = log_q.filter(or_(*log_conds))

    fetch_cap = min(max(limit * 3, 400), 2000)
    audit_records = log_q.order_by(desc(AuditLog.created_at)).limit(fetch_cap).all()

    rows: list[dict[str, Any]] = []
    for r in audit_records:
        srv_name = server_map.get(r.server_id) or ("Control Host" if not r.server_id else f"#{r.server_id}")
        raw_user = (r.username or "-").strip()
        norm_user = "System" if raw_user.lower() in ("sistem", "system") else raw_user
        rows.append({
            "id": f"log-{r.id}",
            "_ts": r.created_at or datetime.min,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "-",
            "username": norm_user,
            "server_id": r.server_id,
            "server_name": srv_name,
            "action": r.action or "-",
            "action_label": AUDIT_ACTION_LABELS.get(r.action, r.action or "-"),
            "target": r.target or "-",
            "result": _normalize_status(r.result),
            "result_detail": _translate_legacy_result(r.result),
            "kind": "log",
            "meta": r.meta,
        })

    # 2. Remote Command execution rows
    cmd_q = db.query(Command)
    if cutoff_start:
        cmd_q = cmd_q.filter(Command.created_at >= cutoff_start)
    if cutoff_end:
        cmd_q = cmd_q.filter(Command.created_at <= cutoff_end)
    if allowed_sids is not None:
        cmd_q = cmd_q.filter(Command.server_id.in_(allowed_sids))
    if server_id is not None:
        cmd_q = cmd_q.filter(Command.server_id == server_id)
    if user_filter.strip() and user_filter.strip().lower() not in ("system", "sistem"):
        cmd_q = cmd_q.filter(func.lower(Command.issued_by) == user_filter.strip().lower())
    if action.strip():
        matched_keys = _resolve_action_keys(action)
        plain_keys = [k.removeprefix("cmd:") for k in matched_keys]
        cmd_q = cmd_q.filter(Command.action.in_(matched_keys | set(plain_keys)))
    if status_filter.strip():
        st_up = status_filter.strip().upper()
        cmd_status_map = {
            "SUCCESS": ("executed", "success"),
            "FAILED": ("failed", "canceled", "cancelled", "error"),
            "EXECUTING": ("executing",),
            "PENDING": ("pending", "queued"),
        }
        if st_up in cmd_status_map:
            cmd_q = cmd_q.filter(func.lower(Command.status).in_(cmd_status_map[st_up]))
    if push_kw_sql:
        like_pat = f"%{kw}%"
        cmd_conds = [
            Command.issued_by.ilike(like_pat),
            Command.action.ilike(like_pat),
            Command.params.ilike(like_pat),
            Command.result.ilike(like_pat),
        ]
        if matching_sids:
            cmd_conds.append(Command.server_id.in_(matching_sids))
        cmd_q = cmd_q.filter(or_(*cmd_conds))

    cmd_records = cmd_q.order_by(desc(Command.created_at)).limit(fetch_cap).all()
    for c in cmd_records:
        key = f"cmd:{c.action}"
        srv_name = server_map.get(c.server_id) or f"#{c.server_id}"
        res_text = _translate_legacy_result(c.result) if (c.result or "").strip() else ""
        if len(res_text) > 160:
            res_text = res_text[:160] + "..."
        raw_user = (c.issued_by or "-").strip()
        norm_user = "System" if raw_user.lower() in ("sistem", "system") else raw_user
        rows.append({
            "id": f"cmd-{c.id}",
            "_ts": c.created_at or datetime.min,
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "-",
            "username": norm_user,
            "server_id": c.server_id,
            "server_name": srv_name,
            "action": key,
            "action_label": AUDIT_ACTION_LABELS.get(key, AUDIT_ACTION_LABELS.get(c.action, c.action or "-")),
            "target": _extract_command_target(c, svc_map),
            "result": _normalize_status(c.result, c.status),
            "result_detail": res_text or (c.status or "SUCCESS").upper(),
            "kind": "cmd",
            "meta": None,
        })

    if not user_actor.is_master_admin and master_names:
        _mask_master_admin(rows, master_names)

    if user_filter.strip():
        u_low = user_filter.strip().lower()
        rows = [r for r in rows if r["username"].lower() == u_low]

    if action.strip():
        matched_keys = _resolve_action_keys(action)
        rows = [
            r for r in rows
            if r["action"] in matched_keys or r["action"].removeprefix("cmd:") in matched_keys
        ]

    if status_filter.strip():
        st_up = status_filter.strip().upper()
        rows = [r for r in rows if r["result"] == st_up]

    if kw:
        rows = [
            r for r in rows
            if kw in f"{r['username']} {r['server_name']} {r['action']} {r['action_label']} {r['target']} {r['result_detail']} {r['meta'] or ''}".lower()
        ]

    rows.sort(key=lambda x: x["_ts"], reverse=True)
    for r in rows:
        r.pop("_ts", None)

    total_count = len(rows)
    truncated = total_count > limit or len(audit_records) >= fetch_cap or len(cmd_records) >= fetch_cap
    return rows[:limit], total_count, truncated


def query_audit_entries(
    db: Session,
    user_actor: User,
    q: str = "",
    action: str = "",
    user_filter: str = "",
    period: str = "24h",
    start_date: str = "",
    end_date: str = "",
    server_id: Optional[int] = None,
    status_filter: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Backward-compatible list wrapper returning audit rows."""
    rows, _, _ = query_audit_entries_with_meta(
        db=db,
        user_actor=user_actor,
        q=q,
        action=action,
        user_filter=user_filter,
        period=period,
        start_date=start_date,
        end_date=end_date,
        server_id=server_id,
        status_filter=status_filter,
        limit=limit,
    )
    return rows


def get_audit_metadata(db: Session, user_actor: User) -> dict[str, Any]:
    """Return available users (Zero-Knowledge safe), accessible servers, and action categories."""
    if user_actor.is_master_admin:
        users = [u.username for u in db.query(User).order_by(User.username.asc()).all()]
    else:
        users = [
            u.username
            for u in db.query(User).filter(~User.role.in_(["master_admin", "master-admin"])).order_by(User.username.asc()).all()
        ]
    if "System" not in users:
        users.append("System")

    allowed_sids = user_actor.get_allowed_server_ids()
    srv_q = db.query(Server).filter(Server.is_active == 1).order_by(Server.hostname.asc())
    if allowed_sids is not None:
        srv_q = srv_q.filter(Server.id.in_(allowed_sids))
    servers = [{"id": s.id, "hostname": s.hostname, "group_name": s.group_name or ""} for s in srv_q.all()]

    categories = [
        {
            "id": cat["id"],
            "name": cat["name"],
            "actions": [{"key": k, "label": lbl} for k, lbl in cat["actions"]],
        }
        for cat in AUDIT_CATEGORIES
    ]
    return {"users": users, "servers": servers, "categories": categories}
