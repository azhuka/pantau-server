"""
Router Manajemen Server Pantau.
Menangani katalog server, tambah/edit server, rotasi API key,
detail server (tab services, users, cron, ports, ssl, firewall, packages, logs),
riwayat aktivitas/kinerja host (perf, system snapshot, storage runway),
serta tindakan pemeliharaan dan catatan server.
"""

from datetime import datetime, timezone, timedelta
import json
import logging
import os
import re
import secrets
import time

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from config import settings
from core.database import get_db
from core.security import (
    get_current_user,
    require_user,
    _verify_csrf_form,
    _verify_csrf_header,
    _verify_operator_password,
)
from core.templates import tpl
from core.utils import (
    _clean_str,
    _validate_ip,
    hash_api_key,
    api_key_fingerprint,
    _is_agent_outdated,
    _flash_qs,
    _fmt_dt,
)
from models import (
    Command,
    FIMEvent,
    FIMPath,
    LogRequest,
    Metric,
    Server,
    ServerExtras,
    ServerProblem,
    Service,
    SysSnapshotHour,
    SystemSnapshot,
    User,
)
from services.audit_service import _audit
from services.hardware_service import (
    _clean_cpu_model,
    _extract_disk_stats,
    _extract_disks_summary,
    _extract_hw_model,
    _extract_primary_interface,
    _classify_platform,
    _get_hardware_specs_dict,
    _format_ignored_prob_msg,
    _format_bytes_gb,
    _format_uptime_str,
    _get_storage_runway_for_server,
)
from services.problem_service import (
    get_global_thresholds,
    sync_server_problems,
    _problem_instances,
    _serialize_problem_list,
    _enrich_problems_for_ui,
)
from services.server_service import (
    _server_stale,
    _server_status,
    _latest_metrics,
    get_existing_groups_and_tags,
    _uptime_stats_cache,
    _get_server_actions,
    _check_server_online,
)
from services.system_service import (
    APT_UNITS,
    SHELL_UNIT,
    VALID_UNIT_RE,
)

logger = logging.getLogger("pantau.servers")

router = APIRouter(tags=["Servers"])


# ---------------------------------------------------------------------------
# SERVERS LIST & FORM
# ---------------------------------------------------------------------------
@router.get("/servers", response_class=HTMLResponse)
def servers_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    extras_map = {ex.server_id: ex for ex in db.query(ServerExtras).all()}
    server_ids = [s.id for s in servers]
    svc_counts = (
        dict(
            db.query(Service.server_id, func.count(Service.id))
            .filter(Service.server_id.in_(server_ids))
            .group_by(Service.server_id)
            .all()
        )
        if server_ids
        else {}
    )

    for srv in servers:
        srv._service_count = svc_counts.get(srv.id, 0)
        srv._key_fp = api_key_fingerprint(srv.api_key)
        ex = extras_map.get(srv.id)
        srv._apt_upgradable = ex.apt_upgradable if ex else None
        srv._apt_last_update = ex.apt_last_update if ex and ex.apt_last_update else None
        srv._os_label = ex.os_label if ex else None
        srv._arch = ex.arch if ex else None
        srv._agent_version = ex.agent_version if ex else None
        srv._agent_outdated = _is_agent_outdated(srv._agent_version, settings.APP_VERSION)
        srv._online = not _server_stale(srv)
        services = db.query(Service).filter(Service.server_id == srv.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        svc_data = []
        for svc in services:
            latest = latest_map.get(svc.id)
            svc_data.append(
                {
                    "name": svc.service_name,
                    "port": svc.port,
                    "process": svc.process_name,
                    "is_core": bool(getattr(svc, "is_core", 1)),
                    "status": latest.status if latest else "unknown",
                }
            )
        srv._problem_level, srv._problems, _ph = sync_server_problems(
            db, srv, _problem_instances(srv, ex, svc_data, db)
        )
        ignored_keys = {p.get("key") for p in srv._problems if p.get("is_ignored")}
        svc_ignored_db = {s.service_name for s in services if getattr(s, "is_ignored", 0)}
        for d in svc_data:
            if f"service_down:{d['name']}" in ignored_keys or d["name"] in svc_ignored_db:
                d["ignored"] = True
        srv._svc_data = svc_data

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
        hw = _get_hardware_specs_dict(srv, ex, latest_sys)
        srv._platform = _classify_platform(hw.get("platform", {}), getattr(srv, "platform_override", None))
        srv._hw = hw
        srv._cpu_model = _clean_cpu_model(hw.get("cpu", {}).get("model"))
        srv._cpu_cores = hw.get("cpu", {}).get("cores") or hw.get("cpu", {}).get("logical_cores") or 0
        srv._hw_model = _extract_hw_model(hw.get("platform"))
        srv._prim_iface = _extract_primary_interface(hw.get("network"))
        srv._os_name = hw.get("os", {}).get("os_name") or (ex.os_label if ex else "Linux")
        srv._kernel = hw.get("os", {}).get("kernel") or (ex.kernel if ex else "—")
        srv._arch = hw.get("cpu", {}).get("arch") or (ex.arch if ex else "x86_64")
        srv._boot_time = hw.get("os", {}).get("boot_time") or "—"
        mem = hw.get("memory", {})
        ram_b = mem.get("ram_total") or (latest_sys.mem_total if latest_sys else 0)
        swap_b = mem.get("swap_total") or (latest_sys.swap_total if latest_sys else 0)
        srv._ram_total_str = _format_bytes_gb(ram_b if ram_b else (latest_sys.mem_total if latest_sys else None))
        srv._swap_total_str = _format_bytes_gb(swap_b if swap_b else (latest_sys.swap_total if latest_sys else None))
        srv._disk_str = _extract_disks_summary(hw.get("disks"))
        srv._uptime_str = _format_uptime_str(latest_sys.uptime_secs if latest_sys else None)
        srv._uptime_secs = latest_sys.uptime_secs if (latest_sys and latest_sys.uptime_secs) else 0

        unignored_down = [d for d in svc_data if d.get("status") in ("down", "offline") and not d.get("ignored")]
        is_ign_stale = False
        if not srv._online:
            is_ign_stale = any(
                p.get("key") == "agent_stale" and p.get("is_ignored") for p in getattr(srv, "_problems", []) or []
            )
        srv._is_ignored_stale = is_ign_stale
        if srv.is_maintenance:
            srv._status_label, srv._status_cls = "Pemeliharaan", "badge-warn"
        else:
            srv._status_label, srv._status_cls = _server_status(
                srv,
                not srv._online,
                bool(svc_data),
                any(d["status"] == "up" for d in svc_data),
                has_unignored_down=bool(unignored_down),
                is_ignored_stale=is_ign_stale,
            )

    existing_groups, existing_tags = get_existing_groups_and_tags(db)
    group_counts = {}
    ungrouped_count = 0
    for srv in servers:
        if srv.group_name:
            group_counts[srv.group_name] = group_counts.get(srv.group_name, 0) + 1
        else:
            ungrouped_count += 1

    servers.sort(key=lambda s: (0 if s.group_name else 1, (s.group_name or "").lower(), s.hostname.lower()))

    return tpl(
        request,
        "servers.html",
        {
            "user": user,
            "servers": servers,
            "all_groups": existing_groups,
            "all_tags": existing_tags,
            "group_counts": group_counts,
            "ungrouped_count": ungrouped_count,
        },
    )


@router.get("/servers/add", response_class=HTMLResponse)
def server_add_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    existing_groups, existing_tags = get_existing_groups_and_tags(db)
    global_th = get_global_thresholds(db)
    return tpl(
        request,
        "server_form.html",
        {
            "user": user,
            "server": None,
            "mode": "add",
            "existing_groups": existing_groups,
            "existing_tags": existing_tags,
            "global_thresholds": global_th,
            "custom_thresholds": {},
            "detected_platform": None,
        },
    )


@router.post("/servers/add")
def server_add_submit(
    request: Request,
    hostname: str = Form(...),
    ip_address: str = Form(...),
    group_name: str = Form(default=""),
    tags: str = Form(default=""),
    notes: str = Form(default=""),
    tier: int = Form(2),
    platform_override: str = Form(default="auto"),
    is_proxmox_ha: int = Form(0),
    is_isolated_net: int = Form(0),
    allow_web_terminal: int = Form(0),
    th_cpu_warn: str = Form(default=""),
    th_cpu_average: str = Form(default=""),
    th_cpu_danger: str = Form(default=""),
    th_ram_warn: str = Form(default=""),
    th_ram_average: str = Form(default=""),
    th_ram_danger: str = Form(default=""),
    th_disk_warn: str = Form(default=""),
    th_disk_average: str = Form(default=""),
    th_disk_danger: str = Form(default=""),
    th_swap_warn: str = Form(default=""),
    th_swap_average: str = Form(default=""),
    th_swap_danger: str = Form(default=""),
    th_ssh_fail_warn: str = Form(default=""),
    th_ssh_fail_danger: str = Form(default=""),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    hostname = _clean_str(hostname, "", 255)
    ip_address = _clean_str(ip_address, "", 45)[:45]
    group_name_clean = _clean_str(group_name, "", 64).strip()
    group_name = group_name_clean if group_name_clean and group_name_clean.lower() != "default" else None
    tags_clean = _clean_str(tags, "", 255).strip()
    tags = tags_clean if tags_clean else None
    notes_clean = (notes or "").strip() or None
    tier_val = 1 if tier == 1 else 2
    if ip_address and not _validate_ip(ip_address):
        existing_groups, existing_tags = get_existing_groups_and_tags(db)
        return tpl(
            request,
            "server_form.html",
            {
                "user": user,
                "server": None,
                "mode": "add",
                "existing_groups": existing_groups,
                "existing_tags": existing_tags,
                "global_thresholds": get_global_thresholds(db),
                "custom_thresholds": {},
                "error": "Format IP address tidak valid. Gunakan IPv4 (contoh: 192.168.1.1) atau IPv6.",
            },
        )

    custom_th = {}
    for k, val in [
        ("cpu_warn", th_cpu_warn),
        ("cpu_average", th_cpu_average),
        ("cpu_danger", th_cpu_danger),
        ("ram_warn", th_ram_warn),
        ("ram_average", th_ram_average),
        ("ram_danger", th_ram_danger),
        ("disk_warn", th_disk_warn),
        ("disk_average", th_disk_average),
        ("disk_danger", th_disk_danger),
        ("swap_warn", th_swap_warn),
        ("swap_average", th_swap_average),
        ("swap_danger", th_swap_danger),
        ("ssh_fail_warn", th_ssh_fail_warn),
        ("ssh_fail_danger", th_ssh_fail_danger),
    ]:
        if val is not None and str(val).strip() != "":
            try:
                custom_th[k] = int(val) if "fail" in k else float(val)
            except ValueError:
                pass
    for metric in ("cpu", "ram", "disk", "swap"):
        w = custom_th.get(f"{metric}_warn")
        a = custom_th.get(f"{metric}_average")
        d = custom_th.get(f"{metric}_danger")
        vals = [v for v in (w, a, d) if v is not None]
        if vals != sorted(vals):
            s_vals = sorted(vals)
            idx = 0
            if w is not None:
                custom_th[f"{metric}_warn"] = s_vals[idx]
                idx += 1
            if a is not None:
                custom_th[f"{metric}_average"] = s_vals[idx]
                idx += 1
            if d is not None:
                custom_th[f"{metric}_danger"] = s_vals[idx]
    w_ssh = custom_th.get("ssh_fail_warn")
    d_ssh = custom_th.get("ssh_fail_danger")
    if w_ssh is not None and d_ssh is not None and w_ssh > d_ssh:
        custom_th["ssh_fail_warn"], custom_th["ssh_fail_danger"] = d_ssh, w_ssh
    custom_th_json = json.dumps(custom_th) if custom_th else None

    plat_override_clean = (platform_override or "").strip().lower()
    if plat_override_clean not in ("baremetal", "vm", "lxc"):
        plat_override_clean = None

    raw = secrets.token_hex(32)
    srv = Server(
        hostname=hostname,
        ip_address=ip_address,
        group_name=group_name,
        tags=tags,
        notes=notes_clean,
        tier=tier_val,
        is_proxmox_ha=1 if (is_proxmox_ha and plat_override_clean != "baremetal") else 0,
        platform_override=plat_override_clean,
        is_isolated_net=1 if is_isolated_net else 0,
        allow_web_terminal=1 if allow_web_terminal else 0,
        custom_thresholds=custom_th_json,
        api_key=hash_api_key(raw),
    )
    db.add(srv)
    _audit(
        db,
        user.username,
        "server_add",
        f"{hostname} ({ip_address}) [Lingkungan: {'Produksi' if tier_val == 1 else 'Non-Produksi'}]"
        + (f" [Grup: {group_name}]" if group_name else ""),
        "berhasil",
    )
    db.commit()
    resp = tpl(request, "key_reveal.html", {"user": user, "server": srv, "api_key": raw})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/servers/{sid}/edit", response_class=HTMLResponse)
def server_edit_page(request: Request, sid: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    server._key_fp = api_key_fingerprint(server.api_key)
    existing_groups, existing_tags = get_existing_groups_and_tags(db)
    global_th = get_global_thresholds(db)
    custom_th = {}
    if server.custom_thresholds:
        try:
            custom_th = json.loads(server.custom_thresholds)
        except Exception:
            pass
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    detected_platform = None
    if extra and extra.hardware_specs:
        try:
            hw = json.loads(extra.hardware_specs) if isinstance(extra.hardware_specs, str) else extra.hardware_specs
            plat_dict = hw.get("platform", {}) if isinstance(hw, dict) else {}
            detected_platform = _classify_platform(plat_dict, override=None)
        except Exception:
            pass
    return tpl(
        request,
        "server_form.html",
        {
            "user": user,
            "server": server,
            "mode": "edit",
            "existing_groups": existing_groups,
            "existing_tags": existing_tags,
            "global_thresholds": global_th,
            "custom_thresholds": custom_th,
            "detected_platform": detected_platform,
        },
    )


@router.post("/servers/{sid}/edit")
def server_edit_submit(
    request: Request,
    sid: int,
    hostname: str = Form(...),
    ip_address: str = Form(...),
    group_name: str = Form(default=""),
    tags: str = Form(default=""),
    notes: str = Form(default=""),
    tier: int = Form(2),
    is_active: int = Form(1),
    platform_override: str = Form(default="auto"),
    is_proxmox_ha: int = Form(0),
    is_isolated_net: int = Form(0),
    allow_web_terminal: int = Form(0),
    th_cpu_warn: str = Form(default=""),
    th_cpu_average: str = Form(default=""),
    th_cpu_danger: str = Form(default=""),
    th_ram_warn: str = Form(default=""),
    th_ram_average: str = Form(default=""),
    th_ram_danger: str = Form(default=""),
    th_disk_warn: str = Form(default=""),
    th_disk_average: str = Form(default=""),
    th_disk_danger: str = Form(default=""),
    th_swap_warn: str = Form(default=""),
    th_swap_average: str = Form(default=""),
    th_swap_danger: str = Form(default=""),
    th_ssh_fail_warn: str = Form(default=""),
    th_ssh_fail_danger: str = Form(default=""),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if server:
        hostname = _clean_str(hostname, server.hostname, 255)
        ip_address = _clean_str(ip_address, server.ip_address, 45)[:45]
        group_name_clean = _clean_str(group_name, "", 64).strip()
        group_name = group_name_clean if group_name_clean and group_name_clean.lower() != "default" else None
        tags_clean = _clean_str(tags, "", 255).strip()
        tags = tags_clean if tags_clean else None
        tier_val = 1 if tier == 1 else 2
        if ip_address and not _validate_ip(ip_address):
            server._key_fp = api_key_fingerprint(server.api_key)
            existing_groups, existing_tags = get_existing_groups_and_tags(db)
            return tpl(
                request,
                "server_form.html",
                {
                    "user": user,
                    "server": server,
                    "mode": "edit",
                    "existing_groups": existing_groups,
                    "existing_tags": existing_tags,
                    "global_thresholds": get_global_thresholds(db),
                    "custom_thresholds": {},
                    "error": "Format IP address tidak valid. Gunakan IPv4 (contoh: 192.168.1.1) atau IPv6.",
                },
            )

        custom_th = {}
        for k, val in [
            ("cpu_warn", th_cpu_warn),
            ("cpu_average", th_cpu_average),
            ("cpu_danger", th_cpu_danger),
            ("ram_warn", th_ram_warn),
            ("ram_average", th_ram_average),
            ("ram_danger", th_ram_danger),
            ("disk_warn", th_disk_warn),
            ("disk_average", th_disk_average),
            ("disk_danger", th_disk_danger),
            ("swap_warn", th_swap_warn),
            ("swap_average", th_swap_average),
            ("swap_danger", th_swap_danger),
            ("ssh_fail_warn", th_ssh_fail_warn),
            ("ssh_fail_danger", th_ssh_fail_danger),
        ]:
            if val is not None and str(val).strip() != "":
                try:
                    custom_th[k] = int(val) if "fail" in k else float(val)
                except ValueError:
                    pass
        for metric in ("cpu", "ram", "disk", "swap"):
            w = custom_th.get(f"{metric}_warn")
            a = custom_th.get(f"{metric}_average")
            d = custom_th.get(f"{metric}_danger")
            vals = [v for v in (w, a, d) if v is not None]
            if vals != sorted(vals):
                s_vals = sorted(vals)
                idx = 0
                if w is not None:
                    custom_th[f"{metric}_warn"] = s_vals[idx]
                    idx += 1
                if a is not None:
                    custom_th[f"{metric}_average"] = s_vals[idx]
                    idx += 1
                if d is not None:
                    custom_th[f"{metric}_danger"] = s_vals[idx]
        w_ssh = custom_th.get("ssh_fail_warn")
        d_ssh = custom_th.get("ssh_fail_danger")
        if w_ssh is not None and d_ssh is not None and w_ssh > d_ssh:
            custom_th["ssh_fail_warn"], custom_th["ssh_fail_danger"] = d_ssh, w_ssh
        custom_th_json = json.dumps(custom_th) if custom_th else None

        plat_override_clean = (platform_override or "").strip().lower()
        if plat_override_clean not in ("baremetal", "vm", "lxc"):
            plat_override_clean = None

        server.hostname = hostname
        server.ip_address = ip_address
        server.group_name = group_name
        server.tags = tags
        server.notes = (notes or "").strip() or None
        server.tier = tier_val
        server.custom_thresholds = custom_th_json
        server.is_active = 1 if is_active else 0
        server.platform_override = plat_override_clean
        server.is_proxmox_ha = 1 if (is_proxmox_ha and plat_override_clean != "baremetal") else 0
        server.is_isolated_net = 1 if is_isolated_net else 0
        server.allow_web_terminal = 1 if allow_web_terminal else 0
        _audit(
            db,
            user.username,
            "server_edit",
            f"id={server.id} {server.hostname} ({server.ip_address}) [Lingkungan: {'Produksi' if tier_val == 1 else 'Non-Produksi'}]"
            + (f" [Grup: {group_name}]" if group_name else ""),
            "berhasil",
        )
        db.commit()
        return RedirectResponse("/servers" + _flash_qs(True, "Server diperbarui"), status_code=303)
    return RedirectResponse("/servers" + _flash_qs(False, "Server tidak ditemukan"), status_code=303)


@router.post("/servers/{sid}/regenerate-key")
def server_regenerate_key(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    password: str = Form(default=""),
    totp: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not user.is_master_admin():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)

    try:
        _verify_operator_password(
            user,
            password,
            totp_code=totp,
            action_name="key_regenerate",
            target_info=f"{server.hostname} (id={server.id})",
            db=db,
        )
    except HTTPException as exc:
        return RedirectResponse(f"/servers/{sid}/edit" + _flash_qs(False, exc.detail), status_code=303)

    raw = secrets.token_hex(32)
    server.api_key = hash_api_key(raw)
    _audit(db, user.username, "key_regenerate", f"{server.hostname} (id={server.id})", "berhasil")
    db.commit()
    resp = tpl(request, "key_reveal.html", {"user": user, "server": server, "api_key": raw})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/servers/{sid}/delete")
def server_delete(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    password: str = Form(default=""),
    totp: str = Form(default=""),
    confirm_hostname: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers" + _flash_qs(False, "Server tidak ditemukan"), status_code=303)

    if confirm_hostname and confirm_hostname.strip().lower() != server.hostname.strip().lower():
        return RedirectResponse(
            "/servers" + _flash_qs(False, f"Nama konfirmasi server tidak cocok (harus '{server.hostname}')"),
            status_code=303,
        )

    try:
        _verify_operator_password(
            user,
            password,
            totp_code=totp,
            action_name="server_delete",
            target_info=f"{server.hostname} ({server.ip_address}) id={server.id}",
            db=db,
        )
    except HTTPException as exc:
        return RedirectResponse("/servers" + _flash_qs(False, exc.detail), status_code=303)

    _audit(
        db,
        user.username,
        "server_delete",
        f"{server.hostname} ({server.ip_address}) id={server.id}",
        "berhasil",
    )
    db.delete(server)
    db.commit()
    return RedirectResponse("/servers" + _flash_qs(True, "Server dihapus"), status_code=303)


@router.post("/api/servers/{sid}/reset-platform-auto")
def api_reset_platform_auto(
    sid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Sinkronkan kembali konfigurasi platform server ke Auto Deteksi dan selesaikan insiden konflik."""
    _verify_csrf_header(request)
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    server.platform_override = "auto"
    _audit(
        db,
        user.username,
        "server_platform_reset",
        target=server.hostname,
        result="Platform disetel ulang ke Auto Deteksi",
    )

    for prob in (
        db.query(ServerProblem)
        .filter(
            ServerProblem.server_id == sid,
            ServerProblem.key == "platform_conflict",
            ServerProblem.resolved_at.is_(None),
        )
        .all()
    ):
        prob.resolved_at = datetime.utcnow()
        prob.resolved_note = _clean_str(f"auto ({user.username})", "auto (reset)", 100)

    db.commit()
    return {"ok": True, "message": "Konfigurasi platform berhasil disinkronkan kembali ke Auto Deteksi"}


# ---------------------------------------------------------------------------
# SERVER DETAILS (CANONICAL) & SERVICES ALIAS
# ---------------------------------------------------------------------------
@router.get("/servers/{sid}", response_class=HTMLResponse)
def services_page(request: Request, sid: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    services = db.query(Service).filter(Service.server_id == sid).all()
    recent_cutoff = datetime.utcnow() - timedelta(seconds=25)
    recent_completed_cmds = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.status == "success",
            Command.executed_at >= recent_cutoff,
        )
        .order_by(desc(Command.executed_at))
        .all()
    )
    recent_svc_cmds = {}
    for rc in recent_completed_cmds:
        if rc.service_id and rc.service_id not in recent_svc_cmds:
            recent_svc_cmds[rc.service_id] = rc

    now_utc = datetime.utcnow()
    since_24 = now_utc - timedelta(hours=24)
    svc_names = {s.service_name for s in services if s.service_name}
    prob_keys = [f"service_down:{name}" for name in svc_names]
    down_by_svc = {}
    if prob_keys:
        down_probs = (
            db.query(ServerProblem)
            .filter(
                ServerProblem.server_id == sid,
                ServerProblem.key.in_(prob_keys),
                (ServerProblem.resolved_at.is_(None)) | (ServerProblem.resolved_at >= since_24),
                ServerProblem.started_at <= now_utc,
            )
            .all()
        )
        for p in down_probs:
            s_name = p.key.split(":", 1)[1] if ":" in p.key else p.key
            p_start = max(since_24, p.started_at)
            p_end = p.resolved_at or now_utc
            if p_end > p_start:
                down_by_svc[s_name] = down_by_svc.get(s_name, 0.0) + (p_end - p_start).total_seconds()

    latest_map = _latest_metrics(db, (s.id for s in services))
    for svc in services:
        latest = latest_map.get(svc.id)
        svc._status = latest.status if latest else "unknown"
        recent_cmd = recent_svc_cmds.get(svc.id)
        if recent_cmd:
            if recent_cmd.action in ("stop", "service_stop"):
                svc._status = "down"
            elif recent_cmd.action in ("start", "service_start") and svc._status != "up":
                svc._status = "up"

        svc._pending_cmd = (
            db.query(Command)
            .filter(
                Command.service_id == svc.id,
                Command.status.in_(["pending", "executing"]),
            )
            .order_by(Command.created_at.desc())
            .first()
        )
        if svc._pending_cmd and svc._pending_cmd.action in ("stop", "service_stop"):
            svc._status = "down"
        elif svc._pending_cmd and svc._pending_cmd.action in ("start", "service_start") and svc._status != "up":
            svc._status = "up"

        if svc.ignored_reason and "DIMATIKAN OLEH OPERATOR" in svc.ignored_reason:
            svc._status = "down"

        svc._conns = latest.active_connections if latest and svc._status == "up" else 0
        svc._response_time = latest.response_time_ms if latest and svc._status == "up" else None
        svc._health_msg = latest.health_message if latest else None
        svc._last_check = latest.timestamp if latest else None

        down_sec = down_by_svc.get(svc.service_name, 0.0)
        if svc._status == "down" and down_sec <= 0:
            down_sec = 60.0
        total_sec = 86400.0
        pct = round(max(0.0, min(100.0, ((total_sec - down_sec) / total_sec) * 100.0)), 1)
        svc._uptime = {
            "uptime_pct": pct,
            "downtime_seconds": int(down_sec),
            "samples": 1 if down_sec == 0 else int(down_sec // 10) + 1,
        }
        _uptime_stats_cache[(svc.id, 24)] = (time.time(), svc._uptime)

    commands = (
        db.query(Command)
        .filter(Command.server_id == sid)
        .order_by(desc(Command.created_at))
        .limit(10)
        .all()
    )
    actions = _get_server_actions(db, sid, limit=50)
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    svc_data = [
        {
            "name": s.service_name,
            "status": getattr(s, "_status", "unknown"),
            "port": s.port,
            "proc": s.process_name,
            "is_core": bool(getattr(s, "is_core", 1)),
        }
        for s in services
    ]
    problem_level, open_problems, problem_history = sync_server_problems(
        db, server, _problem_instances(server, extra, svc_data, db)
    )
    _enrich_problems_for_ui(open_problems, services, extra, user)
    prob_by_key = {p["key"]: p for p in open_problems}
    for svc in services:
        svc._problem = prob_by_key.get(f"service_down:{svc.service_name}")
        svc._is_ignored = bool(getattr(svc, "is_ignored", 0)) or (
            bool(svc._problem and svc._problem.get("is_ignored"))
        )
        if getattr(svc, "_status", None) == "up" and getattr(svc, "ignore_mode", None) == "incident":
            svc._is_ignored = False
    top_p = {"cpu": [], "mem": []}
    if extra and extra.top_procs:
        try:
            top_p = json.loads(extra.top_procs)
        except Exception:
            pass

    cron_data = {"jobs": [], "timers": []}
    if extra and extra.cron_jobs:
        try:
            cron_data = json.loads(extra.cron_jobs)
        except Exception:
            pass

    fw_data = {"backend": "unknown", "status": "inactive", "rules": [], "blocked_ips": []}
    if extra and extra.firewall:
        try:
            fw_data = json.loads(extra.firewall)
        except Exception:
            pass

    ports_data = []
    if extra and extra.listening_ports:
        try:
            ports_data = json.loads(extra.listening_ports)
        except Exception:
            pass

    ssl_data = []
    if extra and extra.ssl_certs:
        try:
            ssl_data = json.loads(extra.ssl_certs)
        except Exception:
            pass

    sys_logs_data = []
    if extra and extra.system_logs:
        try:
            sys_logs_data = json.loads(extra.system_logs)
            if isinstance(sys_logs_data, list):
                sys_logs_data.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
        except Exception:
            pass

    accounts_data = []
    if extra and extra.accounts:
        try:
            accounts_data = json.loads(extra.accounts)
        except Exception:
            pass

    groups_data = []
    if extra and getattr(extra, "system_groups", None):
        try:
            groups_data = (
                json.loads(extra.system_groups)
                if isinstance(extra.system_groups, str)
                else extra.system_groups
            )
        except Exception:
            groups_data = []

    latest_sn = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(desc(SystemSnapshot.timestamp))
        .first()
    )
    hw_specs = _get_hardware_specs_dict(server, extra, latest_sn)
    platform_info = _classify_platform(hw_specs.get("platform", {}), getattr(server, "platform_override", None))

    installed_pkgs = []
    if extra and getattr(extra, "installed_packages", None):
        try:
            installed_pkgs = (
                json.loads(extra.installed_packages)
                if isinstance(extra.installed_packages, str)
                else extra.installed_packages
            )
        except Exception:
            installed_pkgs = []

    upgradable_pkgs = []
    if extra and getattr(extra, "apt_packages", None):
        try:
            upgradable_pkgs = (
                json.loads(extra.apt_packages)
                if isinstance(extra.apt_packages, str)
                else extra.apt_packages
            )
        except Exception:
            upgradable_pkgs = []

    effective_apt_upgradable = extra.apt_upgradable if extra else 0
    if isinstance(upgradable_pkgs, list):
        if len(upgradable_pkgs) == 0:
            effective_apt_upgradable = 0
        elif not effective_apt_upgradable or effective_apt_upgradable < len(upgradable_pkgs):
            effective_apt_upgradable = len(upgradable_pkgs)

    if not installed_pkgs and upgradable_pkgs:
        for u in upgradable_pkgs:
            u_name = u.get("name") if isinstance(u, dict) else str(u)
            u_ver = u.get("version", "") if isinstance(u, dict) else ""
            if u_name:
                installed_pkgs.append(
                    {
                        "name": u_name,
                        "version": u_ver or "-",
                        "arch": "",
                        "size_kb": 0,
                        "summary": "Pembaruan packages tersedia",
                        "is_user": True,
                        "status": "installed",
                    }
                )

    if extra and not extra.installed_packages:
        recent_pkg_req = (
            db.query(LogRequest)
            .filter(
                LogRequest.server_id == server.id,
                LogRequest.unit == "PKG_LIST",
                LogRequest.created_at > datetime.utcnow() - timedelta(minutes=5),
            )
            .first()
        )
        if not recent_pkg_req:
            try:
                db.add(LogRequest(server_id=server.id, unit="PKG_LIST", status="pending"))
                db.commit()
            except Exception:
                db.rollback()

    systemd_units_list = []
    if extra and getattr(extra, "systemd_units", None):
        try:
            systemd_units_list = (
                json.loads(extra.systemd_units)
                if isinstance(extra.systemd_units, str)
                else extra.systemd_units
            )
        except Exception:
            systemd_units_list = []

    op_stopped_units = {}
    for s in services:
        if s.ignored_reason and (
            "DIMATIKAN OLEH OPERATOR" in s.ignored_reason or "DIHENTIKAN OLEH OPERATOR" in s.ignored_reason
        ):
            op_by_u = (s.ignored_by or "OPERATOR").upper()
            if s.service_name:
                op_stopped_units[s.service_name.lower()] = op_by_u
            if s.process_name:
                op_stopped_units[s.process_name.lower()] = op_by_u
    try:
        recent_stop_cmds = (
            db.query(Command)
            .filter(
                Command.server_id == server.id,
                Command.action.in_(["stop", "start", "restart"]),
            )
            .order_by(desc(Command.id))
            .limit(30)
            .all()
        )
        seen_st = set()
        for c in recent_stop_cmds:
            u_name = None
            if c.params:
                try:
                    cp = json.loads(c.params) if isinstance(c.params, str) else c.params
                    u_name = cp.get("service_name") or cp.get("unit") or cp.get("process_name")
                except Exception:
                    pass
            if u_name:
                u_cl = (u_name[:-8] if u_name.endswith(".service") else u_name).lower()
                if u_cl not in seen_st:
                    seen_st.add(u_cl)
                    if c.action == "stop":
                        op_stopped_units[u_cl] = (c.issued_by or "OPERATOR").upper()
    except Exception:
        pass

    oom_count = 0
    oom_killed_units = set()
    ke_obj = None
    if extra and getattr(extra, "kernel_events", None):
        try:
            ke_obj = json.loads(extra.kernel_events) if isinstance(extra.kernel_events, str) else extra.kernel_events
            if isinstance(ke_obj, dict):
                oom_count = ke_obj.get("oom_kill_count") or 0
                now_ts = time.time()
                for ev in ke_obj.get("events") or []:
                    if isinstance(ev, dict) and ev.get("type") == "oom_kill":
                        ev_epoch = float(ev.get("epoch") or 0.0)
                        if ev_epoch > 0 and (now_ts - ev_epoch) > 1800:
                            continue
                        p = (ev.get("proc") or "").lower()
                        u = (ev.get("unit") or "").lower()
                        if p:
                            oom_killed_units.add(p)
                        if u:
                            oom_killed_units.add(u)
                            if u.endswith(".service"):
                                oom_killed_units.add(u[:-8])
        except Exception:
            pass

    for s in services:
        s_name_l = (s.service_name or "").lower()
        s_proc_l = (s.process_name or "").lower()
        s._is_oom_killed = bool(s_name_l in oom_killed_units or s_proc_l in oom_killed_units)

    if isinstance(systemd_units_list, list):
        for u in systemd_units_list:
            if isinstance(u, dict):
                if u.get("status") == "running":
                    continue
                u_name = (u.get("name") or "").lower()
                u_base = (u.get("name") or "").replace(".service", "").lower()
                if u_base in op_stopped_units:
                    u["stopped_by_operator"] = op_stopped_units[u_base]
                elif u_name in op_stopped_units:
                    u["stopped_by_operator"] = op_stopped_units[u_name]
                if u_base in oom_killed_units or u_name in oom_killed_units:
                    u["is_oom_killed"] = True

    if extra and not extra.systemd_units:
        recent_sysd_req = (
            db.query(LogRequest)
            .filter(
                LogRequest.server_id == server.id,
                LogRequest.unit == "SYSTEMD_LIST",
                LogRequest.created_at > datetime.utcnow() - timedelta(minutes=5),
            )
            .first()
        )
        if not recent_sysd_req:
            try:
                db.add(LogRequest(server_id=server.id, unit="SYSTEMD_LIST", status="pending"))
                db.commit()
            except Exception:
                db.rollback()

    available_logs_data = []
    if extra and getattr(extra, "available_logs", None):
        try:
            available_logs_data = json.loads(extra.available_logs)
        except Exception:
            available_logs_data = []

    # Fallback cerdas: HANYA berdasarkan service / unit nyata yang dilaporkan mesin klien ini!
    if not available_logs_data:
        detected_units = []
        if extra and extra.units:
            try:
                detected_units = [str(u).lower() for u in json.loads(extra.units)]
            except Exception:
                pass

        # Nginx HANYA jika nyata ada di units atau services server ini
        has_nginx = any("nginx" in u for u in detected_units) or any("nginx" in (s.service_name or "").lower() for s in services)
        if has_nginx:
            available_logs_data.append({"id": "NGINX_ACCESS", "group": "Web Server", "name": "Nginx Access Log", "desc": "/var/log/nginx/access.log"})
            available_logs_data.append({"id": "NGINX_ERROR", "group": "Web Server", "name": "Nginx Error Log", "desc": "/var/log/nginx/error.log"})

        # Apache HANYA jika nyata ada di units atau services server ini!
        has_apache = any(u in ("apache2", "httpd") for u in detected_units) or any((s.service_name or "").lower() in ("apache2", "httpd") for s in services)
        if has_apache:
            available_logs_data.append({"id": "APACHE_ACCESS", "group": "Web Server", "name": "Apache Access Log", "desc": "/var/log/apache2/access.log"})
            available_logs_data.append({"id": "APACHE_ERROR", "group": "Web Server", "name": "Apache Error Log", "desc": "/var/log/apache2/error.log"})

        # MySQL / MariaDB
        has_mysql = any(u in ("mariadb", "mysql", "mysqld") for u in detected_units) or any((s.service_name or "").lower() in ("mariadb", "mysql", "mysqld") for s in services)
        if has_mysql:
            available_logs_data.append({"id": "MARIADB_ERROR", "group": "Database", "name": "MySQL/MariaDB Error Log", "desc": "/var/log/mysql/error.log"})

        # Log Keamanan & Sistem bawaan Linux
        available_logs_data.append({"id": "SYSTEM_ERRORS", "group": "Keamanan & Sistem", "name": "Jurnal Galat Kritis Sistem", "desc": "journalctl -p 0..3"})
        available_logs_data.append({"id": "AUTH", "group": "Keamanan & Sistem", "name": "Log Autentikasi SSH & Sudo", "desc": "/var/log/auth.log"})
        available_logs_data.append({"id": "SYSLOG", "group": "Keamanan & Sistem", "name": "Syslog Sistem", "desc": "/var/log/syslog"})
        available_logs_data.append({"id": "DPKG", "group": "Keamanan & Sistem", "name": "Riwayat Paket (dpkg.log)", "desc": "/var/log/dpkg.log"})

    fim_paths = (
        db.query(FIMPath)
        .filter(FIMPath.server_id == sid)
        .order_by(FIMPath.category.desc(), FIMPath.path.asc())
        .all()
    )
    fim_events = (
        db.query(FIMEvent)
        .filter(FIMEvent.server_id == sid)
        .order_by(desc(FIMEvent.detected_at))
        .limit(50)
        .all()
    )

    return tpl(
        request,
        "services.html",
        {
            "user": user,
            "server": server,
            "services": services,
            "commands": commands,
            "actions": actions,
            "agent_version": extra.agent_version if extra else None,
            "is_agent_outdated": _is_agent_outdated(extra.agent_version if extra else None, settings.APP_VERSION),
            "os_label": extra.os_label if extra else None,
            "kernel": extra.kernel if extra else None,
            "apt_upgradable": effective_apt_upgradable,
            "apt_last_update": extra.apt_last_update.isoformat() if (extra and extra.apt_last_update) else None,
            "installed_packages": installed_pkgs,
            "upgradable_packages": upgradable_pkgs,
            "systemd_units": systemd_units_list,
            "is_online": not _server_stale(server),
            "problem_level": problem_level,
            "open_problems": open_problems,
            "problem_history": problem_history,
            "top_procs": top_p,
            "accounts": accounts_data,
            "system_groups": groups_data,
            "cron_jobs": cron_data,
            "firewall": fw_data,
            "listening_ports": ports_data,
            "ssl_certs": ssl_data,
            "fim_paths": fim_paths,
            "fim_events": fim_events,
            "system_logs": sys_logs_data,
            "kernel_events": ke_obj,
            "oom_kill_count": oom_count,
            "hardware_specs": hw_specs,
            "platform_info": platform_info,
            "available_logs": available_logs_data,
        },
    )


@router.get("/servers/{sid}/services", response_class=HTMLResponse)
def server_services_alias(request: Request, sid: int, db: Session = Depends(get_db)):
    """Alias backward compatibility untuk tautan lama /servers/{sid}/services."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    qs = request.url.query
    if not qs:
        target = f"/servers/{sid}?tab=layanan"
    elif "tab=" not in qs:
        target = f"/servers/{sid}?tab=layanan&{qs}"
    else:
        target = f"/servers/{sid}?{qs}"
    return RedirectResponse(target, status_code=303)


# ---------------------------------------------------------------------------
# USER ACTIVITY
# ---------------------------------------------------------------------------
IGNORED_SHELL_BASE_COMMANDS = {
    "cd",
    "ls",
    "ll",
    "la",
    "l",
    "dir",
    "vdir",
    "pwd",
    "clear",
    "cls",
    "reset",
    "exit",
    "xit",
    "logout",
    "history",
    "true",
    "false",
}


def is_ignorable_shell_cmd(cmd: str) -> bool:
    if not cmd:
        return True
    s = cmd.strip()
    if not s:
        return True
    if ">" in s:
        return False
    sub_cmds = re.split(r"&&|\|\||[;|]", s)
    for sub in sub_cmds:
        sub = sub.strip()
        if not sub:
            continue
        tokens = sub.split()
        idx = 0
        while idx < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*", tokens[idx]):
            idx += 1
        if idx >= len(tokens):
            continue
        token = tokens[idx].strip().lstrip("\\")
        base = os.path.basename(token)
        if base not in IGNORED_SHELL_BASE_COMMANDS:
            return False
    return True


def _deduplicate_user_logins(raw_list: list) -> list:
    if not isinstance(raw_list, list):
        return []
    result = []
    seen_active_tty = set()
    seen_sudo = set()
    seen_shell = set()
    seen_login = set()
    seen_selesai = set()
    seen_other = set()

    for item in raw_list:
        if not isinstance(item, dict):
            continue
        ev_type = item.get("type")
        tty = str(item.get("tty") or "").strip()
        ts = str(item.get("ts") or "").strip()
        method = str(item.get("method") or "").strip()
        user = str(item.get("user") or "").strip()
        src = str(item.get("from") or "").strip()

        if ev_type == "aktif":
            if tty and tty in seen_active_tty:
                for existing in result:
                    if existing.get("type") == "aktif" and str(existing.get("tty") or "").strip() == tty:
                        if not existing.get("pid") and item.get("pid"):
                            existing["pid"] = item["pid"]
                        if item.get("active_cmd"):
                            existing["active_cmd"] = item["active_cmd"]
                        if item.get("login_time"):
                            existing["login_time"] = item["login_time"]
                        break
                continue
            if tty:
                seen_active_tty.add(tty)
            result.append(item)
        elif ev_type in ("login", "sukses"):
            if tty and tty != "—":
                login_key = (user, ts[:19], tty)
                if login_key in seen_login:
                    continue
                seen_login.add(login_key)
                item["type"] = "login"
                result.append(item)
            else:
                matched = False
                for existing in result:
                    if (
                        existing.get("type") in ("login", "sukses")
                        and str(existing.get("user") or "") == user
                        and str(existing.get("ts") or "")[:16] == ts[:16]
                    ):
                        if (not existing.get("from") or existing.get("from") == "(lokal)") and src and src != "(lokal)":
                            existing["from"] = src
                        if "ssh (" in method and "ssh (" not in str(existing.get("method") or ""):
                            existing["method"] = method
                        matched = True
                        break
                if not matched:
                    login_key = (user, ts[:19], "(auth)")
                    if login_key not in seen_login:
                        seen_login.add(login_key)
                        item["type"] = "login"
                        result.append(item)
        elif ev_type == "selesai":
            selesai_key = (user, ts[:19], tty)
            if selesai_key in seen_selesai:
                continue
            seen_selesai.add(selesai_key)
            result.append(item)
        elif ev_type in ("sudo", "sudo_gagal", "polkit", "polkit_gagal"):
            sudo_key = (ts, tty, method, str(item.get("alert") or ""), str(item.get("type") or ""))
            if sudo_key in seen_sudo:
                for existing in result:
                    if (existing.get("type") in ("sudo", "sudo_gagal", "polkit", "polkit_gagal")) and (
                        str(existing.get("ts") or "").strip(),
                        str(existing.get("tty") or "").strip(),
                        str(existing.get("method") or "").strip(),
                    ) == sudo_key:
                        if not existing.get("pwd") and item.get("pwd"):
                            existing["pwd"] = item["pwd"]
                            existing["target_user"] = item.get("target_user", existing.get("target_user"))
                            existing["alert"] = item.get("alert", existing.get("alert"))
                        break
                continue
            seen_sudo.add(sudo_key)
            result.append(item)
        elif ev_type == "shell":
            if is_ignorable_shell_cmd(method):
                continue
            sh_key = (ts, method, item.get("alert", ""))
            if sh_key in seen_shell:
                continue
            seen_shell.add(sh_key)
            result.append(item)
        else:
            other_key = (ev_type, ts, tty, src, method)
            if other_key in seen_other:
                continue
            seen_other.add(other_key)
            result.append(item)

    max_ts = max(
        (str(r.get("ts", "")) for r in result if r.get("type") != "aktif" and len(str(r.get("ts", ""))) >= 19),
        default="",
    )
    for r in result:
        if r.get("type") == "aktif":
            login_t = str(r.get("login_time", ""))
            cur_ts = str(r.get("ts", ""))
            if login_t and cur_ts < login_t:
                r["ts"] = login_t
            if max_ts and str(r.get("ts", "")) < max_ts:
                r["ts"] = max_ts

    def _sort_key(e):
        t = str(e.get("ts", ""))
        typ = e.get("type", "")
        prio = 4 if typ == "aktif" else (3 if typ == "selesai" else (1 if typ in ("login", "sukses") else 2))
        return (t, prio)

    result.sort(key=_sort_key, reverse=True)
    return result


@router.get("/servers/{sid}/user/{username}", response_class=HTMLResponse)
def user_activity_page(request: Request, sid: int, username: str, db: Session = Depends(get_db)):
    """Detail aktivitas seorang user: info akun, aktivitas login, riwayat perintah."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    if not VALID_UNIT_RE.match(username) or len(username) > 64:
        return RedirectResponse(f"/servers/{sid}?tab=akun", status_code=303)
    account = None
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if extra and extra.accounts:
        try:
            accounts = json.loads(extra.accounts)
        except (TypeError, ValueError):
            accounts = []
        for a in accounts if isinstance(accounts, list) else []:
            if a.get("user") == username:
                account = a
                break

    last_log = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == sid,
            LogRequest.unit == "USER_ACTIVITY",
            LogRequest.detail == username,
            LogRequest.status == "success",
        )
        .order_by(LogRequest.id.desc())
        .first()
    )
    initial_logins = []
    if last_log and last_log.result:
        try:
            parsed = json.loads(last_log.result)
            raw_logins = parsed.get("logins", []) if isinstance(parsed, dict) else []
            initial_logins = _deduplicate_user_logins(raw_logins)
        except Exception:
            initial_logins = []

    return tpl(
        request,
        "user_activity.html",
        {
            "user": user,
            "server": server,
            "username": username,
            "account": account,
            "initial_logins": initial_logins,
        },
    )


@router.get("/servers/{sid}/metrics", response_class=HTMLResponse)
def metrics_page(request: Request, sid: int, db: Session = Depends(get_db)):
    """Alihkan ke tab Services di halaman rincian server."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    return RedirectResponse(f"/servers/{sid}?tab=layanan", status_code=303)


# ---------------------------------------------------------------------------
# API SERVERS & OVERVIEW
# ---------------------------------------------------------------------------
@router.post("/api/servers")
def api_server_add(
    payload: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Pendaftaran server baru via API JSON."""
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kelola server diperlukan")
    hostname = _clean_str(payload.get("hostname", ""), "", 255).strip()
    ip_address = _clean_str(payload.get("ip_address", ""), "", 45).strip()
    group_name = _clean_str(payload.get("group_name", ""), "", 64).strip() or None
    if not hostname or not ip_address:
        raise HTTPException(status_code=400, detail="Hostname dan IP Address wajib diisi")

    raw = secrets.token_hex(32)
    srv = Server(
        hostname=hostname,
        ip_address=ip_address,
        group_name=group_name,
        api_key=hash_api_key(raw),
    )
    db.add(srv)
    _audit(
        db,
        user.username,
        "server_add",
        f"{hostname} ({ip_address})" + (f" [Grup: {group_name}]" if group_name else ""),
        "berhasil",
    )
    db.commit()
    db.refresh(srv)
    return {"ok": True, "server": {"id": srv.id, "hostname": srv.hostname, "ip_address": srv.ip_address, "api_key": raw}}


@router.delete("/api/servers/{sid}")
def api_server_delete(
    sid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Penghapusan server via API JSON."""
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kelola server diperlukan")
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    target_info = f"{server.hostname} ({server.ip_address}) id={server.id}"
    _audit(
        db,
        user.username,
        "server_delete",
        target_info,
        "berhasil",
    )
    db.delete(server)
    db.commit()
    return {"ok": True, "message": f"Server {server.hostname} berhasil dihapus"}


@router.get("/api/servers")
def api_servers(user: User = Depends(require_user), db: Session = Depends(get_db)):
    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    extras_map = {ex.server_id: ex for ex in db.query(ServerExtras).all()}
    result = []
    for srv in servers:
        services = db.query(Service).filter(Service.server_id == srv.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        svc_list = []
        for svc in services:
            latest = latest_map.get(svc.id)
            svc_list.append(
                {
                    "id": svc.id,
                    "name": svc.service_name,
                    "port": svc.port,
                    "process": svc.process_name,
                    "is_core": bool(getattr(svc, "is_core", 1)),
                    "status": latest.status if latest else "unknown",
                    "connections": latest.active_connections if latest else 0,
                    "response_time_ms": latest.response_time_ms if latest else None,
                    "health_message": latest.health_message if latest else None,
                    "last_check": latest.timestamp.isoformat() if latest else None,
                }
            )
        ex = extras_map.get(srv.id)
        prob_level, open_prob, _ = sync_server_problems(
            db,
            srv,
            _problem_instances(
                srv,
                ex,
                [
                    {
                        "name": s["name"],
                        "status": s["status"],
                        "port": s["port"],
                        "is_core": s.get("is_core", True),
                    }
                    for s in svc_list
                ],
                db,
            ),
        )
        ignored_keys = {p.get("key") for p in open_prob if p.get("is_ignored")}
        svc_ignored_db = {s.service_name for s in services if getattr(s, "is_ignored", 0)}
        for s in svc_list:
            if (f"service_down:{s['name']}" in ignored_keys) or (s["name"] in svc_ignored_db):
                s["ignored"] = True

        stale = _server_stale(srv)
        active_svcs = [s for s in svc_list if not s.get("ignored")]
        is_ignored_stale = any(p.get("key") == "agent_stale" and p.get("is_ignored") for p in open_prob)
        if srv.is_maintenance:
            overall = "maintenance"
        elif stale:
            overall = "offline"
        elif not active_svcs:
            overall = "up"
        else:
            overall = "down" if not any(s["status"] == "up" for s in active_svcs) else "up"
        if stale:
            for s in svc_list:
                s["status"] = "offline"
            if not srv.is_maintenance:
                overall = "offline"

        latest_sys = (
            db.query(SystemSnapshot)
            .filter(SystemSnapshot.server_id == srv.id)
            .order_by(desc(SystemSnapshot.timestamp))
            .first()
        )
        cpu_pct = round(latest_sys.cpu, 1) if latest_sys else None
        mem_pct = (
            round(latest_sys.mem_used / latest_sys.mem_total * 100, 1)
            if latest_sys and latest_sys.mem_total
            else None
        )
        uptime_secs = latest_sys.uptime_secs if latest_sys else None
        down_svc_count = sum(1 for s in svc_list if s["status"] in ("down", "offline") and not s.get("ignored"))
        ignored_svc_count = sum(1 for s in svc_list if s["status"] in ("down", "offline") and s.get("ignored"))
        active_p = [p for p in open_prob if not p.get("is_ignored")]
        danger_p = [p for p in active_p if p.get("severity") == "danger"]
        average_p = [p for p in active_p if p.get("severity") == "average"]
        warning_p = [p for p in active_p if p.get("severity") == "warning"]
        info_p = [p for p in active_p if p.get("severity") == "info"]
        ignored_p = [p for p in open_prob if p.get("is_ignored")]

        danger_count = len(danger_p)
        average_count = len(average_p)
        warning_count = len(warning_p)
        info_count = len(info_p)
        active_prob_count = len(active_p)
        ignored_prob_count = len(ignored_p)
        danger_msgs = " • ".join(p.get("message", "") for p in danger_p)
        average_msgs = " • ".join(p.get("message", "") for p in average_p)
        warning_msgs = " • ".join(p.get("message", "") for p in warning_p)
        info_msgs = " • ".join(p.get("message", "") for p in info_p)
        ignored_msgs = " • ".join(_format_ignored_prob_msg(p) for p in ignored_p)

        hw = _get_hardware_specs_dict(srv, ex, latest_sys)
        cpu_cores = hw.get("cpu", {}).get("cores") or hw.get("cpu", {}).get("logical_cores")
        cpu_cores_str = f"{cpu_cores} Core" if (srv.last_seen and cpu_cores) else "—"
        cpu_model_clean = _clean_cpu_model(hw.get("cpu", {}).get("model"))
        d_tot, d_avail, d_pct = _extract_disk_stats(latest_sys.disks if latest_sys else None)
        disks_str = _extract_disks_summary(hw.get("disks"))
        hw_model = _extract_hw_model(hw.get("platform"))
        prim_iface = _extract_primary_interface(hw.get("network"))
        os_name = hw.get("os", {}).get("os_name") or (ex.os_label if ex else "Linux")
        kernel = hw.get("os", {}).get("kernel") or (ex.kernel if ex else "—")
        arch = hw.get("cpu", {}).get("arch") or (ex.arch if ex else "x86_64")
        boot_time = hw.get("os", {}).get("boot_time") or "—"
        mem = hw.get("memory", {})
        ram_b = mem.get("ram_total") or (latest_sys.mem_total if latest_sys else 0)
        swap_b = mem.get("swap_total") or (latest_sys.swap_total if latest_sys else 0)
        m_tot = _format_bytes_gb(ram_b if ram_b else (latest_sys.mem_total if latest_sys else None))
        s_tot = _format_bytes_gb(swap_b if swap_b else (latest_sys.swap_total if latest_sys else None))
        m_avail = _format_bytes_gb(latest_sys.mem_avail if latest_sys else None)
        m_used = _format_bytes_gb(latest_sys.mem_used if latest_sys else None)
        up_str = _format_uptime_str(latest_sys.uptime_secs if latest_sys else None)

        formatted_probs = []
        for p in open_prob:
            p_dict = dict(p)
            p_dict["server_id"] = srv.id
            p_dict["hostname"] = srv.hostname
            p_dict["group_name"] = srv.group_name or ""
            formatted_probs.append(p_dict)

        result.append(
            {
                "id": srv.id,
                "hostname": srv.hostname,
                "ip_address": srv.ip_address,
                "group_name": srv.group_name or "",
                "tier": getattr(srv, "tier", 2),
                "is_active": srv.is_active,
                "is_maintenance": bool(srv.is_maintenance),
                "is_proxmox_ha": bool(srv.is_proxmox_ha),
                "platform_override": getattr(srv, "platform_override", None),
                "is_isolated_net": bool(getattr(srv, "is_isolated_net", 0)),
                "allow_web_terminal": bool(getattr(srv, "allow_web_terminal", 0)),
                "platform": _classify_platform(hw.get("platform", {}), getattr(srv, "platform_override", None)),
                "online": overall not in ("offline", "offline (diabaikan)"),
                "is_ignored_stale": is_ignored_stale,
                "last_seen": srv.last_seen.isoformat() if srv.last_seen else None,
                "overall_status": overall,
                "services": svc_list,
                "problems": _serialize_problem_list(formatted_probs),
                "apt_upgradable": ex.apt_upgradable if ex else None,
                "apt_last_update": ex.apt_last_update.isoformat() if ex and ex.apt_last_update else None,
                "kernel": kernel,
                "os_label": ex.os_label if ex else None,
                "os_name": os_name,
                "arch": arch,
                "cpu": cpu_pct,
                "cpu_cores": cpu_cores_str,
                "cpu_cores_num": cpu_cores or 0,
                "cpu_model": cpu_model_clean,
                "ram_total_str": m_tot,
                "swap_total_str": s_tot,
                "disk_str": disks_str,
                "hw_model": hw_model,
                "prim_iface": prim_iface,
                "boot_time": boot_time,
                "notes": srv.notes or "",
                "tags": srv.tags or "",
                "agent_version": ex.agent_version if ex else "",
                "agent_outdated": _is_agent_outdated(ex.agent_version, settings.APP_VERSION) if ex else False,
                "mem_pct": mem_pct,
                "mem_total_str": m_tot,
                "mem_avail_str": m_avail,
                "mem_used_str": m_used,
                "disk_total_str": d_tot,
                "disk_avail_str": d_avail,
                "disk_pct": d_pct,
                "uptime_secs": uptime_secs,
                "uptime_str": up_str,
                "down_svc_count": down_svc_count,
                "ignored_svc_count": ignored_svc_count,
                "problem_level": prob_level,
                "active_problem_count": active_prob_count,
                "ignored_problem_count": ignored_prob_count,
                "danger_count": danger_count,
                "average_count": average_count,
                "warning_count": warning_count,
                "info_count": info_count,
                "danger_msgs": danger_msgs,
                "average_msgs": average_msgs,
                "warning_msgs": warning_msgs,
                "info_msgs": info_msgs,
                "ignored_msgs": ignored_msgs,
            }
        )
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return result


@router.get("/api/servers/{sid}/overview")
def api_server_overview(sid: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Ringkasan live (services + perintah terbaru) untuk polling UI halaman Services."""
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    services = db.query(Service).filter(Service.server_id == sid).order_by(Service.port).all()
    pending_cmds = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.status.in_(["pending", "executing"]),
        )
        .all()
    )
    pending_ids = {c.service_id for c in pending_cmds if c.service_id}
    pending_actions = {c.service_id: c.action for c in pending_cmds if c.service_id}

    recent_cutoff = datetime.utcnow() - timedelta(seconds=25)
    recent_completed_cmds = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.status == "success",
            Command.executed_at >= recent_cutoff,
        )
        .order_by(desc(Command.executed_at))
        .all()
    )
    recent_svc_cmds = {}
    for rc in recent_completed_cmds:
        if rc.service_id and rc.service_id not in recent_svc_cmds:
            recent_svc_cmds[rc.service_id] = rc

    latest_map = _latest_metrics(db, (s.id for s in services))
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    oom_count = 0
    oom_killed_units = set()
    if extras and getattr(extras, "kernel_events", None):
        try:
            ke_obj = (
                json.loads(extras.kernel_events)
                if isinstance(extras.kernel_events, str)
                else extras.kernel_events
            )
            if isinstance(ke_obj, dict):
                oom_count = ke_obj.get("oom_kill_count") or 0
                now_ts = time.time()
                for ev in ke_obj.get("events") or []:
                    if isinstance(ev, dict) and ev.get("type") == "oom_kill":
                        ev_epoch = float(ev.get("epoch") or 0.0)
                        if ev_epoch > 0 and (now_ts - ev_epoch) > 1800:
                            continue
                        p = (ev.get("proc") or "").lower()
                        u = (ev.get("unit") or "").lower()
                        if p:
                            oom_killed_units.add(p)
                        if u:
                            oom_killed_units.add(u)
                            if u.endswith(".service"):
                                oom_killed_units.add(u[:-8])
        except Exception:
            pass

    resolved_status_map = {}
    for svc in services:
        latest = latest_map.get(svc.id)
        st = latest.status if latest else "unknown"

        p_act = pending_actions.get(svc.id)
        if p_act in ("stop", "service_stop"):
            st = "down"
        elif p_act in ("start", "service_start") and st != "up":
            st = "up"

        recent_cmd = recent_svc_cmds.get(svc.id)
        if recent_cmd:
            if recent_cmd.action in ("stop", "service_stop"):
                st = "down"
            elif recent_cmd.action in ("start", "service_start", "restart", "service_restart") and st != "up":
                st = "up"

        if svc.ignored_reason and "DIMATIKAN OLEH OPERATOR" in svc.ignored_reason:
            st = "down"

        resolved_status_map[svc.id] = st

    svc_data = [
        {
            "name": s.service_name,
            "status": resolved_status_map.get(s.id, "unknown"),
            "port": s.port,
            "proc": s.process_name,
            "is_core": bool(getattr(s, "is_core", 1)),
        }
        for s in services
    ]
    problem_level, open_problems, problem_history = sync_server_problems(
        db, server, _problem_instances(server, extras, svc_data, db)
    )
    _enrich_problems_for_ui(open_problems, services, extras, user)
    open_prob_serialized = _serialize_problem_list(open_problems)
    hist_prob_serialized = _serialize_problem_list(problem_history)
    prob_by_key = {p["key"]: p for p in open_problems}

    svc_list = []
    for svc in services:
        latest = latest_map.get(svc.id)
        st = resolved_status_map.get(svc.id, "unknown")
        p_row = prob_by_key.get(f"service_down:{svc.service_name}")
        is_ign = bool(getattr(svc, "is_ignored", 0)) or (bool(p_row and p_row.get("is_ignored")))
        if st == "up" and getattr(svc, "ignore_mode", None) == "incident":
            is_ign = False
        p_id = p_row.get("id") if p_row else None
        p_msg = p_row.get("message") if p_row else None
        ign_until = None
        if getattr(svc, "ignored_until", None):
            ign_until = svc.ignored_until.isoformat()
        elif p_row and p_row.get("ignored_until"):
            ign_until = p_row.get("ignored_until")
            if isinstance(ign_until, datetime):
                ign_until = ign_until.isoformat()

        s_name_l = (svc.service_name or "").lower()
        s_proc_l = (svc.process_name or "").lower()
        is_oom_k = bool(s_name_l in oom_killed_units or s_proc_l in oom_killed_units)

        svc_list.append(
            {
                "id": svc.id,
                "name": svc.service_name,
                "port": svc.port,
                "status": st,
                "is_core": bool(getattr(svc, "is_core", 1)),
                "is_oom_killed": is_oom_k,
                "ignored": is_ign,
                "ignored_until": ign_until,
                "ignore_mode": getattr(svc, "ignore_mode", None) or (p_row.get("ignore_mode") if p_row else None),
                "problem_id": p_id,
                "problem_msg": p_msg,
                "connections": latest.active_connections if latest else 0,
                "response_time_ms": latest.response_time_ms if latest else None,
                "health_message": latest.health_message if latest else None,
                "pending": svc.id in pending_ids,
                "pending_action": pending_actions.get(svc.id),
            }
        )

    if _server_stale(server):
        for s in svc_list:
            s["status"] = "offline"

    commands = (
        db.query(Command)
        .filter(Command.server_id == sid)
        .order_by(desc(Command.created_at))
        .limit(10)
        .all()
    )
    cmd_list = [
        {
            "id": c.id,
            "service_id": c.service_id,
            "action": c.action,
            "status": c.status,
            "result": c.result,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in commands
    ]

    actions_raw = _get_server_actions(db, sid, limit=50)
    actions_list = [
        {
            "id": a["id"],
            "time": _fmt_dt(a["time"], with_sec=True) if a["time"] else "",
            "user": a["user"],
            "action": a["action"],
            "action_label": a["action_label"],
            "target": a["target"],
            "status": a["status"],
            "status_cls": a["status_cls"],
            "status_label": a["status_label"],
            "result": a["result"],
        }
        for a in actions_raw
    ]
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()

    stale_apt_runs = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == sid,
            LogRequest.unit.in_(APT_UNITS),
            LogRequest.status.in_(["pending", "executing"]),
        )
        .all()
    )
    for stale_req in stale_apt_runs:
        apt_limit = timedelta(minutes=15) if "UPGRADE" in (stale_req.unit or "") else timedelta(minutes=5)
        ref_time = stale_req.updated_at or stale_req.created_at
        if ref_time and ref_time < (datetime.utcnow() - apt_limit):
            stale_req.status = "failed"
            stale_req.result = (stale_req.result or "").strip() + "\n[proses apt kedaluwarsa]"
            db.commit()

    apt_run = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == sid,
            LogRequest.unit.in_(APT_UNITS),
            LogRequest.status.in_(["pending", "executing"]),
        )
        .order_by(LogRequest.id.desc())
        .first()
    )
    shell_run = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == sid,
            LogRequest.unit == SHELL_UNIT,
            LogRequest.status.in_(["pending", "executing"]),
        )
        .order_by(LogRequest.created_at.desc())
        .first()
    )
    if shell_run:
        stale_limit = datetime.utcnow() - timedelta(seconds=25)
        if (shell_run.updated_at and shell_run.updated_at < stale_limit) or (
            shell_run.created_at < stale_limit and shell_run.status == "pending"
        ):
            shell_run.status = "failed"
            shell_run.result = (shell_run.result or "").strip() + "\n[sesi shell kedaluwarsa]"
            db.commit()
            shell_run = None

    latest_snap = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(desc(SystemSnapshot.timestamp))
        .first()
    )

    def _safe_json_loads(val, default):
        if not val:
            return default
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(val)
        except Exception:
            return default

    hw_specs = _get_hardware_specs_dict(server, extras, latest_snap) if extras else {}

    return {
        "server": {
            "id": server.id,
            "hostname": server.hostname,
            "ip_address": server.ip_address,
            "platform": _classify_platform(hw_specs.get("platform", {}), getattr(server, "platform_override", None)),
            "tier": getattr(server, "tier", 2),
            "is_active": bool(server.is_active),
            "status": "stale" if _server_stale(server) else "up",
            "is_maintenance": bool(server.is_maintenance),
            "os_label": extras.os_label if extras else "Linux",
            "uptime_str": _format_uptime_str(latest_snap.uptime_secs if latest_snap else None),
            "agent_version": extras.agent_version if extras else None,
            "agent_outdated": _is_agent_outdated(extras.agent_version if extras else None, settings.APP_VERSION),
        },
        "cpu": latest_snap.cpu if latest_snap else 0.0,
        "load1": latest_snap.load1 if latest_snap else 0.0,
        "load5": latest_snap.load5 if latest_snap else 0.0,
        "load15": latest_snap.load15 if latest_snap else 0.0,
        "mem_total": latest_snap.mem_total if latest_snap else 0,
        "mem_used": latest_snap.mem_used if latest_snap else 0,
        "mem_avail": latest_snap.mem_avail if latest_snap else 0,
        "swap_total": latest_snap.swap_total if latest_snap else 0,
        "swap_used": latest_snap.swap_used if latest_snap else 0,
        "disks": _safe_json_loads(latest_snap.disks, []) if latest_snap else [],
        "net": _safe_json_loads(latest_snap.net, []) if latest_snap else [],
        "top_procs": _safe_json_loads(extras.top_procs if extras else None, {}),
        "hardware_specs": hw_specs,
        "listening_ports": _safe_json_loads(extras.listening_ports if extras else None, []),
        "firewall": _safe_json_loads(extras.firewall if extras else None, {}),
        "accounts": _safe_json_loads(extras.accounts if extras else None, []),
        "cron_jobs": _safe_json_loads(extras.cron_jobs if extras else None, []),
        "ssl_certs": _safe_json_loads(extras.ssl_certs if extras else None, []),
        "installed_packages": _safe_json_loads(extras.installed_packages if extras else None, []),
        "systemd_units": _safe_json_loads(extras.systemd_units if extras else None, []),
        "services": svc_list,
        "commands": cmd_list,
        "actions": actions_list,
        "online": not _server_stale(server),
        "tier": getattr(server, "tier", 2),
        "last_seen": server.last_seen.isoformat() if server.last_seen else None,
        "last_seen_ago_ms": (
            int(
                (
                    datetime.now(timezone.utc)
                    - (server.last_seen.replace(tzinfo=timezone.utc) if server.last_seen.tzinfo is None else server.last_seen)
                ).total_seconds()
                * 1000
            )
            if server.last_seen
            else None
        ),
        "apt_upgradable": extras.apt_upgradable if extras else None,
        "apt_last_update": extras.apt_last_update.isoformat() if extras and extras.apt_last_update else None,
        "agent_version": extras.agent_version if extras else None,
        "agent_outdated": _is_agent_outdated(extras.agent_version if extras else None, settings.APP_VERSION),
        "apt_exec": {
            "id": apt_run.id,
            "kind": apt_run.unit,
            "detail": apt_run.detail,
            "started_ms": int(apt_run.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if apt_run.created_at
            else None,
        }
        if apt_run
        else None,
        "is_maintenance": bool(server.is_maintenance),
        "is_proxmox_ha": bool(server.is_proxmox_ha),
        "platform_override": getattr(server, "platform_override", None),
        "is_isolated_net": bool(getattr(server, "is_isolated_net", 0)),
        "allow_web_terminal": bool(getattr(server, "allow_web_terminal", 0)),
        "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
        "maintenance_reason": server.maintenance_reason,
        "shell_exec": {
            "id": shell_run.id,
            "started_ms": int(shell_run.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if shell_run.created_at
            else None,
        }
        if shell_run
        else None,
        "problem_level": problem_level,
        "open_problems": open_prob_serialized,
        "problem_history": hist_prob_serialized,
        "oom_kill_count": oom_count,
        "notes": server.notes or "",
    }


@router.get("/api/servers/{sid}/top-procs")
def api_server_top_procs(sid: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    procs = {"cpu": [], "mem": []}
    if extra and extra.top_procs:
        try:
            procs = json.loads(extra.top_procs)
        except Exception:
            pass
    return {
        "ok": True,
        "updated_at": extra.updated_at.isoformat() if extra and extra.updated_at else None,
        "top_procs": procs,
    }


@router.post("/api/servers/{sid}/maintenance")
async def api_server_maintenance(
    sid: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_manage_servers"):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Hanya admin atau operator berizin yang dapat mengatur mode pemeliharaan",
        )
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    try:
        body = await request.json()
    except Exception:
        body = {}

    action = body.get("action", "enable")
    try:
        duration = int(body.get("duration_minutes", 60) or 0)
    except (ValueError, TypeError):
        duration = 60
    reason = str(body.get("reason", "") or "").strip()[:255]

    if action == "enable":
        server.is_maintenance = 1
        server.maintenance_reason = reason or "Pemeliharaan terencana"
        if duration > 0:
            server.maintenance_until = datetime.utcnow() + timedelta(minutes=duration)
        else:
            server.maintenance_until = None
        detail_msg = f"Mode pemeliharaan diaktifkan ({duration}m, alasan: {server.maintenance_reason})"
    else:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
        detail_msg = "Mode pemeliharaan dinonaktifkan"

    _audit(
        db,
        user.username,
        "maintenance_mode",
        target=server.hostname,
        result=detail_msg,
        server_id=server.id,
    )
    db.commit()
    return {
        "ok": True,
        "is_maintenance": bool(server.is_maintenance),
        "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
        "maintenance_reason": server.maintenance_reason,
        "message": detail_msg,
    }


@router.post("/api/servers/{sid}/notes")
async def api_server_notes(
    sid: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Hanya admin atau operator berizin yang dapat mengedit catatan server",
        )
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw_notes = body.get("notes")
    if raw_notes is not None:
        notes_str = str(raw_notes).strip()
        server.notes = notes_str if notes_str else None
    else:
        server.notes = None
    _audit(db, user.username, "server_notes_update", f"id={server.id} {server.hostname}", "berhasil")
    db.commit()
    return {"ok": True, "notes": server.notes or ""}


# ---------------------------------------------------------------------------
# PERFORMANCE & SYSTEM TELEMETRY
# ---------------------------------------------------------------------------
@router.get("/api/servers/{sid}/perf")
def api_server_perf(
    sid: int,
    range: str = "24h",  # pylint: disable=redefined-builtin
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Riwayat kinerja sistem utk grafik: gabungan rollup per jam + snapshot mentalah."""
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    now = datetime.utcnow()
    if range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        span = max(now - start, timedelta(minutes=5))
    else:
        span = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }.get(range)
        if not span:
            raise HTTPException(status_code=400, detail="Rentang tidak dikenal")
        start = now - span

    points: list[dict] = []

    if span <= timedelta(hours=24):
        raw_from = start
    else:
        cutoff_raw = now - timedelta(hours=24)
        hour_rows = (
            db.query(SysSnapshotHour)
            .filter(
                SysSnapshotHour.server_id == sid,
                SysSnapshotHour.bucket >= start,
                SysSnapshotHour.bucket < cutoff_raw,
            )
            .order_by(SysSnapshotHour.bucket)
            .all()
        )
        points = [
            {
                "t": int(h.bucket.timestamp()),
                "cpu": round(h.cpu_avg, 1),
                "load": round(h.load1_avg, 2) if h.load1_avg is not None else None,
                "load1": round(h.load1_avg, 2) if h.load1_avg is not None else None,
                "load5": round(h.load5_avg, 2) if h.load5_avg is not None else None,
                "load15": round(h.load15_avg, 2) if h.load15_avg is not None else None,
                "mem_used": h.mem_used_avg,
                "mem_total": h.mem_total,
                "swap_used": h.swap_used_avg,
                "swap_total": h.swap_total,
                "disk": round(h.disk_max_pct, 1) if h.disk_max_pct is not None else None,
            }
            for h in hour_rows
        ]
        raw_from = cutoff_raw

    step_secs = max(int(span.total_seconds() / 120), 30)
    raw = (
        db.query(
            (func.floor(func.unix_timestamp(SystemSnapshot.timestamp) / step_secs) * step_secs).label("tb"),
            func.avg(SystemSnapshot.cpu),
            func.avg(SystemSnapshot.load1),
            func.avg(SystemSnapshot.load5),
            func.avg(SystemSnapshot.load15),
            func.max(SystemSnapshot.mem_total),
            func.avg(SystemSnapshot.mem_used),
            func.max(SystemSnapshot.swap_total),
            func.avg(SystemSnapshot.swap_used),
            func.max(SystemSnapshot.disks),
            func.max(SystemSnapshot.net),
        )
        .filter(
            SystemSnapshot.server_id == sid,
            SystemSnapshot.timestamp >= raw_from,
            SystemSnapshot.timestamp <= now,
        )
        .group_by("tb")
        .order_by("tb")
        .all()
    )

    def _parse_json_list(raw_json):
        if not raw_json:
            return []
        try:
            val = json.loads(raw_json)
            return val if isinstance(val, list) else []
        except Exception:
            return []

    points.extend(
        [
            {
                "t": int(tb_stamp),
                "cpu": round(cpu_avg, 1) if cpu_avg is not None else None,
                "load": round(load1_avg, 2) if load1_avg is not None else None,
                "load1": round(load1_avg, 2) if load1_avg is not None else None,
                "load5": round(load5_avg, 2) if load5_avg is not None else None,
                "load15": round(load15_avg, 2) if load15_avg is not None else None,
                "mem_used": mem_used,
                "mem_total": mem_total,
                "swap_used": swap_used,
                "swap_total": swap_total,
                "disks": _parse_json_list(disks_raw),
                "net": _parse_json_list(net_raw),
            }
            for tb_stamp, cpu_avg, load1_avg, load5_avg, load15_avg, mem_total, mem_used, swap_total, swap_used, disks_raw, net_raw in raw
        ]
    )

    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    latest_sys = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(SystemSnapshot.timestamp.desc())
        .first()
    )
    hw = _get_hardware_specs_dict(server, extra, latest_sys)
    cpu_cores = hw.get("cpu", {}).get("cores") or hw.get("cpu", {}).get("logical_cores") or 0
    ram_mb = round(latest_sys.mem_total / (1024 * 1024)) if (latest_sys and latest_sys.mem_total) else (hw.get("memory", {}).get("total_mb") or 0)

    return {
        "server_id": sid,
        "range": range,
        "from": start.isoformat(),
        "to": now.isoformat(),
        "cpu_cores": cpu_cores,
        "ram_mb": ram_mb,
        "points": points,
    }


@router.get("/api/servers/{sid}/system")
def api_server_system(
    sid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Snapshot HW/jaringan terbaru + riwayat singkat + akun + unit services."""
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    latest = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(desc(SystemSnapshot.timestamp))
        .first()
    )
    series = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(desc(SystemSnapshot.timestamp))
        .limit(60)
        .all()
    )
    series = list(reversed(series))

    def parse_list(raw):
        try:
            obj = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            obj = None
        return obj if isinstance(obj, list) else []

    def parse_dict(raw):
        try:
            obj = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            obj = None
        return obj if isinstance(obj, dict) else None

    acc_list = parse_list(extra.accounts if extra else None)
    net_list = parse_list(latest.net) if latest else []
    if net_list and server.ip_address:
        has_any_ip = any(isinstance(n, dict) and n.get("ip_addrs") for n in net_list)
        if not has_any_ip:
            target_n = next(
                (
                    n
                    for n in net_list
                    if isinstance(n, dict)
                    and n.get("is_up")
                    and not any(str(n.get("iface", "")).startswith(p) for p in ("docker", "br-", "veth", "virbr", "lo"))
                ),
                None,
            )
            if not target_n:
                target_n = next((n for n in net_list if isinstance(n, dict) and n.get("is_up")), None)
            if target_n and isinstance(target_n, dict):
                target_n["ip_addrs"] = [server.ip_address]

    disks_raw = parse_list(latest.disks) if latest else []
    disks_enriched = _get_storage_runway_for_server(db, sid, disks_raw)

    fim_paths_db = (
        db.query(FIMPath)
        .filter(FIMPath.server_id == sid)
        .order_by(FIMPath.category.desc(), FIMPath.path.asc())
        .all()
    )
    fim_events_db = (
        db.query(FIMEvent)
        .filter(FIMEvent.server_id == sid)
        .order_by(desc(FIMEvent.detected_at))
        .limit(50)
        .all()
    )

    return {
        "server_id": sid,
        "ts": latest.timestamp.isoformat() if latest else None,
        "system": {
            "cpu": round(latest.cpu, 1) if latest else None,
            "load1": round(latest.load1, 2) if latest else None,
            "load5": round(latest.load5, 2) if latest else None,
            "load15": round(latest.load15, 2) if latest else None,
            "mem_total": latest.mem_total if latest else None,
            "mem_used": latest.mem_used if latest else None,
            "mem_avail": latest.mem_avail if latest else None,
            "swap_total": latest.swap_total if latest else None,
            "swap_used": latest.swap_used if latest else None,
            "procs": latest.procs if latest else None,
            "uptime": latest.uptime_secs if latest else None,
            "disks": disks_enriched,
            "net": net_list,
        },
        "accounts": acc_list if (extra and extra.accounts) else None,
        "system_groups": parse_list(extra.system_groups if extra else None) if (extra and extra.system_groups) else None,
        "listening_ports": parse_list(extra.listening_ports if extra else None) if (extra and extra.listening_ports) else None,
        "cron_jobs": parse_dict(extra.cron_jobs if extra else None) if (extra and extra.cron_jobs) else None,
        "firewall": parse_dict(extra.firewall if extra else None) if (extra and extra.firewall) else None,
        "ssl_certs": parse_list(extra.ssl_certs if extra else None) if (extra and extra.ssl_certs) else None,
        "fim_paths": [
            {
                "id": fp.id,
                "path": fp.path,
                "category": fp.category,
                "scope": fp.scope,
                "status": fp.status,
                "size_human": "Direktori" if (fp.size_human and "Direktori" in fp.size_human) else (fp.size_human or "-"),
                "size_detail": getattr(fp, "size_detail", None) or (fp.size_human if fp.size_human != "Direktori" else "Direktori"),
                "sha256_hash": fp.sha256_hash or "-",
                "last_sha256_hash": fp.last_sha256_hash or "-",
                "permissions": fp.permissions or "-",
                "owner_group": fp.owner_group or "-",
                "created_by": fp.created_by or "",
                "last_checked_at": fp.last_checked_at.isoformat() if fp.last_checked_at else None,
            }
            for fp in fim_paths_db
        ],
        "fim_events": [
            {
                "id": fe.id,
                "path": fe.path,
                "event_type": fe.event_type,
                "severity": fe.severity,
                "details": fe.details or "-",
                "detected_at": fe.detected_at.isoformat() if fe.detected_at else None,
            }
            for fe in fim_events_db
        ],
        "systemd_units": parse_list(extra.systemd_units if extra else None) if (extra and extra.systemd_units) else None,
        "apt_upgradable": extra.apt_upgradable if extra else 0,
        "apt_last_update": extra.apt_last_update.isoformat() if (extra and extra.apt_last_update) else None,
        "apt_packages": parse_list(extra.apt_packages if extra else None) if (extra and extra.apt_packages) else [],
        "series": [
            {
                "ts": s.timestamp.isoformat(),
                "cpu": round(s.cpu, 1),
                "mem": round(s.mem_used / s.mem_total * 100, 1) if s.mem_total else 0,
            }
            for s in series
        ],
    }
