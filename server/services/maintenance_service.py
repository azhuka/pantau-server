"""Scheduled Maintenance Windows evaluation service."""

from datetime import datetime
import json
from typing import Optional
from sqlalchemy.orm import Session

from models.misc import MaintenanceWindow
from models.server import Server


def _window_matches_server(w: MaintenanceWindow, srv: Server) -> bool:
    if w.scope_type == "all":
        return True
    if w.scope_type == "single":
        return w.server_id == srv.id
    if w.scope_type == "group":
        return bool(w.server_group and srv.group_name == w.server_group)
    if w.scope_type == "multi" and w.server_ids:
        try:
            ids = json.loads(w.server_ids)
            return srv.id in [int(x) for x in ids]
        except Exception:
            return False
    return False


def evaluate_maintenance_windows(db: Session, now: Optional[datetime] = None) -> None:
    """Evaluate active/scheduled maintenance windows and update window statuses."""
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
                    days = [d.strip().lower()[:3] for d in w.repeat_days.split(",") if d.strip()]
                    day_match = weekday_str in days
                t_start = w.repeat_time_start or "00:00"
                t_end = w.repeat_time_end or "23:59"
                time_match = (t_start <= curr_hm < t_end) if t_start <= t_end else (curr_hm >= t_start or curr_hm < t_end)
                if day_match and time_match:
                    w.status = "active"
                    active_windows.append(w)
                else:
                    w.status = "scheduled"

    if active_windows:
        servers = db.query(Server).filter(Server.is_active == 1).all()
        for srv in servers:
            for w in active_windows:
                if _window_matches_server(w, srv):
                    if not srv.is_maintenance:
                        srv.is_maintenance = 1
                        srv.maintenance_reason = f"Scheduled: {w.title}"
                        srv.maintenance_until = w.end_time
                    break

    db.commit()
