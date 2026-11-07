"""Maintenance window scheduling and suppression service."""

import time
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

try:
    from models import MaintenanceWindow, Server
    from core.database import SessionLocal
except ImportError:
    from server.models import MaintenanceWindow, Server
    from server.core.database import SessionLocal

_ACTIVE_MAINTENANCE_CACHE: dict = {"count": 0, "titles": [], "updated_at": 0.0}


def get_active_maintenance_info() -> tuple[int, list[str]]:
    """Kembalikan tuple (count, titles) dari jendela pemeliharaan yang sedang aktif saat ini."""
    now_ts = time.time()
    if (
        now_ts - _ACTIVE_MAINTENANCE_CACHE.get("updated_at", 0.0) < 15.0
        and _ACTIVE_MAINTENANCE_CACHE.get("titles") is not None
    ):
        return _ACTIVE_MAINTENANCE_CACHE["count"], _ACTIVE_MAINTENANCE_CACHE["titles"]

    try:
        with SessionLocal() as db:
            active_windows = (
                db.query(MaintenanceWindow)
                .filter(
                    MaintenanceWindow.is_active == 1,
                    MaintenanceWindow.status == "active",
                )
                .all()
            )
            count = len(active_windows)
            titles = [w.title for w in active_windows]
            _ACTIVE_MAINTENANCE_CACHE["count"] = count
            _ACTIVE_MAINTENANCE_CACHE["titles"] = titles
            _ACTIVE_MAINTENANCE_CACHE["updated_at"] = now_ts
            return count, titles
    except Exception:
        return _ACTIVE_MAINTENANCE_CACHE.get("count", 0), _ACTIVE_MAINTENANCE_CACHE.get("titles", [])


def _evaluate_maintenance_windows(db: Session, now: Optional[datetime] = None) -> None:
    """Evaluasi dan terapkan status jendela pemeliharaan terjadwal ke server klien."""
    now = now or datetime.utcnow()
    weekday_str = now.strftime("%a").lower()[:3]
    curr_hm = now.strftime("%H:%M")

    windows = (
        db.query(MaintenanceWindow)
        .filter(
            MaintenanceWindow.is_active == 1,
            MaintenanceWindow.status.in_(["scheduled", "active"]),
        )
        .all()
    )

    active_windows: list[MaintenanceWindow] = []

    for w in windows:
        if w.schedule_type == "once":
            if now < w.start_time:
                w.status = "scheduled"
            elif w.start_time <= now < w.end_time:
                w.status = "active"
                active_windows.append(w)
            else:
                w.status = "completed"
        elif w.schedule_type in ("daily", "weekly"):
            if now < w.start_time:
                w.status = "scheduled"
            elif w.end_time and now >= w.end_time:
                w.status = "completed"
            else:
                day_match = True
                if w.schedule_type == "weekly" and w.repeat_days:
                    allowed_days = [d.strip().lower() for d in w.repeat_days.split(",") if d.strip()]
                    if weekday_str not in allowed_days:
                        day_match = False

                if not day_match:
                    w.status = "scheduled"
                else:
                    if w.repeat_time_start and w.repeat_time_end:
                        if w.repeat_time_start <= w.repeat_time_end:
                            in_slot = w.repeat_time_start <= curr_hm < w.repeat_time_end
                        else:
                            in_slot = curr_hm >= w.repeat_time_start or curr_hm < w.repeat_time_end
                        if in_slot:
                            w.status = "active"
                            active_windows.append(w)
                        else:
                            w.status = "scheduled"
                    else:
                        w.status = "active"
                        active_windows.append(w)

    all_servers = db.query(Server).all()
    servers_by_id = {s.id: s for s in all_servers}
    covered_servers: dict[int, MaintenanceWindow] = {}

    for aw in active_windows:
        if aw.scope_type == "all":
            for s in all_servers:
                if s.id not in covered_servers:
                    covered_servers[s.id] = aw
        elif aw.scope_type == "group" and aw.server_group:
            for s in all_servers:
                if (s.group_name or "").strip().lower() == aw.server_group.strip().lower():
                    if s.id not in covered_servers:
                        covered_servers[s.id] = aw
        elif aw.scope_type == "server" and aw.server_id:
            if aw.server_id in servers_by_id and aw.server_id not in covered_servers:
                covered_servers[aw.server_id] = aw
        elif aw.scope_type in ("servers", "custom") and aw.server_ids:
            try:
                target_sids = [int(x.strip()) for x in aw.server_ids.split(",") if x.strip().isdigit()]
                for tsid in target_sids:
                    if tsid in servers_by_id and tsid not in covered_servers:
                        covered_servers[tsid] = aw
            except Exception:
                pass

    for sid, aw in covered_servers.items():
        s = servers_by_id.get(sid)
        if not s:
            continue
        tag_reason = f"[Jadwal: {aw.title}]"
        if not getattr(s, "is_maintenance", 0) or (
            s.maintenance_reason and s.maintenance_reason.startswith("[Jadwal:")
        ):
            s.is_maintenance = 1
            s.maintenance_reason = tag_reason
            s.maintenance_until = aw.end_time if aw.schedule_type == "once" else None

    for s in all_servers:
        if s.id not in covered_servers:
            if (
                getattr(s, "is_maintenance", 0)
                and s.maintenance_reason
                and s.maintenance_reason.startswith("[Jadwal:")
            ):
                s.is_maintenance = 0
                s.maintenance_reason = None
                s.maintenance_until = None

    try:
        db.commit()
    except Exception:
        db.rollback()

    _ACTIVE_MAINTENANCE_CACHE["count"] = len(active_windows)
    _ACTIVE_MAINTENANCE_CACHE["titles"] = [w.title for w in active_windows]
    _ACTIVE_MAINTENANCE_CACHE["updated_at"] = time.time()
