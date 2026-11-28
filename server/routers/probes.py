"""Synthetic Probing HTTP API router (HTTP/HTTPS, TCP, ICMP)."""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from core.database import SessionLocal, get_db
from models.misc import AuditLog
from models.probe import ProbeLog, ProbeTarget
from models.server import Server
from models.user import User
from routers.auth import get_current_user
from services.probe_service import execute_probe, record_probe_execution

router = APIRouter(tags=["Synthetic Probing"])

_bg_tasks: set[asyncio.Task] = set()


def _require_probing_perm(user: User) -> None:
    if not (user.is_master_admin or user.has_perm("can_probing")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Synthetic Probing permission (can_probing) is required",
        )


def _assert_probe_access(user: User, probe: ProbeTarget) -> None:
    if user.allowed_server_ids is None:
        return
    if not probe.server_id or not user.can_access_server(probe.server_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for this probe",
        )


def _probe_to_dict(p: ProbeTarget, servers_map: dict[int, str]) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "probe_type": p.probe_type,
        "target": p.target,
        "port": p.port,
        "server_id": p.server_id,
        "server_hostname": servers_map.get(p.server_id) if p.server_id else None,
        "tier": getattr(p, "tier", 1) or 1,
        "interval_seconds": p.interval_seconds or 60,
        "timeout_seconds": p.timeout_seconds or 5,
        "http_method": p.http_method or "GET",
        "expected_status": p.expected_status or "200-299",
        "keyword_match": p.keyword_match,
        "ssl_verify": bool(p.ssl_verify),
        "latency_threshold_ms": p.latency_threshold_ms or 1000,
        "consecutive_threshold": p.consecutive_threshold or 3,
        "is_active": bool(p.is_active),
        "status": p.status if p.is_active else "paused",
        "last_checked_at": p.last_checked_at.isoformat() if p.last_checked_at else None,
        "last_latency_ms": round(p.last_latency_ms, 1) if p.last_latency_ms is not None else None,
        "last_status_code": p.last_status_code,
        "last_error": p.last_error,
        "ssl_expires_at": p.ssl_expires_at.isoformat() if p.ssl_expires_at else None,
        "ssl_days_remaining": p.ssl_days_remaining,
        "uptime_24h": round(p.uptime_24h, 2) if p.uptime_24h is not None else 100.0,
        "uptime_30d": round(p.uptime_30d, 2) if p.uptime_30d is not None else 100.0,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def _run_initial_probe(probe_id: int, probe_data: dict) -> None:
    try:
        res = await execute_probe(probe_data)
        with SessionLocal() as db:
            record_probe_execution(db, probe_id, res, datetime.utcnow())
    except Exception:
        pass


@router.get("/api/probes")
def list_probes(
    probe_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ProbeTarget).order_by(ProbeTarget.name.asc())
    all_q = db.query(ProbeTarget)

    if user.allowed_server_ids is not None:
        allowed_ids = user.get_allowed_server_ids()
        if allowed_ids:
            query = query.filter(ProbeTarget.server_id.in_(allowed_ids))
            all_q = all_q.filter(ProbeTarget.server_id.in_(allowed_ids))
        else:
            query = query.filter(ProbeTarget.id == -1)
            all_q = all_q.filter(ProbeTarget.id == -1)

    if probe_type and probe_type != "all":
        if probe_type == "web":
            query = query.filter(ProbeTarget.probe_type.in_(["http", "https"]))
        else:
            query = query.filter(ProbeTarget.probe_type == probe_type)
    if status_filter and status_filter != "all":
        if status_filter == "paused":
            query = query.filter(ProbeTarget.is_active == 0)
        else:
            query = query.filter(ProbeTarget.status == status_filter, ProbeTarget.is_active == 1)
    if search and search.strip():
        s = f"%{search.strip()}%"
        query = query.filter(or_(ProbeTarget.name.like(s), ProbeTarget.target.like(s)))

    all_probes = all_q.all()
    filtered = query.all()
    servers_map = {s.id: s.hostname for s in db.query(Server.id, Server.hostname).filter(Server.is_active == 1).all()}

    up_cnt = sum(1 for p in all_probes if p.status == "up" and p.is_active)
    down_cnt = sum(1 for p in all_probes if p.status == "down" and p.is_active)
    degraded_cnt = sum(1 for p in all_probes if p.status == "degraded" and p.is_active)
    paused_cnt = sum(1 for p in all_probes if not p.is_active)
    lats = [p.last_latency_ms for p in all_probes if p.is_active and p.last_latency_ms is not None]
    avg_lat = round(sum(lats) / len(lats), 1) if lats else None

    return {
        "probes": [_probe_to_dict(p, servers_map) for p in filtered],
        "summary": {
            "total": len(all_probes),
            "up": up_cnt,
            "down": down_cnt,
            "degraded": degraded_cnt,
            "paused": paused_cnt,
            "avg_latency_ms": avg_lat,
        },
    }


@router.post("/api/probes")
async def create_probe(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_probing_perm(user)
    name = str(body.get("name") or "").strip()[:100]
    ptype = str(body.get("probe_type") or "http").strip().lower()
    target = str(body.get("target") or "").strip()[:255]
    if not name or not target:
        raise HTTPException(status_code=400, detail="Probe name and target are required")
    if ptype not in ("http", "https", "tcp", "icmp"):
        raise HTTPException(status_code=400, detail="Probe type must be http, https, tcp, or icmp")

    sid = body.get("server_id")
    if sid is not None and sid != "":
        sid = int(sid)
        if not user.can_access_server(sid):
            raise HTTPException(status_code=403, detail="Access denied for selected asset")
    else:
        if user.allowed_server_ids is not None:
            raise HTTPException(status_code=403, detail="Scoped operators must bind probes to an authorized asset")
        sid = None

    port = int(body["port"]) if body.get("port") not in (None, "") else None
    raw_tier = body.get("tier")
    if raw_tier in (1, 2, 3, "1", "2", "3"):
        tier_val = int(raw_tier)
    elif sid is not None:
        srv_row = db.query(Server.tier).filter(Server.id == sid).first()
        tier_val = int(srv_row[0] or 1) if srv_row else 1
    else:
        tier_val = 1
    probe = ProbeTarget(
        name=name,
        probe_type=ptype,
        target=target,
        port=port,
        server_id=sid,
        tier=tier_val,
        interval_seconds=max(10, min(3600, int(body.get("interval_seconds") or 60))),
        timeout_seconds=max(1, min(30, int(body.get("timeout_seconds") or 5))),
        http_method=str(body.get("http_method") or "GET").upper()[:10],
        expected_status=str(body.get("expected_status") or "200-299")[:50],
        keyword_match=str(body.get("keyword_match") or "").strip()[:255] or None,
        ssl_verify=1 if body.get("ssl_verify", True) else 0,
        latency_threshold_ms=max(50, int(body.get("latency_threshold_ms") or 1000)),
        consecutive_threshold=max(1, min(10, int(body.get("consecutive_threshold") or 3))),
        is_active=1,
        status="unknown",
        created_by=user.username,
    )
    db.add(probe)
    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="probe_create",
        target=f"{name} ({ptype}: {target})",
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(probe)

    task = asyncio.create_task(_run_initial_probe(probe.id, {
        "probe_type": probe.probe_type,
        "target": probe.target,
        "port": probe.port,
        "timeout_seconds": probe.timeout_seconds,
        "http_method": probe.http_method,
        "expected_status": probe.expected_status,
        "keyword_match": probe.keyword_match,
        "ssl_verify": bool(probe.ssl_verify),
        "latency_threshold_ms": probe.latency_threshold_ms,
    }))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)

    servers_map = {s.id: s.hostname for s in db.query(Server.id, Server.hostname).filter(Server.is_active == 1).all()}
    return {"ok": True, "probe": _probe_to_dict(probe, servers_map), "message": f"Probe '{name}' created"}


@router.put("/api/probes/{pid}")
def update_probe(
    pid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_probing_perm(user)
    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Probe not found")
    _assert_probe_access(user, probe)

    if "name" in body and str(body["name"]).strip():
        probe.name = str(body["name"]).strip()[:100]
    if "probe_type" in body and str(body["probe_type"]).lower() in ("http", "https", "tcp", "icmp"):
        probe.probe_type = str(body["probe_type"]).lower()
    if "target" in body and str(body["target"]).strip():
        probe.target = str(body["target"]).strip()[:255]
    if "port" in body:
        probe.port = int(body["port"]) if body["port"] not in (None, "") else None
    if "server_id" in body:
        new_sid = int(body["server_id"]) if body["server_id"] not in (None, "") else None
        if new_sid is None and user.allowed_server_ids is not None:
            raise HTTPException(status_code=403, detail="Scoped operators must bind probes to an authorized asset")
        if new_sid is not None and not user.can_access_server(new_sid):
            raise HTTPException(status_code=403, detail="Access denied for selected asset")
        probe.server_id = new_sid
    if "interval_seconds" in body:
        probe.interval_seconds = max(10, min(3600, int(body["interval_seconds"] or 60)))
    if "timeout_seconds" in body:
        probe.timeout_seconds = max(1, min(30, int(body["timeout_seconds"] or 5)))
    if "http_method" in body:
        probe.http_method = str(body["http_method"] or "GET").upper()[:10]
    if "expected_status" in body:
        probe.expected_status = str(body["expected_status"] or "200-299")[:50]
    if "keyword_match" in body:
        probe.keyword_match = str(body["keyword_match"] or "").strip()[:255] or None
    if "ssl_verify" in body:
        probe.ssl_verify = 1 if body["ssl_verify"] else 0
    if "latency_threshold_ms" in body:
        probe.latency_threshold_ms = max(50, int(body["latency_threshold_ms"] or 1000))
    if "consecutive_threshold" in body:
        probe.consecutive_threshold = max(1, min(10, int(body["consecutive_threshold"] or 3)))
    if "tier" in body and body["tier"] in (1, 2, 3, "1", "2", "3"):
        probe.tier = int(body["tier"])

    db.add(AuditLog(
        server_id=probe.server_id,
        username=user.username,
        action="probe_update",
        target=probe.name,
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "message": f"Probe '{probe.name}' updated"}


@router.delete("/api/probes/{pid}")
def delete_probe(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_probing_perm(user)
    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Probe not found")
    _assert_probe_access(user, probe)
    name = probe.name
    db.query(ProbeLog).filter(ProbeLog.probe_id == pid).delete()
    db.delete(probe)
    db.add(AuditLog(
        server_id=probe.server_id,
        username=user.username,
        action="probe_delete",
        target=name,
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "message": f"Probe '{name}' deleted"}


@router.post("/api/probes/{pid}/toggle")
def toggle_probe(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_probing_perm(user)
    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Probe not found")
    _assert_probe_access(user, probe)
    probe.is_active = 0 if probe.is_active else 1
    state = "resumed" if probe.is_active else "paused"
    db.add(AuditLog(
        server_id=probe.server_id,
        username=user.username,
        action="probe_toggle",
        target=probe.name,
        result=state,
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "is_active": bool(probe.is_active), "message": f"Probe '{probe.name}' {state}"}


@router.post("/api/probes/test-adhoc")
async def test_probe_adhoc(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
):
    _require_probing_perm(user)
    ptype = str(body.get("probe_type") or "http").strip().lower()
    target = str(body.get("target") or "").strip()[:255]
    if not target:
        raise HTTPException(status_code=400, detail="Target URL or Host is required")
    if ptype not in ("http", "https", "tcp", "icmp"):
        raise HTTPException(status_code=400, detail="Probe type must be http, https, tcp, or icmp")
    if user.allowed_server_ids is not None:
        sid_raw = body.get("server_id")
        sid = int(sid_raw) if sid_raw not in (None, "") else None
        if not sid or not user.can_access_server(sid):
            raise HTTPException(status_code=403, detail="Scoped operators must bind probes to an authorized asset")
    port = int(body["port"]) if body.get("port") not in (None, "") else None
    res = await execute_probe({
        "probe_type": ptype,
        "target": target,
        "port": port,
        "timeout_seconds": max(1, min(30, int(body.get("timeout_seconds") or 5))),
        "http_method": str(body.get("http_method") or "GET").upper()[:10],
        "expected_status": str(body.get("expected_status") or "200-299")[:50],
        "keyword_match": str(body.get("keyword_match") or "").strip()[:255] or None,
        "ssl_verify": bool(body.get("ssl_verify", True)),
        "latency_threshold_ms": max(50, int(body.get("latency_threshold_ms") or 1000)),
    })
    return {"ok": True, "result": res.to_dict()}


@router.post("/api/probes/{pid}/test")
async def test_probe_now(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_probing_perm(user)
    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Probe not found")
    _assert_probe_access(user, probe)
    res = await execute_probe({
        "probe_type": probe.probe_type,
        "target": probe.target,
        "port": probe.port,
        "timeout_seconds": probe.timeout_seconds,
        "http_method": probe.http_method,
        "expected_status": probe.expected_status,
        "keyword_match": probe.keyword_match,
        "ssl_verify": bool(probe.ssl_verify),
        "latency_threshold_ms": probe.latency_threshold_ms,
    })
    record_probe_execution(db, pid, res, datetime.utcnow())
    return {"ok": True, "result": res.to_dict()}


@router.get("/api/probes/{pid}/history")
def probe_history(
    pid: int,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    probe = db.query(ProbeTarget).filter(ProbeTarget.id == pid).first()
    if not probe:
        raise HTTPException(status_code=404, detail="Probe not found")
    _assert_probe_access(user, probe)
    logs = (
        db.query(ProbeLog)
        .filter(ProbeLog.probe_id == pid)
        .order_by(desc(ProbeLog.checked_at))
        .limit(min(200, max(10, limit)))
        .all()
    )
    return {
        "probe_id": pid,
        "name": probe.name,
        "logs": [
            {
                "id": l.id,
                "checked_at": l.checked_at.isoformat() if l.checked_at else None,
                "status": l.status,
                "latency_ms": l.latency_ms,
                "status_code": l.status_code,
                "error_message": l.error_message,
            }
            for l in logs
        ],
    }
