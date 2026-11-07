"""
Router Dashboard dan Manajemen Insiden Pantau Server.
Menyediakan endpoint untuk UI dashboard NOC, halaman insiden (/problems),
API polling insiden (/api/alerts, /api/problems), tindakan acknowledge/ignore/resolve,
serta endpoint status sistem host.
"""

from datetime import datetime, timezone, timedelta
import logging
import socket

from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from config import settings
from core.database import get_db
from core.security import get_current_user, require_user, _verify_csrf_header
from core.templates import tpl
from core.utils import _clean_str, _fmt_dt, _fmt_short_dt, _is_agent_outdated
from models import (
    Server,
    ServerExtras,
    Service,
    Metric,
    SystemSnapshot,
    ServerProblem,
    ProbeTarget,
    User,
)
from services.audit_service import _audit
from services.hardware_service import (
    _format_bytes_gb,
    _format_uptime_str,
    _extract_disk_stats,
    _classify_platform,
    _get_hardware_specs_dict,
    _format_ignored_prob_msg,
)
from services.maintenance_service import get_active_maintenance_info
from services.problem_service import (
    DEFAULT_THRESHOLDS,
    get_global_thresholds,
    sync_server_problems,
    _problem_instances,
    problems_aggregate,
    _fmt_duration,
    _alert_dict,
)
from services.server_service import (
    _server_stale,
    _server_status,
    _latest_metrics,
    get_existing_groups_and_tags,
)
from services.system_service import (
    _SERVER_BOOT_TIME,
    _proc_uptime,
    _proc_loadavg,
    _proc_cpu,
    _proc_memory,
    _proc_disks,
    _proc_top,
)

logger = logging.getLogger("pantau.dashboard")

router = APIRouter(tags=["Dashboard"])


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    total = len(servers)
    up_count = 0
    down_services = 0
    ignored_services = 0
    extras_map = {ex.server_id: ex for ex in db.query(ServerExtras).all()}

    for srv in servers:
        ex = extras_map.get(srv.id)
        srv._apt_upgradable = ex.apt_upgradable if ex else None
        srv._apt_last_update = ex.apt_last_update if ex else None
        srv._os_label = ex.os_label if ex else None
        srv._arch = ex.arch if ex else None
        srv._kernel = ex.kernel if ex else None
        srv._agent_version = ex.agent_version if ex else None
        srv._agent_outdated = _is_agent_outdated(srv._agent_version, settings.APP_VERSION)
        services = db.query(Service).filter(Service.server_id == srv.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        srv._svc_data = []
        for svc in services:
            latest = latest_map.get(svc.id)
            d = {
                "name": svc.service_name,
                "port": svc.port,
                "process": svc.process_name,
                "is_core": bool(getattr(svc, "is_core", 1)),
                "status": latest.status if latest else "unknown",
                "connections": latest.active_connections if latest else 0,
                "response_time": latest.response_time_ms if latest else None,
                "health_msg": latest.health_message if latest else None,
                "last_check": latest.timestamp.isoformat() if latest else None,
            }
            srv._svc_data.append(d)
        # Sync problems terlebih dahulu agar status ignored diketahui
        srv._problem_level, srv._problems, _ph = sync_server_problems(
            db, srv, _problem_instances(srv, ex, srv._svc_data, db)
        )
        active_probs = [p for p in srv._problems if not p.get("is_ignored")]
        danger_probs = [p for p in active_probs if p.get("severity") == "danger"]
        average_probs = [p for p in active_probs if p.get("severity") == "average"]
        warning_probs = [p for p in active_probs if p.get("severity") == "warning"]
        info_probs = [p for p in active_probs if p.get("severity") == "info"]
        ignored_probs = [p for p in srv._problems if p.get("is_ignored")]

        srv._danger_count = len(danger_probs)
        srv._average_count = len(average_probs)
        srv._warning_count = len(warning_probs)
        srv._info_count = len(info_probs)
        srv._ignored_count = len(ignored_probs)
        srv._danger_msgs = " • ".join(p.get("message", "") for p in danger_probs)
        srv._average_msgs = " • ".join(p.get("message", "") for p in average_probs)
        srv._warning_msgs = " • ".join(p.get("message", "") for p in warning_probs)
        srv._info_msgs = " • ".join(p.get("message", "") for p in info_probs)
        srv._ignored_msgs = " • ".join(_format_ignored_prob_msg(p) for p in ignored_probs)

        ignored_keys = {p.get("key") for p in srv._problems if p.get("is_ignored")}
        svc_ignored_db = {s.service_name for s in services if getattr(s, "is_ignored", 0)}
        unignored_down = 0
        server_ignored_down = 0
        for d in srv._svc_data:
            if d.get("status") in ("down", "offline"):
                if f"service_down:{d['name']}" not in ignored_keys and d['name'] not in svc_ignored_db:
                    unignored_down += 1
                    down_services += 1
                else:
                    d["ignored"] = True
                    server_ignored_down += 1
                    ignored_services += 1
            elif d.get("name") in svc_ignored_db:
                d["ignored"] = True
        srv._unignored_down = unignored_down
        srv._ignored_down = server_ignored_down

        stale = _server_stale(srv)
        is_ign_stale = False
        if stale:
            for d in srv._svc_data:
                d["status"] = "offline"
            is_ign_stale = any(
                p.get("key") == "agent_stale" and p.get("is_ignored")
                for p in getattr(srv, "_problems", []) or []
            )
        srv._is_ignored_stale = is_ign_stale
        if srv.is_maintenance:
            srv._status_label, srv._status_cls = "Pemeliharaan", "badge-warn"
        else:
            srv._status_label, srv._status_cls = _server_status(
                srv,
                stale,
                bool(srv._svc_data),
                any(d["status"] == "up" for d in srv._svc_data),
                has_unignored_down=(unignored_down > 0),
                is_ignored_stale=is_ign_stale,
            )
        latest_sys = (
            db.query(SystemSnapshot)
            .filter(SystemSnapshot.server_id == srv.id)
            .order_by(desc(SystemSnapshot.timestamp))
            .first()
        )
        srv._cpu = round(latest_sys.cpu, 1) if latest_sys else None
        srv._mem_pct = (
            round(latest_sys.mem_used / latest_sys.mem_total * 100, 1)
            if latest_sys and latest_sys.mem_total
            else None
        )
        srv._load1 = round(latest_sys.load1, 2) if (latest_sys and latest_sys.load1 is not None) else None

        hw = _get_hardware_specs_dict(srv, ex, latest_sys)
        cpu_cores = hw.get("cpu", {}).get("cores") or hw.get("cpu", {}).get("logical_cores")
        srv._cpu_cores_str = f"{cpu_cores} Core" if (srv.last_seen and cpu_cores) else "—"
        srv._platform = _classify_platform(hw.get("platform", {}), getattr(srv, "platform_override", None))
        d_tot, d_avail, d_pct = _extract_disk_stats(latest_sys.disks if latest_sys else None)
        srv._disk_total_str = d_tot
        srv._disk_avail_str = d_avail
        srv._disk_pct = d_pct
        srv._mem_total_str = _format_bytes_gb(latest_sys.mem_total if latest_sys else None)
        srv._mem_avail_str = _format_bytes_gb(latest_sys.mem_avail if latest_sys else None)
        srv._mem_used_str = _format_bytes_gb(latest_sys.mem_used if latest_sys else None)
        srv._uptime_str = _format_uptime_str(latest_sys.uptime_secs if latest_sys else None)
        srv._uptime_secs = latest_sys.uptime_secs if latest_sys else 0

        if srv._status_cls == "badge-up":
            up_count += 1

    last_metric = db.query(Metric.timestamp).order_by(desc(Metric.timestamp)).first()
    if last_metric:
        ts = last_metric[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        last_update_secs = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    else:
        last_update_secs = -1

    existing_groups, existing_tags = get_existing_groups_and_tags(db)
    group_counts = {}
    ungrouped_count = 0
    for srv in servers:
        if srv.group_name:
            group_counts[srv.group_name] = group_counts.get(srv.group_name, 0) + 1
        else:
            ungrouped_count += 1

    danger_total = sum(srv._danger_count for srv in servers)
    average_total = sum(srv._average_count for srv in servers)
    warning_total = sum(srv._warning_count for srv in servers)
    info_total = sum(srv._info_count for srv in servers)
    ignored_total = sum(srv._ignored_count for srv in servers)
    healthy_total = sum(
        1
        for srv in servers
        if srv._status_cls == "badge-up"
        and (srv._danger_count + srv._average_count + srv._warning_count) == 0
    )

    problems_by_sev = {
        "danger": [],
        "average": [],
        "warning": [],
        "info": [],
        "ignored": [],
    }
    all_open_problems = []
    for srv in servers:
        for p in (srv._problems or []):
            is_ign = bool(p.get("is_ignored"))
            p_started = p.get("started_at")
            dur_str = "—"
            if p_started:
                diff_s = max(0, int((datetime.utcnow() - p_started).total_seconds()))
                d = diff_s // 86400
                h = (diff_s % 86400) // 3600
                m = (diff_s % 3600) // 60
                s = diff_s % 60
                if d:
                    dur_str = f"{d} h {h} j"
                elif h:
                    dur_str = f"{h} j {m} mnt"
                elif m:
                    dur_str = f"{m} mnt {s} dtk"
                else:
                    dur_str = f"{s} dtk"
            item = {
                "server_id": srv.id,
                "hostname": srv.hostname,
                "group_name": srv.group_name or "",
                "ip_address": srv.ip_address or "",
                "is_offline": (srv.last_seen is None) or _server_stale(srv),
                "severity": p.get("severity", "warning"),
                "message": p.get("message", ""),
                "key": p.get("key", ""),
                "is_ignored": is_ign,
                "is_operator_action": bool(p.get("is_operator_action")),
                "ignored_reason": p.get("ignored_reason"),
                "ignored_by": ("master-admin" if p.get("ignored_by") == "admin" else p.get("ignored_by")),
                "started_at": p_started.isoformat() if p_started else "",
                "started_at_str": _fmt_short_dt(p_started),
                "durasi": dur_str,
                "acknowledged_by": ("master-admin" if p.get("acknowledged_by") == "admin" else p.get("acknowledged_by")),
                "acknowledged_at": (
                    p.get("acknowledged_at").isoformat()
                    if isinstance(p.get("acknowledged_at"), datetime)
                    else (p.get("acknowledged_at") or "")
                ),
            }
            if is_ign:
                problems_by_sev["ignored"].append(item)
            else:
                sev = item["severity"]
                if sev in problems_by_sev:
                    problems_by_sev[sev].append(item)
                else:
                    problems_by_sev["warning"].append(item)

            if is_ign:
                continue

            all_open_problems.append(item)

    # Tambahkan insiden dari Synthetic Probing mandiri (tanpa server_id)
    standalone_probs = (
        db.query(ServerProblem)
        .filter(
            ServerProblem.server_id.is_(None),
            ServerProblem.probe_id.isnot(None),
            ServerProblem.resolved_at.is_(None),
        )
        .all()
    )
    if standalone_probs:
        probes_map = {p.id: p for p in db.query(ProbeTarget).all()}
        for sp in standalone_probs:
            prb = probes_map.get(sp.probe_id)
            prb_name = prb.name if prb else f"Endpoint #{sp.probe_id}"
            is_ign = bool(sp.is_ignored)
            p_started = sp.started_at
            dur_str = "—"
            if p_started:
                diff_s = max(0, int((datetime.utcnow() - p_started).total_seconds()))
                d = diff_s // 86400
                h = (diff_s % 86400) // 3600
                m = (diff_s % 3600) // 60
                s = diff_s % 60
                if d:
                    dur_str = f"{d} h {h} j"
                elif h:
                    dur_str = f"{h} j {m} mnt"
                elif m:
                    dur_str = f"{m} mnt {s} dtk"
                else:
                    dur_str = f"{s} dtk"
            item = {
                "server_id": None,
                "probe_id": sp.probe_id,
                "hostname": prb_name,
                "group_name": "Endpoint",
                "tier": getattr(prb, "tier", 2) or 2 if prb else 2,
                "severity": sp.severity or "warning",
                "message": sp.message or "",
                "key": sp.key or "",
                "is_ignored": is_ign,
                "ignored_reason": sp.ignored_reason,
                "ignored_by": ("master-admin" if sp.ignored_by == "admin" else sp.ignored_by),
                "started_at": p_started.isoformat() if p_started else "",
                "started_at_str": _fmt_short_dt(p_started),
                "durasi": dur_str,
                "acknowledged_by": ("master-admin" if sp.acknowledged_by == "admin" else sp.acknowledged_by),
                "acknowledged_at": (
                    sp.acknowledged_at.isoformat()
                    if isinstance(sp.acknowledged_at, datetime)
                    else (sp.acknowledged_at or "")
                ),
            }
            if is_ign:
                problems_by_sev["ignored"].append(item)
                ignored_total += 1
            else:
                sev = item["severity"]
                if sev == "danger":
                    danger_total += 1
                elif sev == "average":
                    average_total += 1
                elif sev == "warning":
                    warning_total += 1
                elif sev == "info":
                    info_total += 1
                if sev in problems_by_sev:
                    problems_by_sev[sev].append(item)
                else:
                    problems_by_sev["warning"].append(item)

            if is_ign:
                continue

            all_open_problems.append(item)

    sev_order = {"danger": 0, "average": 1, "warning": 2, "info": 3}

    def _prob_sort_key(p):
        is_ign = 1 if p.get("is_ignored") else 0
        sev = sev_order.get((p.get("severity") or "info").lower(), 4)
        iso = p.get("started_at") or ""
        ts = 0.0
        if iso:
            try:
                clean_iso = iso.replace("Z", "")
                ts = datetime.fromisoformat(clean_iso).timestamp()
            except Exception:
                ts = 0.0
        return (is_ign, sev, -ts)

    all_open_problems.sort(key=_prob_sort_key)

    top_cpu = sorted([s for s in servers if s._cpu is not None], key=lambda s: s._cpu, reverse=True)[:5]
    top_mem = sorted([s for s in servers if s._mem_pct is not None], key=lambda s: s._mem_pct, reverse=True)[:5]

    return tpl(
        request,
        "dashboard.html",
        {
            "user": user,
            "servers": servers,
            "total": total,
            "up_count": up_count,
            "down_count": total - up_count,
            "down_services": down_services,
            "ignored_services": ignored_services,
            "last_update_secs": last_update_secs,
            "all_groups": existing_groups,
            "all_tags": existing_tags,
            "group_counts": group_counts,
            "ungrouped_count": ungrouped_count,
            "danger_total": danger_total,
            "average_total": average_total,
            "warning_total": warning_total,
            "info_total": info_total,
            "ignored_total": ignored_total,
            "healthy_total": healthy_total,
            "all_open_problems": all_open_problems,
            "problems_by_sev": problems_by_sev,
            "top_cpu": top_cpu,
            "top_mem": top_mem,
            "global_thresholds": get_global_thresholds(db),
        },
    )


# ---------------------------------------------------------------------------
# PROBLEMS (agregat semua server)
# ---------------------------------------------------------------------------
@router.get("/problems", response_class=HTMLResponse)
def problems_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    filter_sid_str = request.query_params.get("server", "")
    filter_sid = int(filter_sid_str) if filter_sid_str.isdigit() else None
    filter_group = (request.query_params.get("group") or "").strip()

    res_period = (request.query_params.get("res_period") or "24h").strip().lower()
    if res_period not in ("today", "24h", "7d", "30d", "custom"):
        res_period = "24h"
    res_start = (request.query_params.get("start_date") or "").strip()
    res_end = (request.query_params.get("end_date") or "").strip()
    res_server_str = (request.query_params.get("res_server") or "").strip()
    res_server = int(res_server_str) if res_server_str.isdigit() else None
    res_sev = (request.query_params.get("res_sev") or "").strip()
    res_type = (request.query_params.get("res_type") or "").strip()
    res_q = (request.query_params.get("res_q") or "").strip()

    open_problems, recent_resolved = problems_aggregate(
        db,
        res_period=res_period,
        res_start=res_start,
        res_end=res_end,
        res_server=res_server,
        res_sev=res_sev,
        res_type=res_type,
        res_q=res_q,
    )
    if filter_sid:
        open_problems = [p for p in open_problems if p["server_id"] == filter_sid]
        recent_resolved = [p for p in recent_resolved if p["server_id"] == filter_sid]
    if filter_group:
        if filter_group == "__none__":
            open_problems = [p for p in open_problems if not p.get("group_name")]
            recent_resolved = [p for p in recent_resolved if not p.get("group_name")]
        else:
            open_problems = [p for p in open_problems if (p.get("group_name") or "") == filter_group]
            recent_resolved = [p for p in recent_resolved if (p.get("group_name") or "") == filter_group]

    all_servers = db.query(Server).order_by(Server.hostname).all()
    servers_total = len(all_servers)
    active_open_servers = {p["server_id"] for p in open_problems if not p.get("is_ignored")}
    existing_groups, existing_tags = get_existing_groups_and_tags(db)

    global_thresholds = get_global_thresholds(db)

    res_durations = []
    auto_res_cnt = 0
    manual_res_cnt = 0
    for p in recent_resolved:
        st = p.get("started_at")
        res = p.get("resolved_at")
        if isinstance(st, datetime) and isinstance(res, datetime):
            res_durations.append(max(0, int((res - st).total_seconds())))
        if p.get("res_type") == "manual" or p.get("acknowledged_by"):
            manual_res_cnt += 1
        else:
            auto_res_cnt += 1
    avg_secs = int(sum(res_durations) / len(res_durations)) if res_durations else 0
    avg_mttr_str = _fmt_duration(datetime.min, datetime.min + timedelta(seconds=avg_secs)) if avg_secs > 0 else "—"

    resolved_stats = {
        "total": len(recent_resolved),
        "avg_mttr": avg_mttr_str,
        "auto_count": auto_res_cnt,
        "manual_count": manual_res_cnt,
    }

    return tpl(
        request,
        "problems.html",
        {
            "user": user,
            "open_problems": open_problems,
            "recent_resolved": recent_resolved,
            "resolved_stats": resolved_stats,
            "danger_open": sum(1 for p in open_problems if p["severity"] == "danger" and not p.get("is_ignored")),
            "average_open": sum(1 for p in open_problems if p["severity"] == "average" and not p.get("is_ignored")),
            "warning_open": sum(1 for p in open_problems if p["severity"] == "warning" and not p.get("is_ignored")),
            "info_open": sum(1 for p in open_problems if p["severity"] == "info" and not p.get("is_ignored")),
            "ignored_open": sum(1 for p in open_problems if p.get("is_ignored")),
            "ok_count": servers_total - len(active_open_servers),
            "all_servers": all_servers,
            "filter_sid": filter_sid,
            "filter_group": filter_group,
            "res_period": res_period,
            "res_start": res_start,
            "res_end": res_end,
            "res_server": res_server,
            "res_sev": res_sev,
            "res_type": res_type,
            "res_q": res_q,
            "all_groups": existing_groups,
            "all_tags": existing_tags,
            "global_thresholds": global_thresholds,
            "default_thresholds": DEFAULT_THRESHOLDS,
        },
    )


# ---------------------------------------------------------------------------
# API ALERTS & REALTIME PROBLEMS
# ---------------------------------------------------------------------------
@router.get("/api/alerts")
def api_alerts(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Insiden terbuka lintas semua tingkat keparahan (danger, average, warning, info)."""
    now = datetime.utcnow()
    servers_list = db.query(Server).all()
    # Pastikan server offline/stale langsung tersinkronisasi tanpa jeda background loop
    stale_servers = [
        s for s in servers_list if getattr(s, "is_active", 1) and s.last_seen is not None and _server_stale(s)
    ]
    for st in stale_servers:
        try:
            sync_server_problems(db, st, _problem_instances(st, None, None, db))
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    host = {s.id: s.hostname for s in servers_list}
    probes_list = db.query(ProbeTarget).all()
    probes_map = {p.id: p.name for p in probes_list}
    probes_obj_map = {p.id: p for p in probes_list}
    probes_tier_map = {p.id: (getattr(p, "tier", 2) or 2) for p in probes_list}
    tier_map = {s.id: (getattr(s, "tier", 2) or 2) for s in servers_list}

    def get_effective_tier(r):
        if r.server_id and r.server_id in tier_map:
            return tier_map[r.server_id]
        if r.probe_id and r.probe_id in probes_tier_map:
            return probes_tier_map[r.probe_id]
        return 2

    def get_host_label(sid, pid=None):
        if sid and sid in host:
            return host[sid]
        if pid and pid in probes_map:
            return probes_map[pid]
        return f"Server #{sid}" if sid else "Eksternal"

    open_problems = (
        db.query(ServerProblem)
        .filter(
            ServerProblem.resolved_at.is_(None),
            (ServerProblem.is_ignored == 0) | (ServerProblem.is_ignored.is_(None)),
        )
        .order_by(desc(ServerProblem.started_at))
        .all()
    )

    open_danger = [r for r in open_problems if r.severity == "danger" and get_effective_tier(r) == 1]
    open_average = [r for r in open_problems if r.severity == "average" and get_effective_tier(r) == 1]
    open_warning = [
        r
        for r in open_problems
        if (r.severity == "warning") or (get_effective_tier(r) != 1 and r.severity != "info")
    ]
    open_info = [r for r in open_problems if r.severity == "info"]

    unack_danger = [r for r in open_danger if r.acknowledged_at is None]
    unack_average = [r for r in open_average if r.acknowledged_at is None]
    unack_warning = [r for r in open_warning if r.acknowledged_at is None]

    # Filter Anti-Spike: Beban resource (CPU/RAM/Swap) yang menyentuh ambang batas
    # ditahan selama 60 detik sebelum memicu Alert Banner & Audio darurat
    RESOURCE_ALERT_DELAY_SECS = 60

    def _is_alert_banner_firing(r, now_dt):
        if getattr(r, "is_ignored", 0):
            return False
        if get_effective_tier(r) != 1:
            return False
        if r.probe_id:
            prb_obj = probes_obj_map.get(r.probe_id)
            if prb_obj and (getattr(prb_obj, "uptime_24h", 0) == 0 and (prb_obj.consecutive_successes or 0) == 0):
                return False
        reason = getattr(r, "ignored_reason", None) or ""
        if "DIMATIKAN OLEH OPERATOR" in reason or "DIHENTIKAN OLEH OPERATOR" in reason:
            return False
        msg_txt = getattr(r, "message", "") or ""
        if "dimatikan oleh operator" in msg_txt.lower() or "dihentikan oleh operator" in msg_txt.lower():
            return False
        key = getattr(r, "key", "") or ""
        if key in ("agent_outdated", "apt_updates"):
            return False
        if key.startswith(("ram_", "cpu_", "swap_")):
            st = getattr(r, "started_at", None)
            if st and (now_dt - st).total_seconds() < RESOURCE_ALERT_DELAY_SECS:
                return False
        return True

    firing_danger = [r for r in unack_danger if _is_alert_banner_firing(r, now)]
    firing_average = [r for r in unack_average if _is_alert_banner_firing(r, now)]
    firing_warning = [r for r in unack_warning if _is_alert_banner_firing(r, now)]

    rank = {"danger": 4, "average": 3, "warning": 2, "info": 1}
    unack_operational = sorted(
        unack_danger + unack_average + unack_warning,
        key=lambda r: (rank.get(r.severity, 0), r.started_at),
        reverse=True,
    )
    firing_operational = sorted(
        firing_danger + firing_average + firing_warning,
        key=lambda r: (rank.get(r.severity, 0), r.started_at),
        reverse=True,
    )

    danger_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in unack_danger]
    average_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in unack_average]
    warning_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in unack_warning]
    info_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in open_info]
    info_hosts = sorted(list({get_host_label(r.server_id, r.probe_id) for r in open_info}))
    firing_danger_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in firing_danger]
    firing_average_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in firing_average]
    firing_warning_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in firing_warning]
    all_unack_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in unack_operational]
    firing_alerts = [_alert_dict(r, get_host_label(r.server_id, r.probe_id), now) for r in firing_operational]

    danger_hosts = sorted(list({get_host_label(r.server_id, r.probe_id) for r in open_danger}))
    average_hosts = sorted(list({get_host_label(r.server_id, r.probe_id) for r in open_average}))
    warning_hosts = sorted(list({get_host_label(r.server_id, r.probe_id) for r in open_warning}))
    firing_danger_hosts = sorted(list({get_host_label(r.server_id, r.probe_id) for r in firing_danger}))
    firing_average_hosts = sorted(list({get_host_label(r.server_id, r.probe_id) for r in firing_average}))
    firing_warning_hosts = sorted(list({get_host_label(r.server_id, r.probe_id) for r in firing_warning}))

    host_danger_counts = {}
    for r in open_danger:
        hname = get_host_label(r.server_id, r.probe_id)
        host_danger_counts[hname] = host_danger_counts.get(hname, 0) + 1

    host_average_counts = {}
    for r in open_average:
        hname = get_host_label(r.server_id, r.probe_id)
        host_average_counts[hname] = host_average_counts.get(hname, 0) + 1

    host_warning_counts = {}
    for r in open_warning:
        hname = get_host_label(r.server_id, r.probe_id)
        host_warning_counts[hname] = host_warning_counts.get(hname, 0) + 1

    if open_danger:
        highest_severity = "danger"
    elif open_average:
        highest_severity = "average"
    elif open_warning:
        highest_severity = "warning"
    elif open_info:
        highest_severity = "info"
    else:
        highest_severity = "ok"

    active_m_count, active_m_titles = get_active_maintenance_info()

    return {
        "alerts": firing_danger_alerts,
        "all_alerts": all_unack_alerts,
        "danger_alerts": danger_alerts,
        "firing_danger_alerts": firing_danger_alerts,
        "average_alerts": average_alerts,
        "firing_average_alerts": firing_average_alerts,
        "warning_alerts": warning_alerts,
        "info_alerts": info_alerts,
        "info_hosts": info_hosts,
        "firing_alerts": firing_alerts,
        "unack_count": len(firing_danger),
        "unack_danger_count": len(firing_danger),
        "unack_average_count": len(average_alerts),
        "unack_warning_count": len(warning_alerts),
        "unack_total_count": len(all_unack_alerts),
        "firing_danger_count": len(firing_danger),
        "firing_average_count": len(firing_average),
        "firing_warning_count": len(firing_warning),
        "firing_total_count": len(firing_operational),
        "open_danger_count": len(open_danger),
        "open_average_count": len(open_average),
        "open_warning_count": len(open_warning),
        "open_info_count": len(open_info),
        "total_open_count": len(open_problems),
        "acked_count": len(open_danger) - len(danger_alerts),
        "danger_hosts": danger_hosts,
        "average_hosts": average_hosts,
        "warning_hosts": warning_hosts,
        "firing_danger_hosts": firing_danger_hosts,
        "firing_average_hosts": firing_average_hosts,
        "firing_warning_hosts": firing_warning_hosts,
        "firing_warning_alerts": firing_warning_alerts,
        "host_danger_counts": host_danger_counts,
        "host_average_counts": host_average_counts,
        "host_warning_counts": host_warning_counts,
        "highest_severity": highest_severity,
        "active_maintenance_count": active_m_count,
        "active_maintenance_titles": active_m_titles,
    }


@router.get("/api/problems")
def api_problems(
    server: int | None = None,
    group: str | None = None,
    res_period: str = "24h",
    res_start: str | None = None,
    res_end: str | None = None,
    res_server: int | None = None,
    res_sev: str | None = None,
    res_type: str | None = None,
    res_q: str | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Endpoint realtime JSON untuk halaman /problems dan pemantauan aktif."""
    p_clean = (res_period or "24h").strip().lower()
    if p_clean not in ("today", "24h", "7d", "30d", "custom"):
        p_clean = "24h"
    open_problems, recent_resolved = problems_aggregate(
        db,
        res_period=p_clean,
        res_start=res_start,
        res_end=res_end,
        res_server=res_server,
        res_sev=res_sev,
        res_type=res_type,
        res_q=res_q,
    )
    if server:
        open_problems = [p for p in open_problems if p.get("server_id") == server]
        recent_resolved = [p for p in recent_resolved if p.get("server_id") == server]
    if group:
        g_clean = group.strip()
        if g_clean == "__none__":
            open_problems = [p for p in open_problems if not p.get("group_name")]
            recent_resolved = [p for p in recent_resolved if not p.get("group_name")]
        else:
            open_problems = [p for p in open_problems if (p.get("group_name") or "") == g_clean]
            recent_resolved = [p for p in recent_resolved if (p.get("group_name") or "") == g_clean]

    def _serialize(prob):
        p = dict(prob)
        if isinstance(p.get("started_at"), datetime):
            p["started_at_iso"] = p["started_at"].replace(tzinfo=None).isoformat() + "Z"
            p["started_at_str"] = _fmt_dt(p["started_at"], with_sec=True)
            p["started_at"] = _fmt_dt(p["started_at"], with_sec=True)
        if isinstance(p.get("resolved_at"), datetime):
            p["resolved_at_iso"] = p["resolved_at"].replace(tzinfo=None).isoformat() + "Z"
            p["resolved_at_str"] = _fmt_dt(p["resolved_at"], with_sec=True)
            p["resolved_at_date"] = p["resolved_at"].strftime("%Y-%m-%d")
            p["resolved_at"] = _fmt_dt(p["resolved_at"], with_sec=True)
        if isinstance(p.get("acknowledged_at"), datetime):
            p["acknowledged_at_str"] = _fmt_dt(p["acknowledged_at"], with_sec=True)
            p["acknowledged_at"] = _fmt_dt(p["acknowledged_at"], with_sec=True)
        if isinstance(p.get("ignored_until"), datetime):
            p["ignored_until_str"] = _fmt_dt(p["ignored_until"], with_sec=True)
            p["ignored_until"] = _fmt_dt(p["ignored_until"], with_sec=True)
        return p

    open_serialized = [_serialize(p) for p in open_problems]
    resolved_serialized = [_serialize(p) for p in recent_resolved]

    servers_total = db.query(Server).count()
    active_open_servers = {p["server_id"] for p in open_problems if not p.get("is_ignored")}

    res_durations = []
    auto_cnt = 0
    manual_cnt = 0
    for p in recent_resolved:
        st = p.get("started_at")
        res = p.get("resolved_at")
        if isinstance(st, datetime) and isinstance(res, datetime):
            res_durations.append(max(0, int((res - st).total_seconds())))
        if p.get("res_type") == "manual" or p.get("acknowledged_by"):
            manual_cnt += 1
        else:
            auto_cnt += 1
    avg_s = int(sum(res_durations) / len(res_durations)) if res_durations else 0
    avg_mttr_str = _fmt_duration(datetime.min, datetime.min + timedelta(seconds=avg_s)) if avg_s > 0 else "—"

    return {
        "open_problems": open_serialized,
        "recent_resolved": resolved_serialized,
        "summary": {
            "danger_open": sum(1 for p in open_problems if p.get("severity") == "danger" and not p.get("is_ignored")),
            "average_open": sum(1 for p in open_problems if p.get("severity") == "average" and not p.get("is_ignored")),
            "warning_open": sum(1 for p in open_problems if p.get("severity") == "warning" and not p.get("is_ignored")),
            "info_open": sum(1 for p in open_problems if p.get("severity") == "info" and not p.get("is_ignored")),
            "ignored_open": sum(1 for p in open_problems if p.get("is_ignored")),
            "ok_count": servers_total - len(active_open_servers),
            "total_open": len(open_problems),
            "total_resolved": len(recent_resolved),
            "avg_mttr": avg_mttr_str,
            "auto_resolved": auto_cnt,
            "manual_resolved": manual_cnt,
        },
    }


@router.post("/api/alerts/{pid}/ack")
def api_alert_ack(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Acknowledge peringatan (semua level) agar tidak mengganggu terus-menerus."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Viewer tidak memiliki izin melakukan tindakan pada insiden",
        )
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Insiden tidak ditemukan")
    row.acknowledged_at = datetime.utcnow()
    row.acknowledged_by = user.username
    _audit(
        db,
        user.username,
        "problem_ack",
        target=row.message[:100],
        result="di-ack",
        server_id=row.server_id,
    )
    db.commit()
    return {"ok": True, "id": pid, "acknowledged_by": user.username}


@router.post("/api/alerts/{pid}/resolve")
def api_alert_resolve(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Selesaikan insiden secara manual bila operator telah memverifikasi perbaikan."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Viewer tidak memiliki izin menyelesaikan insiden",
        )
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Insiden tidak ditemukan")
    now = datetime.utcnow()
    row.resolved_at = now
    row.resolved_note = _clean_str(f"manual ({user.username})", "manual", 100)
    row.acknowledged_at = row.acknowledged_at or now
    row.acknowledged_by = row.acknowledged_by or user.username
    _audit(
        db,
        user.username,
        "problem_resolve",
        target=row.message[:100],
        result="diselesaikan manual",
        server_id=row.server_id,
    )
    db.commit()
    return {"ok": True, "id": pid, "resolved_by": user.username}


@router.post("/api/alerts/{pid}/ignore")
def api_alert_ignore(
    pid: int,
    request: Request,
    body: dict = Body(default={}),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Abaikan peringatan atau masalah (tunda alarm kritis)."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Viewer tidak memiliki izin mengabaikan insiden",
        )
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Insiden tidak ditemukan")

    duration = str(body.get("duration", "24h")).lower().strip()
    reason = str(body.get("reason", "")).strip()[:255] or None

    now = datetime.utcnow()
    until = None
    ignore_mode = "duration"
    if duration == "2h":
        until = now + timedelta(hours=2)
    elif duration == "24h":
        until = now + timedelta(hours=24)
    elif duration == "7d":
        until = now + timedelta(days=7)
    elif duration == "30d":
        until = now + timedelta(days=30)
    elif duration in ("0", "perm", "permanent", "forever"):
        until = None
        ignore_mode = "permanent"
    elif duration == "incident":
        until = None
        ignore_mode = "incident"
    else:
        until = now + timedelta(hours=24)

    row.is_ignored = 1
    row.ignored_until = until
    row.ignored_by = user.username
    row.ignored_reason = reason or f"diabaikan oleh {user.username}"
    row.ignore_mode = ignore_mode
    row.updated_at = now
    if not row.acknowledged_at:
        row.acknowledged_at = now
        row.acknowledged_by = user.username

    # Jika masalah ini adalah service_down, sinkronkan ke tabel Service
    if row.key.startswith("service_down:"):
        svc_name = row.key.split(":", 1)[1]
        svc = db.query(Service).filter(
            Service.server_id == row.server_id,
            Service.service_name == svc_name,
        ).first()
        if svc:
            svc.is_ignored = 1
            svc.ignored_until = until
            svc.ignored_by = user.username
            svc.ignored_reason = reason or f"diabaikan oleh {user.username}"
            svc.ignore_mode = ignore_mode

    dur_label = f" ({duration})" if ignore_mode != "permanent" else " (permanen)"
    if ignore_mode == "incident":
        dur_label = " (hanya insiden saat ini)"
    res_str = f"diabaikan{dur_label}" + (f": {reason}" if reason else "")
    _audit(
        db,
        user.username,
        "problem_ignore",
        target=row.message[:100],
        result=res_str,
        server_id=row.server_id,
    )
    db.commit()
    return {
        "ok": True,
        "id": pid,
        "is_ignored": True,
        "ignored_until": until.isoformat() if until else None,
        "ignore_mode": ignore_mode,
        "ignored_by": user.username,
        "ignored_reason": reason,
    }


@router.post("/api/alerts/{pid}/unignore")
def api_alert_unignore(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Batalkan pengabaian / aktifkan kembali pemantauan masalah."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Viewer tidak memiliki izin memulihkan pengabaian insiden",
        )
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Insiden tidak ditemukan")

    # Bersihkan seluruh riwayat pengabaian pada masalah ini dan key terkait di server ini
    db.query(ServerProblem).filter(
        ServerProblem.server_id == row.server_id,
        ServerProblem.key == row.key,
    ).update(
        {
            ServerProblem.is_ignored: 0,
            ServerProblem.ignored_until: None,
            ServerProblem.ignored_reason: None,
            ServerProblem.ignore_mode: None,
        },
        synchronize_session=False,
    )

    row.is_ignored = 0
    row.ignored_until = None
    row.ignored_reason = None
    row.ignore_mode = None
    row.updated_at = datetime.utcnow()

    # Jika masalah ini adalah service_down, batalkan juga abaikan pada tabel Service
    if row.key.startswith("service_down:"):
        svc_name = row.key.split(":", 1)[1]
        svc = db.query(Service).filter(
            Service.server_id == row.server_id,
            Service.service_name == svc_name,
        ).first()
        if svc:
            svc.is_ignored = 0
            svc.ignored_until = None
            svc.ignored_reason = None
            svc.ignore_mode = None

    _audit(
        db,
        user.username,
        "problem_unignore",
        target=row.message[:100],
        result="pemantauan diaktifkan kembali",
        server_id=row.server_id,
    )
    db.commit()
    return {"ok": True, "id": pid, "is_ignored": False}


# ---------------------------------------------------------------------------
# SYSTEM STATUS & VERSION
# ---------------------------------------------------------------------------
@router.get("/api/system/version")
def api_system_version():
    """Endpoint publik ringan untuk sinkronisasi otomatis antarmuka browser (Live Version Watcher)."""
    return {
        "version": settings.APP_VERSION,
        "boot_time": _SERVER_BOOT_TIME,
    }


@router.get("/api/system/status")
def api_system_status(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Status sumber daya internal host server Pantau."""
    return {
        "hostname": socket.gethostname(),
        "uptime": _proc_uptime(),
        "loadavg": _proc_loadavg(),
        "cpu": _proc_cpu(),
        "memory": _proc_memory(),
        "disks": _proc_disks(),
        "processes": _proc_top(),
    }
