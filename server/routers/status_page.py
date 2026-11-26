"""Public Status Page API router (zero-trust summary, no sensitive internal data)."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.database import get_db
from models.probe import ProbeTarget
from models.problem import ServerProblem
from models.server import Server

router = APIRouter(tags=["Status Page"])


@router.get("/api/status-page/summary")
def public_status_summary(request: Request, db: Session = Depends(get_db)):
    """Public read-only operational status summary across assets and synthetic probes."""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=60)

    servers = db.query(Server).filter(Server.is_active == 1).order_by(Server.hostname.asc()).all()
    active_probs = db.query(ServerProblem).filter(ServerProblem.resolved_at.is_(None)).all()
    probes = db.query(ProbeTarget).filter(ProbeTarget.is_active == 1).order_by(ProbeTarget.name.asc()).all()

    prob_by_srv: dict[int, list[ServerProblem]] = {}
    for p in active_probs:
        if not p.is_ignored:
            prob_by_srv.setdefault(p.server_id, []).append(p)

    assets_out = []
    down_count = 0
    degraded_count = 0
    maint_count = 0

    for s in servers:
        online = bool(s.last_seen and s.last_seen >= cutoff)
        if s.is_maintenance:
            st = "maintenance"
            maint_count += 1
        elif not online:
            st = "down"
            down_count += 1
        elif any(p.severity in ("danger", "critical") for p in prob_by_srv.get(s.id, [])):
            st = "degraded"
            degraded_count += 1
        else:
            st = "operational"
        assets_out.append({
            "hostname": s.hostname,
            "group": s.group_name or "Default",
            "status": st,
        })

    probes_out = [
        {
            "name": pr.name,
            "type": pr.probe_type,
            "status": pr.status or "unknown",
            "uptime_24h": round(pr.uptime_24h, 2) if pr.uptime_24h is not None else 100.0,
            "latency_ms": round(pr.last_latency_ms, 1) if pr.last_latency_ms is not None else None,
        }
        for pr in probes
    ]

    overall = "operational"
    if down_count > 0 or any(p["status"] == "down" for p in probes_out):
        overall = "major_outage" if down_count > 1 else "partial_outage"
    elif degraded_count > 0 or any(p["status"] == "degraded" for p in probes_out):
        overall = "degraded"

    return {
        "overall_status": overall,
        "generated_at": now.isoformat() + "Z",
        "counts": {
            "total_assets": len(assets_out),
            "operational": len(assets_out) - down_count - degraded_count - maint_count,
            "degraded": degraded_count,
            "down": down_count,
            "maintenance": maint_count,
        },
        "assets": assets_out,
        "probes": probes_out,
    }
