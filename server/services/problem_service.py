import json
import re
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session
from config import settings
from models.server import Server, Service, SystemSnapshot
from models.problem import ServerProblem
from models.command import Command
from models.fim import FIMPath
from models.misc import AuditLog, SystemSetting

DEFAULT_THRESHOLDS = {
    "cpu_warn": 85.0,
    "cpu_average": 90.0,
    "cpu_danger": 95.0,
    "ram_warn": 85.0,
    "ram_average": 90.0,
    "ram_danger": 95.0,
    "disk_warn": 90.0,
    "disk_average": 92.5,
    "disk_danger": 95.0,
    "swap_warn": 80.0,
    "swap_average": 86.0,
    "swap_danger": 92.0,
    "ssh_fail_warn": 5,
    "ssh_fail_danger": 10,
}

_RETENTION_LIMITS = {
    "login_attempts_days": 1,
    "audit_logs_days": 365,
    "commands_days": 180,
    "log_requests_days": 30,
    "resolved_problems_days": 30,
}

CRITICAL_SERVICES = {
    "nginx", "mariadb", "mysql", "sshd", "cloudflared", "docker",
    "redis", "postgresql", "apache2", "caddy", "php-fpm", "systemd-resolved",
}


def _parse_ver_tuple(ver: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", str(ver or ""))]
    return tuple(nums) if nums else (0,)


def _is_agent_outdated(agent_ver: str, app_ver: str) -> bool:
    if not agent_ver or not app_ver:
        return False
    return _parse_ver_tuple(agent_ver) < _parse_ver_tuple(app_ver)


def get_global_thresholds(db: Session) -> dict:
    """Fetch global incident thresholds from SystemSetting with factory defaults fallback."""
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
        if row and row.value:
            data = json.loads(row.value)
            res = dict(DEFAULT_THRESHOLDS)
            for k in res:
                if k in data and data[k] is not None and str(data[k]).strip() != "":
                    try:
                        res[k] = int(data[k]) if "fail" in k else float(data[k])
                    except (ValueError, TypeError):
                        pass
            return res
    except Exception:
        pass
    return dict(DEFAULT_THRESHOLDS)


def get_server_thresholds(srv: Server, db: Session) -> dict:
    """Merge per-server custom_thresholds on top of global thresholds."""
    th = get_global_thresholds(db)
    raw = getattr(srv, "custom_thresholds", None)
    if raw:
        try:
            custom = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(custom, dict):
                for k in th:
                    if k in custom and custom[k] is not None and str(custom[k]).strip() != "":
                        try:
                            th[k] = int(custom[k]) if "fail" in k else float(custom[k])
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass
    return th


def sync_maintenance_state(srv: Server, now: Optional[datetime] = None) -> bool:
    """Clear expired maintenance window on Server and return True if currently in active maintenance."""
    if not getattr(srv, "is_maintenance", 0):
        return False
    ref_now = now or datetime.utcnow()
    m_until = getattr(srv, "maintenance_until", None)
    if m_until and m_until < ref_now:
        srv.is_maintenance = 0
        srv.maintenance_until = None
        srv.maintenance_reason = None
        return False
    return True


def _get_recent_host_power_cmd(db: Session, srv: Server, now: datetime) -> Optional[Command]:
    """Check if an operator intentionally rebooted or powered off this host within the last 30 minutes."""
    try:
        cutoff = now - timedelta(minutes=30)
        last_cmd = (
            db.query(Command)
            .filter(
                Command.server_id == srv.id,
                Command.action.in_(["poweroff_host", "reboot_host"]),
                Command.created_at >= cutoff,
            )
            .order_by(desc(Command.id))
            .first()
        )
        if last_cmd and last_cmd.created_at:
            ls_time = srv.last_seen.replace(tzinfo=None) if srv.last_seen and srv.last_seen.tzinfo else srv.last_seen
            if ls_time is None or last_cmd.created_at >= ls_time - timedelta(seconds=60):
                return last_cmd
    except Exception:
        pass
    return None


def _suppress_dependent_incidents_on_offline(db: Session, srv: Server, now: datetime):
    """Close open service_down and resource incidents when host is offline to prevent alert storms."""
    open_deps = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.resolved_at.is_(None),
    ).all()
    for p in open_deps:
        if p.key == "agent_stale" or p.key.startswith("probe_failed:") or p.probe_id is not None:
            continue
        if p.key.startswith(("service_down:", "svc_no_data:", "cpu_", "ram_", "swap_", "disk_")):
            p.resolved_at = now
            p.updated_at = now
            p.resolved_note = "server_offline"


def check_server_stale(db: Session, srv: Server, now: datetime = None):
    """
    Evaluate whether a monitored client node is silent/offline (agent_stale).
    - Operator-initiated reboot/poweroff -> warning.
    - Production (tier=1): >= 60s critical, >= 180s danger.
    - Non-Production (tier=2): warning (capped, non-escalating).
    """
    if now is None:
        now = datetime.utcnow()

    was_maint = bool(getattr(srv, "is_maintenance", 0))
    if sync_maintenance_state(srv, now):
        return
    if was_maint:
        db.commit()

    ls = srv.last_seen.replace(tzinfo=None) if srv.last_seen and srv.last_seen.tzinfo else srv.last_seen
    sec_silent = (now - ls).total_seconds() if ls else 999999.0
    is_prod = (getattr(srv, "tier", 1) == 1)

    existing_stale = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "agent_stale",
        ServerProblem.resolved_at.is_(None),
    ).first()

    if sec_silent >= 60.0:
        dur_mins = max(1, int(sec_silent // 60))
        dur_txt = f"{dur_mins}m"
        power_cmd = _get_recent_host_power_cmd(db, srv, now)

        if power_cmd:
            op_by = (power_cmd.issued_by or "operator").upper()
            sev = "warning"
            if power_cmd.action == "reboot_host":
                msg = f"Host rebooting by operator ({op_by})"
                tip = f"Host is undergoing a scheduled reboot initiated by operator ({op_by})."
            else:
                msg = f"Host powered off by operator ({op_by})"
                tip = f"Host was intentionally powered off by operator ({op_by})."
        elif is_prod:
            if sec_silent >= 180.0:
                sev = "danger"
                msg = f"Agent silent (> {dur_txt}) — HOST OFFLINE"
                tip = "Check power supply, hypervisor/physical hardware, and network connectivity for this Production host."
            else:
                sev = "critical"
                msg = f"Agent silent (> {dur_txt})"
                tip = "Vital telemetry interrupted. Verify pantau-agent daemon status and network connectivity."
        else:
            sev = "warning"
            msg = f"Agent silent (> {dur_txt})"
            tip = "Non-Production host is currently unreachable or pantau-agent is stopped."

        if existing_stale:
            old_sev = existing_stale.severity
            existing_stale.severity = sev
            existing_stale.message = msg
            existing_stale.tip = tip
            existing_stale.updated_at = now
            existing_stale.last_active_at = now
            if old_sev != sev:
                db.add(AuditLog(
                    server_id=srv.id,
                    username="System",
                    action="incident_escalated",
                    target="agent_stale",
                    result=sev,
                    meta=f"{srv.hostname}: severity changed [{old_sev.upper()} -> {sev.upper()}] — {msg}",
                    created_at=now,
                ))
        else:
            db.add(ServerProblem(
                server_id=srv.id,
                key="agent_stale",
                severity=sev,
                message=msg,
                tip=tip,
                started_at=now,
                updated_at=now,
                last_active_at=now,
            ))
            db.flush()
            db.add(AuditLog(
                server_id=srv.id,
                username="System",
                action="incident_detected",
                target="agent_stale",
                result="detected",
                meta=f"{srv.hostname}: {msg}",
                created_at=now,
            ))

        _suppress_dependent_incidents_on_offline(db, srv, now)
        db.commit()
    elif existing_stale:
        existing_stale.resolved_at = now
        existing_stale.updated_at = now
        existing_stale.resolved_note = "server_online"
        db.add(AuditLog(
            server_id=srv.id,
            username="System",
            action="incident_resolved",
            target="agent_stale",
            result="resolved",
            meta=f"{srv.hostname}: node back online and reporting normally",
            created_at=now,
        ))
        db.commit()


def check_all_servers_stale(db: Session):
    """Periodically check online/stale status across all active servers."""
    now = datetime.utcnow()
    servers = db.query(Server).filter(Server.is_active == 1).all()
    for srv in servers:
        try:
            check_server_stale(db, srv, now=now)
        except Exception:
            db.rollback()


def _resolve_resource_severity(
    values_desc: list[float],
    warn_th: float,
    crit_th: float,
    danger_th: float,
    is_open: bool,
    is_prod: bool,
) -> Optional[str]:
    """
    Evaluate resource utilization with 3-snapshot anti-flapping hysteresis when opening new incidents.
    Returns 'danger', 'critical', 'warning', or None.
    """
    if not values_desc:
        return None
    cur = values_desc[0]
    avg = sum(values_desc) / len(values_desc)

    if is_open:
        if cur >= danger_th or avg >= danger_th:
            return "danger" if is_prod else "warning"
        if is_prod and (cur >= crit_th or avg >= crit_th):
            return "critical"
        if cur >= warn_th or avg >= warn_th:
            return "warning"
        return None

    # Require 3 consecutive snapshots above warning threshold before opening a new incident
    if len(values_desc) >= 3 and all(v >= warn_th for v in values_desc[:3]):
        if cur >= danger_th and avg >= danger_th:
            return "danger" if is_prod else "warning"
        if is_prod and (cur >= crit_th or avg >= crit_th):
            return "critical"
        return "warning"
    return None


def _collect_operator_stopped_services(db: Session, srv: Server, now: datetime) -> dict[str, str]:
    """Collect service/process names intentionally stopped by an operator."""
    op_map: dict[str, str] = {}
    try:
        for s in db.query(Service).filter(Service.server_id == srv.id).all():
            reason = (s.ignored_reason or "").upper()
            if "DIMATIKAN OLEH OPERATOR" in reason or "DIHENTIKAN OLEH OPERATOR" in reason or "STOPPED BY OPERATOR" in reason:
                by = s.ignored_by or "operator"
                if s.service_name:
                    op_map[s.service_name.lower()] = by
                if s.process_name:
                    op_map[s.process_name.lower()] = by

        cutoff = now - timedelta(minutes=15)
        recent_cmds = (
            db.query(Command)
            .filter(
                Command.server_id == srv.id,
                Command.action.in_(["stop", "start"]),
                Command.created_at >= cutoff,
            )
            .order_by(desc(Command.id))
            .limit(20)
            .all()
        )
        seen = set()
        for cmd in recent_cmds:
            tgt = None
            if cmd.params:
                try:
                    cp = json.loads(cmd.params) if isinstance(cmd.params, str) else cmd.params
                    tgt = cp.get("service_name") or cp.get("unit") or cp.get("process_name")
                except Exception:
                    tgt = None
            if tgt:
                clean = tgt[:-8].lower() if tgt.lower().endswith(".service") else tgt.lower()
                if clean not in seen:
                    seen.add(clean)
                    if cmd.action == "stop" and cmd.status in ("pending", "executing", "success", "executed"):
                        by = cmd.issued_by or "operator"
                        op_map[clean] = by
                        op_map[tgt.lower()] = by
    except Exception:
        pass
    return op_map


def evaluate_server_problems(db: Session, srv: Server, report_dict: dict, extras):
    """Evaluate host health telemetry and synchronize active/resolved rows in server_problems."""
    now = datetime.utcnow()

    was_maint = bool(getattr(srv, "is_maintenance", 0))
    if sync_maintenance_state(srv, now):
        return
    if was_maint:
        db.commit()

    # Close agent_stale since agent just reported
    existing_stale = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "agent_stale",
        ServerProblem.resolved_at.is_(None),
    ).first()
    if existing_stale:
        existing_stale.resolved_at = now
        existing_stale.updated_at = now
        existing_stale.resolved_note = "server_online"
        db.add(AuditLog(
            server_id=srv.id,
            username="System",
            action="incident_resolved",
            target="agent_stale",
            result="resolved",
            meta=f"{srv.hostname}: node back online and reporting normally",
            created_at=now,
        ))

    existing_active = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.resolved_at.is_(None),
    ).all()
    existing_map = {p.key: p for p in existing_active}

    active_keys: set[str] = set()
    active_instances: list[dict] = []
    is_prod = (getattr(srv, "tier", 1) == 1)
    th = get_server_thresholds(srv, db)

    def _add(key: str, severity: str, message: str, tip: str, context=None):
        active_keys.add(key)
        ctx_str = json.dumps(context, ensure_ascii=False) if isinstance(context, (dict, list)) else context
        active_instances.append({
            "key": key,
            "severity": severity,
            "message": message,
            "tip": tip,
            "context": ctx_str,
        })

    # 1. Agent Outdated Check (warning)
    agent_ver = getattr(extras, "agent_version", None) or report_dict.get("agent_version")
    if agent_ver and _is_agent_outdated(agent_ver, settings.APP_VERSION):
        _add(
            "agent_outdated",
            "warning",
            f"Agent version v{agent_ver} is older than control plane v{settings.APP_VERSION}",
            "Dispatch an OTA agent update from the asset workspace to keep telemetry and security modules up to date.",
            {"agent_version": agent_ver, "app_version": settings.APP_VERSION},
        )

    # 2. OS Package Updates Available (info)
    apt_up = getattr(extras, "apt_upgradable", 0) or 0
    if not apt_up and isinstance(report_dict.get("apt"), dict):
        apt_up = int(report_dict["apt"].get("upgradable") or 0)
    if apt_up > 0 and getattr(srv, "is_isolated_net", 0) != 1:
        active_keys.add("pkg_updates")
        _add(
            "apt_updates",
            "info",
            f"{apt_up} OS package updates available",
            "Security or package updates are pending. Run package upgrade during a scheduled maintenance window.",
            {"upgradable_count": apt_up},
        )

    # 3. Active Remote SSH Sessions (warning for standard users, critical for root/tmp_*)
    accounts = report_dict.get("accounts")
    if isinstance(accounts, str):
        try:
            accounts = json.loads(accounts)
        except Exception:
            accounts = []
    if isinstance(accounts, list):
        for acc in accounts:
            if not isinstance(acc, dict):
                continue
            u_name = str(acc.get("user") or "unknown").strip()
            if u_name == "pantau":
                continue
            for s in (acc.get("sessions") or []):
                if not isinstance(s, dict):
                    continue
                raw_from = str(s.get("from") or "").strip().strip("()")
                r_tty = str(s.get("tty") or "").strip()
                r_time = str(s.get("time") or "").strip()
                low_from = raw_from.lower()
                if raw_from and not raw_from.startswith(":") and not low_from.startswith(("local", "lokal", "web terminal", "tmux(")):
                    clean_tty = r_tty.replace("/", "_") if r_tty else "ssh"
                    clean_from = re.sub(r"[^a-zA-Z0-9_.:-]", "_", raw_from)
                    sess_key = f"ssh_active_session:{u_name}:{clean_tty}:{clean_from}"[:150]
                    tty_disp = f" ({r_tty})" if r_tty else ""
                    time_disp = f" since {r_time}" if r_time else ""
                    sev = "info"
                    _add(
                        sess_key,
                        sev,
                        f"Active remote SSH session: user '{u_name}' from {raw_from}{tty_disp}",
                        f"User '{u_name}' is connected via remote SSH from {raw_from}{tty_disp}{time_disp}. Terminate session if unauthorized.",
                        {
                            "diagnosa_en": "Active Remote SSH Session in Progress",
                            "penyebab_en": f"User '{u_name}' connected via remote SSH from {raw_from}{tty_disp}.",
                            "dampak_en": "Interactive administrative session active on target host.",
                            "data_teknis": {"user": u_name, "source_ip": raw_from, "tty": r_tty, "login_time": r_time},
                        },
                    )

    # 4. SSH Brute-Force / Failed Logins (info / warning / danger)
    sec_raw = report_dict.get("security") or getattr(extras, "security", None)
    if isinstance(sec_raw, str):
        try:
            sec_raw = json.loads(sec_raw)
        except Exception:
            sec_raw = None
    if isinstance(sec_raw, dict):
        failed = int(sec_raw.get("failed") or 0)
        invalid = int(sec_raw.get("invalid_users") or 0)
        src_ips = sec_raw.get("source_ips") or {}
        nips = len(src_ips) if isinstance(src_ips, dict) else 0
        ssh_warn_th = int(th.get("ssh_fail_warn", 5))
        ssh_danger_th = int(th.get("ssh_fail_danger", 10))
        if invalid >= 4 or failed >= ssh_danger_th:
            sev = "danger" if is_prod else "warning"
            _add(
                "failed_logins",
                sev,
                f"SSH brute-force suspected: {failed} failed logins, {invalid} invalid users from {nips} IP(s)",
                "Block offending source IPs via Firewall controls and verify SSH key-only authentication.",
                {"failed": failed, "invalid_users": invalid, "source_ips": src_ips, "threshold": ssh_danger_th},
            )
        elif failed >= ssh_warn_th:
            _add(
                "failed_logins",
                "warning",
                f"{failed} failed SSH login attempts from {nips} IP(s) (threshold >= {ssh_warn_th})",
                "Monitor authentication logs for brute-force patterns and consider blocking repeat offender IPs.",
                {"failed": failed, "invalid_users": invalid, "source_ips": src_ips, "threshold": ssh_warn_th},
            )
        elif failed >= 1:
            _add(
                "failed_logins",
                "info",
                f"{failed} failed SSH login attempt(s) detected",
                "Low-volume authentication failure observed in SSH logs.",
                {"failed": failed, "invalid_users": invalid, "source_ips": src_ips},
            )

    # 5. Kernel Events (OOM Killer, Disk I/O Error, Kernel Panic, Segfault)
    oom_event_map: dict[str, dict] = {}
    ke_raw = report_dict.get("kernel_events") or getattr(extras, "kernel_events", None)
    if isinstance(ke_raw, str):
        try:
            ke_raw = json.loads(ke_raw)
        except Exception:
            ke_raw = None
    if isinstance(ke_raw, dict):
        now_ts = now.timestamp()
        for ev in (ke_raw.get("events") or []):
            if not isinstance(ev, dict):
                continue
            ev_type = ev.get("type")
            ev_epoch = float(ev.get("epoch") or 0.0)
            if ev_epoch > 0 and (now_ts - ev_epoch) > 1800:
                continue
            if ev_type == "oom_kill":
                p_name = str(ev.get("proc") or "process").strip()
                u_name = str(ev.get("unit") or "").strip()
                clean_proc = p_name.lower()
                clean_unit = u_name[:-8].lower() if u_name.lower().endswith(".service") else u_name.lower()
                oom_info = {"proc": p_name, "pid": ev.get("pid"), "unit": u_name, "time": ev.get("time")}
                if clean_proc:
                    oom_event_map[clean_proc] = oom_info
                if clean_unit:
                    oom_event_map[clean_unit] = oom_info
                _add(
                    f"oom_kill:{clean_proc}",
                    "danger" if is_prod else "warning",
                    f"Process '{p_name}' terminated by Kernel OOM Killer",
                    "Host exhausted physical memory and swap. Inspect memory leaks or increase RAM allocation.",
                    oom_info,
                )
            elif ev_type == "disk_io_error":
                dev_name = str(ev.get("dev") or "storage").strip()
                _add(
                    f"disk_io_error:{dev_name}",
                    "danger" if is_prod else "warning",
                    f"Storage I/O error detected on {dev_name}",
                    f"Kernel logged physical read/write I/O errors on {dev_name}. Back up critical data and inspect drive health.",
                    {"device": dev_name, "time": ev.get("time"), "raw": ev.get("message")},
                )
            elif ev_type == "kernel_panic":
                _add(
                    "kernel_panic",
                    "danger" if is_prod else "warning",
                    "Kernel Panic or fatal hardware error (MCE) detected",
                    "Inspect dmesg/journalctl crash logs and verify hardware stability.",
                    {"detail": ev.get("detail"), "raw": ev.get("message")},
                )
            elif ev_type == "segfault":
                p_name = str(ev.get("proc") or "process").strip()
                _add(
                    f"segfault:{p_name.lower()}",
                    "critical" if is_prod else "warning",
                    f"Process '{p_name}' crashed with segmentation fault (SIGSEGV)",
                    f"Application '{p_name}' encountered an invalid memory access. Inspect application logs and binary integrity.",
                    {"process": p_name, "time": ev.get("time"), "raw": ev.get("message")},
                )

    # 6. Crucial Services Down / Failed (with operator stop downgrade & time escalation)
    units_raw = report_dict.get("units") or report_dict.get("services") or report_dict.get("systemd_units")
    if isinstance(units_raw, str):
        try:
            units_raw = json.loads(units_raw)
        except Exception:
            units_raw = []
    op_action_map = _collect_operator_stopped_services(db, srv, now)
    if isinstance(units_raw, list):
        for u in units_raw:
            if not isinstance(u, dict):
                continue
            svc_name = str(u.get("name") or "").replace(".service", "").strip().lower()
            if not svc_name:
                continue
            active_state = str(u.get("active") or "").strip().lower()
            sub_state = str(u.get("sub") or "").strip().lower()
            is_failed = (active_state == "failed" or sub_state == "failed")
            if is_failed and (svc_name in CRITICAL_SERVICES or u.get("monitored")):
                k = f"service_down:{svc_name}"
                if svc_name in op_action_map:
                    op_by = op_action_map[svc_name]
                    sev = "warning"
                    msg = f"Service {svc_name} stopped by operator ({op_by})"
                    tip = f"Unit '{svc_name}' was intentionally stopped by operator ({op_by})."
                elif svc_name in oom_event_map:
                    sev = "danger" if is_prod else "warning"
                    msg = f"Service {svc_name} down — killed by Kernel OOM Killer"
                    tip = f"Primary process for '{svc_name}' was terminated by OOM Killer. Verify RAM availability and restart unit."
                else:
                    down_secs = 0.0
                    open_svc = existing_map.get(k)
                    if open_svc and open_svc.started_at:
                        st_dt = open_svc.started_at.replace(tzinfo=None) if open_svc.started_at.tzinfo else open_svc.started_at
                        down_secs = max(0.0, (now - st_dt).total_seconds())
                    if is_prod:
                        sev = "danger" if down_secs >= 60.0 else "critical"
                    else:
                        sev = "warning"
                    msg = f"Service {svc_name} is down ({active_state}/{sub_state})"
                    tip = f"Crucial service '{svc_name}' is not running. Restart the service or inspect systemd journal logs."
                _add(
                    k,
                    sev,
                    msg,
                    tip,
                    {"service": svc_name, "active": active_state, "sub": sub_state, "description": u.get("description", "")},
                )

    # 7. Resource Metrics with 3-Snapshot Anti-Flapping Hysteresis
    recent_snaps = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == srv.id)
        .order_by(desc(SystemSnapshot.id))
        .limit(3)
        .all()
    )
    sysd = report_dict.get("system") if isinstance(report_dict.get("system"), dict) else report_dict

    # 7a. CPU
    cur_cpu = float(sysd.get("cpu") if sysd.get("cpu") is not None else (report_dict.get("cpu") or 0.0))
    cpu_series = [cur_cpu] + [float(s.cpu) for s in recent_snaps if s.cpu is not None][:2]
    cpu_sev = _resolve_resource_severity(
        cpu_series,
        float(th.get("cpu_warn", 85.0)),
        float(th.get("cpu_average", 90.0)),
        float(th.get("cpu_danger", 95.0)),
        is_open=("cpu_usage" in existing_map or "cpu_critical" in existing_map or "cpu_high" in existing_map),
        is_prod=is_prod,
    )
    if cpu_sev:
        _add(
            "cpu_usage",
            cpu_sev,
            f"CPU utilization {cpu_sev}: {cur_cpu:.1f}%",
            "Inspect top CPU-consuming processes in the asset workspace.",
            {"cpu_pct": round(cur_cpu, 1)},
        )

    # 7b. RAM
    mem_total = int(sysd.get("mem_total") or (report_dict.get("mem") or {}).get("total") or 0)
    mem_used = int(sysd.get("mem_used") or (report_dict.get("mem") or {}).get("used") or 0)
    if mem_total > 0:
        cur_ram = (mem_used / mem_total) * 100.0
        ram_series = [cur_ram] + [
            (s.mem_used / s.mem_total) * 100.0
            for s in recent_snaps
            if (s.mem_total or 0) > 0 and s.mem_used is not None
        ][:2]
        ram_sev = _resolve_resource_severity(
            ram_series,
            float(th.get("ram_warn", 85.0)),
            float(th.get("ram_average", 90.0)),
            float(th.get("ram_danger", 95.0)),
            is_open=("ram_usage" in existing_map or "ram_danger" in existing_map or "ram_warning" in existing_map),
            is_prod=is_prod,
        )
        if ram_sev:
            _add(
                "ram_usage",
                ram_sev,
                f"Memory utilization {ram_sev}: {cur_ram:.1f}%",
                "High physical memory pressure increases OOM killer risk. Inspect memory-intensive processes.",
                {"ram_pct": round(cur_ram, 1), "used": mem_used, "total": mem_total},
            )

    # 7c. Swap
    swap = report_dict.get("swap") if isinstance(report_dict.get("swap"), dict) else {}
    swap_total = int(sysd.get("swap_total") or swap.get("total") or 0)
    swap_used = int(sysd.get("swap_used") or swap.get("used") or 0)
    if swap_total > 0:
        cur_swap = (swap_used / swap_total) * 100.0
        swap_series = [cur_swap] + [
            (s.swap_used / s.swap_total) * 100.0
            for s in recent_snaps
            if (s.swap_total or 0) > 0 and s.swap_used is not None
        ][:2]
        swap_sev = _resolve_resource_severity(
            swap_series,
            float(th.get("swap_warn", 80.0)),
            float(th.get("swap_average", 86.0)),
            float(th.get("swap_danger", 92.0)),
            is_open=("swap_usage" in existing_map),
            is_prod=is_prod,
        )
        if swap_sev:
            _add(
                "swap_usage",
                swap_sev,
                f"Swap utilization {swap_sev}: {cur_swap:.1f}%",
                "Sustained swap usage indicates memory pressure and degraded disk I/O performance.",
                {"swap_pct": round(cur_swap, 1), "used": swap_used, "total": swap_total},
            )

    # 7d. Disk Partitions & Read-Only Filesystems
    disks_raw = sysd.get("disks") if sysd.get("disks") is not None else report_dict.get("disk")
    disk_warn = float(th.get("disk_warn", 90.0))
    disk_crit = float(th.get("disk_average", 92.5))
    disk_danger = float(th.get("disk_danger", 95.0))
    if isinstance(disks_raw, list):
        for d in disks_raw:
            if not isinstance(d, dict):
                continue
            mount = d.get("mount") or d.get("mounted_on") or "/"
            pct = float(d.get("pct") or d.get("used_percent") or d.get("percent") or 0.0)
            is_ro = bool(d.get("is_ro"))
            if is_ro:
                _add(
                    f"disk_ro:{mount}",
                    "danger" if (is_prod or mount == "/") else "warning",
                    f"Filesystem {mount} mounted Read-Only",
                    f"Kernel remounted {mount} read-only due to I/O or filesystem errors. Check dmesg and storage health.",
                    {"mount": mount},
                )
            if pct >= disk_danger:
                _add(
                    f"disk_usage:{mount}",
                    "danger" if is_prod else "warning",
                    f"Critical disk capacity on {mount}: {pct:.1f}%",
                    f"Partition {mount} exceeded danger threshold ({disk_danger:.0f}%). Free disk space immediately.",
                    {"mount": mount, "pct": round(pct, 1)},
                )
            elif is_prod and pct >= disk_crit:
                _add(
                    f"disk_usage:{mount}",
                    "critical",
                    f"Very high disk capacity on {mount}: {pct:.1f}%",
                    f"Partition {mount} exceeded critical threshold ({disk_crit:.0f}%). Clean logs or expand volume.",
                    {"mount": mount, "pct": round(pct, 1)},
                )
            elif pct >= disk_warn:
                _add(
                    f"disk_usage:{mount}",
                    "warning",
                    f"High disk capacity on {mount}: {pct:.1f}%",
                    f"Partition {mount} exceeded warning threshold ({disk_warn:.0f}%).",
                    {"mount": mount, "pct": round(pct, 1)},
                )

    # 8. S.M.A.R.T. / NVMe Hardware Health
    hw_raw = report_dict.get("hardware_specs") or report_dict.get("hardware") or getattr(extras, "hardware_specs", None)
    if isinstance(hw_raw, str):
        try:
            hw_raw = json.loads(hw_raw)
        except Exception:
            hw_raw = None
    if isinstance(hw_raw, dict):
        for disk in (hw_raw.get("disks") or []):
            if not isinstance(disk, dict) or disk.get("is_virtual"):
                continue
            dname = str(disk.get("name") or "").strip()
            smart = disk.get("smart")
            if not dname or not isinstance(smart, dict) or smart.get("is_virtual"):
                continue
            health = smart.get("health")
            temp_c = smart.get("temp_c")
            wear_pct = smart.get("wearout_pct")
            wear_rem = smart.get("wearout_remaining")
            realloc = smart.get("reallocated_sectors") or 0

            if health == "critical" or smart.get("status_label") == "CRITICAL":
                _add(
                    f"disk_smart_failing:{dname}",
                    "danger" if is_prod else "warning",
                    f"Drive {dname} S.M.A.R.T. health CRITICAL",
                    f"Hardware failure predicted on {dname}. Back up data and schedule immediate drive replacement.",
                    smart,
                )
            elif temp_c and temp_c >= 65:
                _add(
                    f"disk_smart_temp:{dname}",
                    "danger" if (is_prod and temp_c >= 75) else "warning",
                    f"Drive {dname} temperature high: {temp_c}°C",
                    f"Check chassis airflow and cooling fans for drive {dname}.",
                    smart,
                )
            elif (wear_pct is not None and wear_pct >= 90) or (wear_rem is not None and wear_rem <= 10):
                rem_val = wear_rem if wear_rem is not None else (100 - wear_pct)
                _add(
                    f"disk_smart_wear:{dname}",
                    "danger" if (is_prod and rem_val <= 3) else "warning",
                    f"SSD/NVMe {dname} endurance low: {rem_val}% remaining",
                    f"Flash endurance on {dname} is nearing TBW limit. Plan drive replacement.",
                    smart,
                )
            elif realloc > 50:
                _add(
                    f"disk_smart_sectors:{dname}",
                    "warning",
                    f"Drive {dname} has {realloc} reallocated sectors",
                    f"Physical bad sectors detected on {dname}. Monitor I/O stability.",
                    smart,
                )

    # 9. File Integrity Monitoring (FIM) Anomalies
    try:
        anom_paths = db.query(FIMPath).filter(
            FIMPath.server_id == srv.id,
            FIMPath.status.in_(["CHANGED", "MISSING", "ERROR"]),
        ).all()
        for ap in anom_paths:
            if ap.status == "MISSING" and not ap.sha256_hash:
                continue
            _add(
                f"fim_anomaly:{ap.path}"[:150],
                "warning" if ap.category == "system" else "info",
                f"File integrity changed on {ap.path} ({ap.status})",
                f"Review FIM changes for {ap.path} and update baseline if the modification was authorized.",
                {"path": ap.path, "status": ap.status, "category": ap.category},
            )
    except Exception:
        pass

    # 10. Synchronize Active Incidents to Database
    for inst in active_instances:
        k = inst["key"]
        if k in existing_map:
            prob = existing_map[k]
            old_sev = prob.severity
            prob.severity = inst["severity"]
            prob.updated_at = now
            prob.last_active_at = now
            prob.message = inst["message"]
            if inst.get("tip"):
                prob.tip = inst["tip"]
            if inst.get("context"):
                prob.context = inst["context"]
            if old_sev != inst["severity"]:
                db.add(AuditLog(
                    server_id=srv.id,
                    username="System",
                    action="incident_escalated",
                    target=k,
                    result=inst["severity"],
                    meta=f"{srv.hostname}: severity changed [{old_sev.upper()} -> {inst['severity'].upper()}] — {inst['message']}",
                    created_at=now,
                ))
        else:
            # Inherit active permanent or unexpired duration ignore policy for this (server_id, key)
            prev_ign = (
                db.query(ServerProblem)
                .filter(
                    ServerProblem.server_id == srv.id,
                    ServerProblem.key == k,
                    ServerProblem.is_ignored == 1,
                )
                .order_by(ServerProblem.id.desc())
                .first()
            )
            inh_ignored = 0
            inh_until = None
            inh_by = None
            inh_reason = None
            inh_mode = None
            if prev_ign:
                p_mode = prev_ign.ignore_mode
                if p_mode == "permanent" or (p_mode == "duration" and prev_ign.ignored_until and prev_ign.ignored_until > now):
                    inh_ignored = 1
                    inh_until = prev_ign.ignored_until
                    inh_by = prev_ign.ignored_by
                    inh_reason = prev_ign.ignored_reason
                    inh_mode = p_mode

            db.add(ServerProblem(
                server_id=srv.id,
                key=k,
                severity=inst["severity"],
                message=inst["message"],
                tip=inst.get("tip"),
                started_at=now,
                updated_at=now,
                last_active_at=now,
                context=inst.get("context"),
                is_ignored=inh_ignored,
                ignored_until=inh_until,
                ignored_by=inh_by,
                ignored_reason=inh_reason,
                ignore_mode=inh_mode,
            ))
            db.flush()
            db.add(AuditLog(
                server_id=srv.id,
                username="System",
                action="incident_detected",
                target=k,
                result="detected",
                meta=f"{srv.hostname}: {inst['message']}",
                created_at=now,
            ))

    # 11. Auto-Resolve Cleared Incidents
    for k, prob in existing_map.items():
        if k == "agent_stale" or k.startswith("probe_failed:") or prob.probe_id is not None:
            continue
        if k not in active_keys:
            prob.resolved_at = now
            prob.updated_at = now
            if k.startswith("ssh_active_session:"):
                prob.resolved_note = "session_closed"
            elif k.startswith("service_down:"):
                prob.resolved_note = "service_up"
            elif k in ("pkg_updates", "apt_updates"):
                prob.resolved_note = "packages_updated"
            elif k.startswith(("cpu_", "ram_", "swap_", "disk_")):
                prob.resolved_note = "auto"
            else:
                prob.resolved_note = "resolved"

            db.add(AuditLog(
                server_id=srv.id,
                username="System",
                action="incident_resolved",
                target=k,
                result="resolved",
                meta=f"{srv.hostname}: incident {k} resolved ({prob.resolved_note})",
                created_at=now,
            ))


def run_retention_prune(db: Session) -> None:
    """Prune expired sessions, old audit/command/log/metric rows, and transient resolved incidents."""
    from models.command import Command, LogRequest
    from models.user import AppSession

    now = datetime.utcnow()
    db.query(AppSession).filter(AppSession.expires_at < now).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.created_at < now - timedelta(days=365)).delete(synchronize_session=False)
    db.query(Command).filter(
        Command.status.in_(["success", "failed", "executed", "canceled"]),
        Command.created_at < now - timedelta(days=180),
    ).delete(synchronize_session=False)
    db.query(LogRequest).filter(
        LogRequest.status.in_(["success", "failed"]),
        LogRequest.updated_at < now - timedelta(days=30),
    ).delete(synchronize_session=False)
    db.query(ServerProblem).filter(
        ServerProblem.resolved_at.isnot(None),
        ServerProblem.resolved_at < now - timedelta(days=30),
        (ServerProblem.is_ignored == 0) | (ServerProblem.is_ignored.is_(None)) | (ServerProblem.ignore_mode != "permanent"),
    ).delete(synchronize_session=False)

    mcut = now - timedelta(days=7)
    for _ in range(25):
        del_cnt = db.execute(
            text("DELETE FROM metrics WHERE timestamp < :cutoff LIMIT 10000"),
            {"cutoff": mcut},
        ).rowcount
        db.commit()
        if del_cnt < 10000:
            break

    pcut = now - timedelta(days=7)
    db.execute(
        text(
            "DELETE FROM server_problems WHERE resolved_at IS NOT NULL AND resolved_at < :pcut "
            "AND resolved_note IN ('duplicate_cleanup', 'auto', 'server_online', 'service_up')"
        ),
        {"pcut": pcut},
    )
    db.commit()
