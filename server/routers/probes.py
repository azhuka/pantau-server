"""Synthetic Probing router (HTTP, HTTPS, Ping ICMP, TCP Handshake)."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

try:
    from models import ProbeLog, ProbeTarget, Server, ServerProblem, User
    from prober import execute_probe, record_probe_execution
    from core.database import SessionLocal, get_db
    from core.security import get_current_user, require_user, _verify_csrf_header
    from core.templates import tpl
    from core.utils import _fmt_short_dt
    from services.audit_service import _audit
except ImportError:
    from server.models import ProbeLog, ProbeTarget, Server, ServerProblem, User
    from server.prober import execute_probe, record_probe_execution
    from server.core.database import SessionLocal, get_db
    from server.core.security import get_current_user, require_user, _verify_csrf_header
    from server.core.templates import tpl
    from server.core.utils import _fmt_short_dt
    from server.services.audit_service import _audit

logger = logging.getLogger("pantau.probes")

router = APIRouter(tags=["Synthetic Probing"])

_active_bg_tasks = set()


async def _run_initial_probe_background(probe_id: int, p_data: dict) -> None:
    try:
        res = await execute_probe(p_data)
        with SessionLocal() as sess:
            record_probe_execution(sess, probe_id, res, datetime.utcnow())
    except Exception as exc:
        logger.warning("[prober] Initial probe check failed: %s", exc)


@router.get("/probing", response_class=HTMLResponse)
@router.get("/probes", response_class=HTMLResponse)
def probing_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    servers_list = db.query(Server).order_by(Server.hostname).all()
    servers_data = [{"id": s.id, "hostname": s.hostname, "ip_address": s.ip_address} for s in servers_list]

    return tpl(
        request,
        "probing.html",
        {
            "user": user,
            "servers": servers_data,
            "can_probing": user.has_perm("can_probing"),
        },
    )


@router.get("/api/probes")
def api_probes_list(
    request: Request,
    type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Harap login terlebih dahulu")

    query = db.query(ProbeTarget).order_by(ProbeTarget.name)

    if type and type != "all":
        query = query.filter(ProbeTarget.probe_type == type)
    if status and status != "all":
        if status == "paused":
            query = query.filter(ProbeTarget.is_active == 0)
        else:
            query = query.filter(ProbeTarget.status == status, ProbeTarget.is_active == 1)
    if search and search.strip():
        s = f"%{search.strip()}%"
        query = query.filter(or_(ProbeTarget.name.like(s), ProbeTarget.target.like(s)))

    all_probes = db.query(ProbeTarget).all()
    filtered_probes = query.all()

    total = len(all_probes)
    up_cnt = sum(1 for p in all_probes if p.status == "up" and p.is_active)
    down_cnt = sum(1 for p in all_probes if p.status == "down" and p.is_active)
    degraded_cnt = sum(1 for p in all_probes if p.status == "degraded" and p.is_active)
    paused_cnt = sum(1 for p in all_probes if not p.is_active)

    active_up_lats = [
        p.last_latency_ms
        for p in all_probes
        if p.status in ("up", "degraded") and p.last_latency_ms is not None
    ]
    avg_lat = round(sum(active_up_lats) / len(active_up_lats), 1) if active_up_lats else 0.0

    uptimes_24 = [p.uptime_24h for p in all_probes if p.uptime_24h is not None and p.is_active]
    avg_uptime_24h = round(sum(uptimes_24) / len(uptimes_24), 2) if uptimes_24 else 100.0

    uptimes_30 = [p.uptime_30d for p in all_probes if p.uptime_30d is not None and p.is_active]
    avg_uptime_30d = round(sum(uptimes_30) / len(uptimes_30), 2) if uptimes_30 else 100.0

    servers_map = {s.id: s.hostname for s in db.query(Server).all()}

    probes_out = []
    for p in filtered_probes:
        probes_out.append(
            {
                "id": p.id,
                "name": p.name,
                "probe_type": p.probe_type,
                "target": p.target,
                "port": p.port,
                "server_id": p.server_id,
                "server_hostname": servers_map.get(p.server_id) if p.server_id else None,
                "tier": getattr(p, "tier", 2) or 2,
                "interval_seconds": p.interval_seconds,
                "timeout_seconds": p.timeout_seconds,
                "http_method": p.http_method,
                "http_headers": p.http_headers,
                "http_body": p.http_body,
                "expected_status": p.expected_status,
                "keyword_match": p.keyword_match,
                "ssl_verify": bool(p.ssl_verify),
                "ssl_expiry_threshold_days": p.ssl_expiry_threshold_days,
                "latency_threshold_ms": p.latency_threshold_ms,
                "consecutive_threshold": p.consecutive_threshold,
                "is_active": bool(p.is_active),
                "status": p.status if p.is_active else "paused",
                "last_checked_at": p.last_checked_at.isoformat() if p.last_checked_at else None,
                "last_latency_ms": round(p.last_latency_ms, 1) if p.last_latency_ms is not None else None,
                "last_status_code": p.last_status_code,
                "last_error": p.last_error,
                "ssl_expires_at": p.ssl_expires_at.isoformat() if p.ssl_expires_at else None,
                "ssl_days_remaining": p.ssl_days_remaining,
                "uptime_24h": round(p.uptime_24h if p.uptime_24h is not None else 100.0, 1),
                "uptime_30d": round(p.uptime_30d if p.uptime_30d is not None else 100.0, 1),
                "consecutive_failures": p.consecutive_failures,
                "consecutive_successes": p.consecutive_successes,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "created_by": p.created_by,
            }
        )

    return {
        "ok": True,
        "summary": {
            "total": total,
            "up": up_cnt,
            "down": down_cnt,
            "degraded": degraded_cnt,
            "paused": paused_cnt,
            "avg_latency_ms": avg_lat,
            "avg_uptime_24h": avg_uptime_24h,
            "avg_uptime_30d": avg_uptime_30d,
        },
        "probes": probes_out,
    }


@router.post("/api/probes")
async def api_probe_create(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_probing")):
        raise HTTPException(status_code=403, detail="Akses ditolak: Izin 'can_probing' diperlukan")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Format JSON tidak valid")

    name = str(body.get("name", "")).strip()
    probe_type = str(body.get("probe_type", "")).strip().lower()
    target = str(body.get("target", "")).strip()

    if not name or len(name) < 2 or len(name) > 100:
        raise HTTPException(status_code=400, detail="Nama probe wajib diisi (2-100 karakter)")
    if probe_type not in ("http", "https", "ping", "tcp"):
        raise HTTPException(status_code=400, detail="Tipe probe harus: http, https, ping, atau tcp")
    if not target:
        raise HTTPException(status_code=400, detail="Target URL atau Host wajib diisi")

    port = body.get("port")
    if probe_type == "tcp":
        try:
            port = int(port)
            if port < 1 or port > 65535:
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Port TCP harus berupa angka valid (1-65535)")
    else:
        port = int(port) if port and str(port).isdigit() else None

    server_id = body.get("server_id")
    server_id = int(server_id) if server_id and str(server_id).isdigit() else None

    interval = int(body.get("interval_seconds", 60) or 60)
    interval = max(10, min(86400, interval))

    timeout = int(body.get("timeout_seconds", 5) or 5)
    timeout = max(1, min(60, timeout))

    http_method = str(body.get("http_method", "GET")).strip().upper()
    if http_method not in ("GET", "POST", "HEAD", "PUT"):
        http_method = "GET"

    http_headers = body.get("http_headers")
    if isinstance(http_headers, dict):
        http_headers = json.dumps(http_headers)
    elif isinstance(http_headers, str) and http_headers.strip():
        try:
            json.loads(http_headers)
            http_headers = http_headers.strip()
        except Exception:
            raise HTTPException(status_code=400, detail="Header kustom harus berformat JSON valid")
    else:
        http_headers = None

    http_body = body.get("http_body") or None
    expected_status = str(body.get("expected_status", "200")).strip() or "200"
    raw_kw = body.get("keyword_match")
    keyword_match = (
        str(raw_kw).strip()
        if (raw_kw is not None and str(raw_kw).strip() and str(raw_kw).strip().lower() != "none")
        else None
    )
    ssl_verify = 1 if body.get("ssl_verify", True) else 0
    ssl_expiry_days = int(body.get("ssl_expiry_threshold_days", 14) or 14)

    latency_threshold = int(body.get("latency_threshold_ms", 2000) or 2000)
    consec_threshold = int(body.get("consecutive_threshold", 2) or 2)
    tier_input = body.get("tier", 2)
    if isinstance(tier_input, str):
        tier_input = "".join(c for c in tier_input if c.isdigit())
    try:
        tier_raw = int(tier_input or 2)
    except (ValueError, TypeError):
        tier_raw = 2
    tier_val = 1 if tier_raw == 1 else 2

    new_probe = ProbeTarget(
        name=name,
        probe_type=probe_type,
        target=target,
        port=port,
        server_id=server_id,
        tier=tier_val,
        interval_seconds=interval,
        timeout_seconds=timeout,
        http_method=http_method,
        http_headers=http_headers,
        http_body=http_body,
        expected_status=expected_status,
        keyword_match=keyword_match,
        ssl_verify=ssl_verify,
        ssl_expiry_threshold_days=ssl_expiry_days,
        latency_threshold_ms=latency_threshold,
        consecutive_threshold=consec_threshold,
        is_active=1,
        status="unknown",
        created_at=datetime.utcnow(),
        created_by=user.username,
    )
    db.add(new_probe)
    db.commit()
    db.refresh(new_probe)

    _audit(
        db,
        user.username,
        "probe_add",
        f"Tambah endpoint pantau {probe_type.upper()}: '{name}' -> {target}",
        "berhasil",
        server_id=server_id,
    )

    p_dict = {
        "id": new_probe.id,
        "probe_type": new_probe.probe_type,
        "target": new_probe.target,
        "port": new_probe.port,
        "timeout_seconds": new_probe.timeout_seconds,
        "latency_threshold_ms": new_probe.latency_threshold_ms,
        "http_method": new_probe.http_method,
        "http_headers": new_probe.http_headers,
        "http_body": new_probe.http_body,
        "expected_status": new_probe.expected_status,
        "keyword_match": new_probe.keyword_match,
        "ssl_verify": new_probe.ssl_verify,
        "ssl_expiry_threshold_days": new_probe.ssl_expiry_threshold_days,
    }
    _bg_t = asyncio.create_task(_run_initial_probe_background(new_probe.id, p_dict))
    _active_bg_tasks.add(_bg_t)
    _bg_t.add_done_callback(_active_bg_tasks.discard)

    return {
        "ok": True,
        "message": f"Endpoint pantau '{name}' berhasil dibuat",
        "probe_id": new_probe.id,
    }


@router.get("/api/probes/open-problems")
def api_probes_open_problems(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    standalone_probs = (
        db.query(ServerProblem)
        .filter(
            ServerProblem.server_id.is_(None),
            ServerProblem.probe_id.isnot(None),
            ServerProblem.resolved_at.is_(None),
        )
        .all()
    )
    if not standalone_probs:
        return []
    probes_map = {p.id: p for p in db.query(ProbeTarget).all()}
    res = []
    for sp in standalone_probs:
        prb = probes_map.get(sp.probe_id)
        prb_name = prb.name if prb else f"Endpoint #{sp.probe_id}"
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
        res.append(
            {
                "id": sp.id,
                "server_id": None,
                "probe_id": sp.probe_id,
                "probe_name": prb_name,
                "hostname": prb_name,
                "group_name": "Endpoint",
                "tier": getattr(prb, "tier", 2) or 2 if prb else 2,
                "severity": sp.severity or "warning",
                "message": sp.message or "",
                "key": sp.key or "",
                "is_ignored": bool(sp.is_ignored),
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
        )
    return res


@router.get("/api/probes/{pid}")
def api_probe_get(
    pid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Endpoint pantau tidak ditemukan")

    servers_map = {s.id: s.hostname for s in db.query(Server).all()}
    recent_logs = (
        db.query(ProbeLog)
        .filter(ProbeLog.probe_id == pid)
        .order_by(desc(ProbeLog.checked_at))
        .limit(50)
        .all()
    )

    return {
        "ok": True,
        "probe": {
            "id": probe.id,
            "name": probe.name,
            "probe_type": probe.probe_type,
            "target": probe.target,
            "port": probe.port,
            "server_id": probe.server_id,
            "server_hostname": servers_map.get(probe.server_id) if probe.server_id else None,
            "tier": getattr(probe, "tier", 2) or 2,
            "interval_seconds": probe.interval_seconds,
            "timeout_seconds": probe.timeout_seconds,
            "http_method": probe.http_method,
            "http_headers": probe.http_headers,
            "http_body": probe.http_body,
            "expected_status": probe.expected_status,
            "keyword_match": probe.keyword_match,
            "ssl_verify": bool(probe.ssl_verify),
            "ssl_expiry_threshold_days": probe.ssl_expiry_threshold_days,
            "latency_threshold_ms": probe.latency_threshold_ms,
            "consecutive_threshold": probe.consecutive_threshold,
            "is_active": bool(probe.is_active),
            "status": probe.status if probe.is_active else "paused",
            "last_checked_at": probe.last_checked_at.isoformat() if probe.last_checked_at else None,
            "last_latency_ms": round(probe.last_latency_ms, 1) if probe.last_latency_ms is not None else None,
            "last_status_code": probe.last_status_code,
            "last_error": probe.last_error,
            "ssl_expires_at": probe.ssl_expires_at.isoformat() if probe.ssl_expires_at else None,
            "ssl_days_remaining": probe.ssl_days_remaining,
            "uptime_24h": round(probe.uptime_24h if probe.uptime_24h is not None else 100.0, 1),
            "uptime_30d": round(probe.uptime_30d if probe.uptime_30d is not None else 100.0, 1),
            "consecutive_failures": probe.consecutive_failures,
            "consecutive_successes": probe.consecutive_successes,
            "created_at": probe.created_at.isoformat() if probe.created_at else None,
            "created_by": probe.created_by,
        },
        "recent_logs": [
            {
                "id": l.id,
                "checked_at": l.checked_at.isoformat(),
                "status": l.status,
                "latency_ms": round(l.latency_ms, 1) if l.latency_ms is not None else None,
                "status_code": l.status_code,
                "error_message": l.error_message,
            }
            for l in recent_logs
        ],
    }


@router.put("/api/probes/{pid}")
async def api_probe_update(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_probing")):
        raise HTTPException(status_code=403, detail="Akses ditolak: Izin 'can_probing' diperlukan")

    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Endpoint pantau tidak ditemukan")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Format JSON tidak valid")

    name = str(body.get("name", probe.name)).strip()
    probe_type = str(body.get("probe_type", probe.probe_type)).strip().lower()
    target = str(body.get("target", probe.target)).strip()

    if not name or len(name) < 2 or len(name) > 100:
        raise HTTPException(status_code=400, detail="Nama endpoint pantau wajib diisi (2-100 karakter)")
    if probe_type not in ("http", "https", "ping", "tcp"):
        raise HTTPException(status_code=400, detail="Tipe protokol harus: http, https, ping, atau tcp")
    if not target:
        raise HTTPException(status_code=400, detail="Target URL atau Host wajib diisi")

    port = body.get("port")
    if probe_type == "tcp":
        try:
            port = int(port)
            if port < 1 or port > 65535:
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Port TCP harus berupa angka valid (1-65535)")
    else:
        port = int(port) if port and str(port).isdigit() else None

    server_id = body.get("server_id")
    server_id = int(server_id) if server_id and str(server_id).isdigit() else None

    probe.name = name
    probe.probe_type = probe_type
    probe.target = target
    probe.port = port
    probe.server_id = server_id
    probe.interval_seconds = max(10, min(86400, int(body.get("interval_seconds", probe.interval_seconds) or 60)))
    probe.timeout_seconds = max(1, min(60, int(body.get("timeout_seconds", probe.timeout_seconds) or 5)))
    probe.http_method = str(body.get("http_method", probe.http_method or "GET")).strip().upper()

    raw_headers = body.get("http_headers")
    if isinstance(raw_headers, dict):
        probe.http_headers = json.dumps(raw_headers)
    elif isinstance(raw_headers, str) and raw_headers.strip():
        try:
            json.loads(raw_headers)
            probe.http_headers = raw_headers.strip()
        except Exception:
            raise HTTPException(status_code=400, detail="Header kustom harus berformat JSON valid")
    else:
        probe.http_headers = None

    probe.http_body = body.get("http_body") or None
    probe.expected_status = str(body.get("expected_status", probe.expected_status or "200")).strip() or "200"
    raw_kw = body.get("keyword_match")
    probe.keyword_match = (
        str(raw_kw).strip()
        if (raw_kw is not None and str(raw_kw).strip() and str(raw_kw).strip().lower() != "none")
        else None
    )
    probe.ssl_verify = 1 if body.get("ssl_verify", probe.ssl_verify) else 0
    probe.ssl_expiry_threshold_days = int(
        body.get("ssl_expiry_threshold_days", probe.ssl_expiry_threshold_days or 14) or 14
    )
    probe.latency_threshold_ms = int(body.get("latency_threshold_ms", probe.latency_threshold_ms or 2000) or 2000)
    probe.consecutive_threshold = int(body.get("consecutive_threshold", probe.consecutive_threshold or 2) or 2)
    if "tier" in body:
        tier_input = body.get("tier", getattr(probe, "tier", 2) or 2)
        if isinstance(tier_input, str):
            tier_input = "".join(c for c in tier_input if c.isdigit())
        try:
            tier_raw = int(tier_input or 2)
        except (ValueError, TypeError):
            tier_raw = 2
        probe.tier = 1 if tier_raw == 1 else 2

    db.commit()
    _audit(
        db,
        user.username,
        "probe_edit",
        f"Ubah endpoint pantau #{pid} '{probe.name}' -> {probe.target}",
        "berhasil",
        server_id=probe.server_id,
    )

    return {"ok": True, "message": f"Endpoint pantau '{probe.name}' berhasil diperbarui"}


@router.delete("/api/probes/{pid}")
def api_probe_delete(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_probing")):
        raise HTTPException(status_code=403, detail="Akses ditolak: Izin 'can_probing' diperlukan")

    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Endpoint pantau tidak ditemukan")

    name = probe.name
    sid = probe.server_id
    db.delete(probe)
    db.commit()
    _audit(db, user.username, "probe_delete", f"Hapus endpoint pantau #{pid} '{name}'", "berhasil", server_id=sid)

    return {"ok": True, "message": f"Endpoint pantau '{name}' berhasil dihapus"}


@router.post("/api/probes/{pid}/toggle")
def api_probe_toggle(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_probing")):
        raise HTTPException(status_code=403, detail="Akses ditolak: Izin 'can_probing' diperlukan")

    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Endpoint pantau tidak ditemukan")

    new_active = 0 if probe.is_active else 1
    probe.is_active = new_active
    probe.status = "unknown" if new_active else "paused"
    if not new_active:
        open_prob = (
            db.query(ServerProblem)
            .filter(
                ServerProblem.probe_id == probe.id,
                ServerProblem.resolved_at.is_(None),
            )
            .first()
        )
        if open_prob:
            open_prob.resolved_at = datetime.utcnow()
            open_prob.resolved_note = "paused"

    db.commit()
    action_str = "diaktifkan" if new_active else "dijeda"
    _audit(
        db,
        user.username,
        "probe_toggle",
        f"Endpoint pantau #{pid} '{probe.name}' {action_str}",
        "berhasil",
        server_id=probe.server_id,
    )

    return {"ok": True, "is_active": bool(new_active), "message": f"Endpoint pantau '{probe.name}' {action_str}"}


@router.post("/api/probes/{pid}/test")
async def api_probe_test_now(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak")

    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Endpoint pantau tidak ditemukan")

    p_data = {
        "id": probe.id,
        "probe_type": probe.probe_type,
        "target": probe.target,
        "port": probe.port,
        "timeout_seconds": probe.timeout_seconds,
        "latency_threshold_ms": probe.latency_threshold_ms,
        "http_method": probe.http_method,
        "http_headers": probe.http_headers,
        "http_body": probe.http_body,
        "expected_status": probe.expected_status,
        "keyword_match": probe.keyword_match,
        "ssl_verify": probe.ssl_verify,
        "ssl_expiry_threshold_days": probe.ssl_expiry_threshold_days,
    }

    res = await execute_probe(p_data)
    now = datetime.utcnow()
    record_probe_execution(db, probe.id, res, now)
    _audit(
        db,
        user.username,
        "probe_test",
        f"Uji langsung probe #{pid} '{probe.name}' -> {res.status.upper()}",
        "berhasil",
        server_id=probe.server_id,
    )

    return {
        "ok": True,
        "result": res.to_dict(),
        "probe": {
            "status": probe.status,
            "last_latency_ms": probe.last_latency_ms,
            "last_status_code": probe.last_status_code,
            "last_error": probe.last_error,
            "uptime_24h": probe.uptime_24h,
            "uptime_30d": probe.uptime_30d,
        },
    }


@router.post("/api/probes/test-adhoc")
async def api_probe_test_adhoc(
    request: Request,
    user: User = Depends(require_user),
):
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Format JSON tidak valid")

    target = str(body.get("target", "")).strip()
    if not target:
        raise HTTPException(status_code=400, detail="Target URL atau Host wajib diisi")

    res = await execute_probe(body)
    return {
        "ok": True,
        "result": res.to_dict(),
    }


@router.get("/api/probes/{pid}/history")
def api_probe_history(
    pid: int,
    limit: int = 100,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Probe target tidak ditemukan")

    limit = max(10, min(500, limit))
    logs = (
        db.query(ProbeLog)
        .filter(ProbeLog.probe_id == pid)
        .order_by(desc(ProbeLog.checked_at))
        .limit(limit)
        .all()
    )

    log_list = []
    latencies = []
    for l in logs:
        if l.latency_ms is not None:
            latencies.append(l.latency_ms)
        log_list.append(
            {
                "id": l.id,
                "checked_at": l.checked_at.isoformat(),
                "status": l.status,
                "latency_ms": round(l.latency_ms, 1) if l.latency_ms is not None else None,
                "status_code": l.status_code,
                "error_message": l.error_message,
            }
        )

    avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else None
    min_lat = round(min(latencies), 1) if latencies else None
    max_lat = round(max(latencies), 1) if latencies else None

    chart_points = [
        {
            "t": l["checked_at"],
            "lat": l["latency_ms"],
            "status": l["status"],
            "code": l["status_code"],
        }
        for l in reversed(log_list)
    ]

    return {
        "ok": True,
        "probe": {
            "id": probe.id,
            "name": probe.name,
            "probe_type": probe.probe_type,
            "target": probe.target,
            "port": probe.port,
            "status": probe.status,
            "uptime_24h": probe.uptime_24h,
            "uptime_30d": probe.uptime_30d,
        },
        "stats": {
            "avg_latency_ms": avg_lat,
            "min_latency_ms": min_lat,
            "max_latency_ms": max_lat,
            "total_samples": len(log_list),
        },
        "chart": chart_points,
        "logs": log_list,
    }
