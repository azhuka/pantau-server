"""Domain service for audit log filtering, command audit merging, and RBAC masking."""

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from models.command import Command
from models.misc import AuditLog
from models.server import Server
from models.user import User

AUDIT_ACTION_LABELS = {
    "login": "Login",
    "login_2fa": "2FA Login",
    "logout": "Logout",
    "server_add": "Add Server",
    "server_edit": "Edit Server",
    "update_server": "Edit Server",
    "server_delete": "Delete Server",
    "key_regenerate": "Regenerate Key",
    "service_add": "Add Service",
    "service_delete": "Delete Service",
    "user_add": "Add User",
    "user_delete": "Delete User",
    "user_update": "Update User",
    "apt_update": "Update OS Packages (apt)",
    "apt_upgrade": "Upgrade OS Packages (apt)",
    "alert_ack": "Mark Incident Handled",
    "ack_problem": "Mark Incident Handled",
    "problem_ignore": "Ignore Incident",
    "problem_unignore": "Cancel Ignore Incident",
    "update_thresholds": "Update Thresholds",
    "maintenance_mode": "Maintenance Mode",
    "restart": "Restart Service",
    "restart_service": "Restart Service",
    "cmd:restart": "Restart Service",
    "cmd:restart_service": "Restart Service",
    "start": "Start Service",
    "start_service": "Start Service",
    "cmd:start": "Start Service",
    "cmd:start_service": "Start Service",
    "stop": "Stop Service",
    "stop_service": "Stop Service",
    "cmd:stop": "Stop Service",
    "cmd:stop_service": "Stop Service",
    "reload_service": "Reload Service",
    "cmd:reload_service": "Reload Service",
    "block_ip": "Block IP",
    "firewall_block": "Block IP",
    "cmd:block_ip": "Block IP",
    "unblock_ip": "Unblock IP",
    "firewall_unblock": "Unblock IP",
    "cmd:unblock_ip": "Unblock IP",
    "toggle_ufw": "Toggle Firewall (UFW)",
    "ufw_enable": "Enable Firewall",
    "ufw_disable": "Disable Firewall",
    "ufw_reload": "Reload Firewall",
    "kill_process": "Signal / Kill Process",
    "cmd:kill_process": "Signal / Kill Process",
    "terminate_ssh_session": "Terminate SSH Session",
    "cmd:terminate_ssh_session": "Terminate SSH Session",
    "terminal_exec": "Terminal Command",
    "cron_run": "Run Cron Job",
    "cmd:cron_run": "Run Cron Job",
    "fim_scan": "FIM Verification Scan",
    "cmd:fim_scan": "FIM Verification Scan",
    "fim_rebaseline": "FIM Rebaseline",
    "cmd:fim_rebaseline": "FIM Rebaseline",
    "reboot_host": "Reboot Host",
    "cmd:reboot_host": "Reboot Host",
    "poweroff_host": "Power Off Host",
    "cmd:poweroff_host": "Power Off Host",
    "update_agent": "Agent Update (OTA)",
    "cmd:update_agent": "Agent Update (OTA)",
    "restart_agent": "Restart Agent",
    "cmd:restart_agent": "Restart Agent",
}

AUDIT_CATEGORIES = [
    {
        "id": "cat:auth",
        "name": "Auth & User Accounts",
        "keys": [
            "login", "login_2fa", "logout", "user_add", "user_update", "user_delete",
            "user_create", "cmd:user_create", "user_lock", "cmd:user_lock",
            "user_unlock", "cmd:user_unlock", "terminate_ssh_session", "cmd:terminate_ssh_session",
            "session_terminate", "cmd:session_terminate",
        ],
        "actions": [
            ("login", "Login"),
            ("login_2fa", "2FA Login"),
            ("logout", "Logout"),
            ("user_add", "Add User"),
            ("user_update", "Update User"),
            ("user_delete", "Delete User"),
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
            "toggle_ufw", "ufw_enable", "ufw_disable", "ufw_reload",
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
            "file_manager_unlock", "file_manager_lock", "file_save",
            "file_upload", "file_rm", "file_mkdir", "file_rename", "file_chmod", "file_chown",
        ],
        "actions": [
            ("file_save", "Save / Edit File"),
            ("file_upload", "Upload File"),
            ("file_rm", "Delete File / Folder"),
            ("file_mkdir", "Create Folder"),
            ("file_rename", "Rename File"),
            ("file_chmod", "Change Permissions"),
        ],
    },
    {
        "id": "cat:cron",
        "name": "Cron Jobs",
        "keys": ["cron_run", "cmd:cron_run", "cron_add", "cmd:cron_add", "cron_toggle", "cron_delete"],
        "actions": [
            ("cron_run", "Run Cron Job"),
            ("cron_add", "Add Cron Job"),
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
        "name": "Server & Incidents",
        "keys": [
            "server_add", "server_edit", "update_server", "server_delete", "key_regenerate",
            "maintenance_mode", "update_thresholds", "alert_ack", "ack_problem",
            "problem_ignore", "problem_unignore", "terminal_exec",
            "reboot_host", "cmd:reboot_host", "poweroff_host", "cmd:poweroff_host",
            "update_agent", "cmd:update_agent", "restart_agent", "cmd:restart_agent",
        ],
        "actions": [
            ("update_server", "Edit Server"),
            ("maintenance_mode", "Maintenance Mode"),
            ("update_thresholds", "Update Thresholds"),
            ("alert_ack", "Mark Incident Handled"),
            ("problem_ignore", "Ignore Incident"),
            ("problem_unignore", "Cancel Ignore Incident"),
            ("terminal_exec", "Terminal Command"),
            ("reboot_host", "Reboot Host"),
            ("poweroff_host", "Power Off Host"),
            ("update_agent", "Agent Update (OTA)"),
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
    "alert_ack": {"alert_ack", "ack_problem"},
    "terminate_ssh_session": {"terminate_ssh_session", "cmd:terminate_ssh_session", "session_terminate", "cmd:session_terminate"},
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
    """Normalize result/command status into SUCCESS, FAILED, or PENDING."""
    if raw_cmd_status:
        st = raw_cmd_status.strip().lower()
        if st in ("executed", "success"):
            return "SUCCESS"
        if st in ("failed", "canceled", "cancelled", "error"):
            return "FAILED"
        if st in ("pending", "executing", "queued"):
            return "PENDING"

    res_low = (raw_result or "").strip().lower()
    if any(w in res_low for w in ("gagal", "fail", "error", "ditolak", "denied")):
        return "FAILED"
    if any(w in res_low for w in ("pending", "antre", "menunggu", "queued", "executing")):
        return "PENDING"
    return "SUCCESS"


def _extract_command_target(cmd: Command) -> str:
    """Extract readable target parameter from Command JSON params."""
    if not cmd.params:
        return "Pantau Agent" if cmd.action in ("restart_agent", "update_agent") else "-"
    try:
        ps = json.loads(cmd.params)
        if isinstance(ps, dict):
            for key in ("name", "unit", "ip", "username", "tty", "path", "command", "pid", "version"):
                if ps.get(key) is not None and str(ps.get(key)).strip():
                    val = str(ps[key]).strip()
                    if key == "pid":
                        return f"PID {val}" + (f" ({ps['pname']})" if ps.get("pname") else "")
                    if key == "tty" and ps.get("username"):
                        return f"{val} ({ps['username']})"
                    return val
    except (TypeError, ValueError):
        pass
    return str(cmd.params)[:120]


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
    """Apply Zero-Knowledge Master Admin masking across returned audit rows."""
    for item in items:
        if item["username"] in master_names:
            item["username"] = "System"
        tgt = str(item.get("target") or "")
        for m in master_names:
            if m in tgt:
                tgt = tgt.replace(m, "System")
        item["target"] = tgt.replace("master_admin", "system").replace("master-admin", "system")
    return items


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
    """Query AuditLog + Command history with multi-criteria filtering and RBAC isolation."""
    allowed_sids = user_actor.get_allowed_server_ids()
    if allowed_sids is not None and server_id is not None and server_id not in allowed_sids:
        return []

    master_names: set[str] = set()
    if not user_actor.is_master_admin:
        master_names = {
            u.username for u in db.query(User).filter(User.role.in_(["master_admin", "master-admin"])).all()
        }
        if user_filter.strip() in master_names:
            return []

    cutoff_start, cutoff_end = _compute_time_window(period, start_date, end_date)
    server_map = {s.id: s.hostname for s in db.query(Server).all()}

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

    fetch_cap = min(max(limit * 3, 300), 1500)
    audit_records = log_q.order_by(desc(AuditLog.created_at)).limit(fetch_cap).all()

    rows: list[dict[str, Any]] = []
    for r in audit_records:
        srv_name = server_map.get(r.server_id) or ("Control Host" if not r.server_id else f"#{r.server_id}")
        rows.append({
            "id": f"log-{r.id}",
            "_ts": r.created_at or datetime.min,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "-",
            "username": r.username or "-",
            "server_id": r.server_id,
            "server_name": srv_name,
            "action": r.action or "-",
            "action_label": AUDIT_ACTION_LABELS.get(r.action, r.action or "-"),
            "target": r.target or "-",
            "result": _normalize_status(r.result),
            "result_detail": r.result or "SUCCESS",
            "kind": "log",
            "meta": r.meta,
        })

    # 2. Remote Command execution rows (if scoped or general)
    cmd_q = db.query(Command)
    if cutoff_start:
        cmd_q = cmd_q.filter(Command.created_at >= cutoff_start)
    if cutoff_end:
        cmd_q = cmd_q.filter(Command.created_at <= cutoff_end)
    if allowed_sids is not None:
        cmd_q = cmd_q.filter(Command.server_id.in_(allowed_sids))
    if server_id is not None:
        cmd_q = cmd_q.filter(Command.server_id == server_id)

    for c in cmd_q.order_by(desc(Command.created_at)).limit(fetch_cap).all():
        key = f"cmd:{c.action}"
        srv_name = server_map.get(c.server_id) or f"#{c.server_id}"
        res_text = (c.result or "").strip()
        if len(res_text) > 160:
            res_text = res_text[:160] + "..."
        rows.append({
            "id": f"cmd-{c.id}",
            "_ts": c.created_at or datetime.min,
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "-",
            "username": c.issued_by or "-",
            "server_id": c.server_id,
            "server_name": srv_name,
            "action": key,
            "action_label": AUDIT_ACTION_LABELS.get(key, AUDIT_ACTION_LABELS.get(c.action, c.action or "-")),
            "target": _extract_command_target(c),
            "result": _normalize_status(res_text, c.status),
            "result_detail": res_text or (c.status or "SUCCESS"),
            "kind": "cmd",
            "meta": None,
        })

    if not user_actor.is_master_admin and master_names:
        _mask_master_admin(rows, master_names)

    # Apply exact multi-criteria filters
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

    if q.strip():
        kw = q.strip().lower()
        rows = [
            r for r in rows
            if kw in f"{r['username']} {r['server_name']} {r['action']} {r['action_label']} {r['target']} {r['result_detail']}".lower()
        ]

    rows.sort(key=lambda x: x["_ts"], reverse=True)
    for r in rows:
        r.pop("_ts", None)
    return rows[:limit]


def get_audit_metadata(db: Session, user_actor: User) -> dict[str, Any]:
    """Return available users (Zero-Knowledge safe), accessible servers, and action categories."""
    if user_actor.is_master_admin:
        users = [u.username for u in db.query(User).order_by(User.username.asc()).all()]
    else:
        users = [
            u.username
            for u in db.query(User).filter(~User.role.in_(["master_admin", "master-admin"])).order_by(User.username.asc()).all()
        ]

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
