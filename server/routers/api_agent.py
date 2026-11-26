import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Body
from fastapi.responses import PlainTextResponse
from sqlalchemy import desc, text
from sqlalchemy.orm import Session
from core.database import get_db
from core.utils import hash_api_key
from models.server import Server, ServerExtras
from models.user import User
from models.command import Command, LogRequest
from routers.auth import get_current_user
from services.telemetry_service import process_telemetry_report

VALID_UNIT_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,100}$")
_AGENT_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agent", "agent_pantau.py"))


def _get_latest_agent_meta() -> tuple[str, str, str]:
    if not os.path.isfile(_AGENT_FILE_PATH):
        return "", "", ""
    with open(_AGENT_FILE_PATH, "r", encoding="utf-8") as f:
        code = f.read()
    m = re.search(r'^AGENT_VERSION\s*=\s*"([^"]+)"', code, re.M)
    ver = m.group(1) if m else ""
    sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    return ver, sha, code


def _ver_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in str(v or "").strip().lstrip("v").split(".") if x.isdigit())
    except Exception:
        return (0,)

router = APIRouter(tags=["Agent API"])

def get_server_by_agent_key(x_api_key: str = Header(alias="X-Api-Key"), db: Session = Depends(get_db)) -> Server:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Header X-Api-Key is missing")
    hashed = hash_api_key(x_api_key)
    server = db.query(Server).filter(
        Server.is_active == 1,
        Server.api_key == hashed,
    ).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return server

@router.post("/api/report")
def agent_report(
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Menerima dan memproses paket telemetri dari agent_pantau."""
    # Ambil IP klien jika tidak disediakan dalam body
    client_host = request.client.host if request.client else "127.0.0.1"
    if not body.get("ip_address") or body.get("ip_address") == "127.0.0.1":
        body["ip_address"] = client_host

    res = process_telemetry_report(db, x_api_key, body)
    if not res.get("ok"):
        raise HTTPException(status_code=401, detail=res.get("error"))
    return {"ok": True}

@router.get("/api/agent/latest-code")
def api_agent_latest_code(server: Server = Depends(get_server_by_agent_key)):
    """Serve the latest verified agent_pantau.py source for OTA updates."""
    _, _, code = _get_latest_agent_meta()
    if not code:
        raise HTTPException(status_code=404, detail="Agent source not found")
    return PlainTextResponse(content=code, media_type="text/x-python")


@router.get("/api/commands")
def api_commands_pending(
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Agent mengambil antrean perintah yang berstatus 'pending'."""
    now = datetime.utcnow()
    # Auto-heal stuck executing update_agent commands older than 2 minutes
    stale_ota_cutoff = now - timedelta(minutes=2)
    db.query(Command).filter(
        Command.server_id == server.id,
        Command.action == "update_agent",
        Command.status == "executing",
        Command.created_at < stale_ota_cutoff,
    ).update({"status": "failed", "result": "OTA timeout (>2m)"}, synchronize_session=False)

    latest_ver, sha256, _ = _get_latest_agent_meta()
    if latest_ver and sha256:
        extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
        cur_ver = extras.agent_version if extras else None
        if cur_ver and _ver_tuple(cur_ver) < _ver_tuple(latest_ver):
            active_ota = db.query(Command).filter(
                Command.server_id == server.id,
                Command.action == "update_agent",
                Command.status.in_(["pending", "executing"]),
            ).first()
            if not active_ota:
                db.add(Command(
                    server_id=server.id,
                    action="update_agent",
                    params=json.dumps({"version": latest_ver, "sha256": sha256}),
                    status="pending",
                    issued_by="System",
                    created_at=now,
                ))
    db.commit()

    pending = (
        db.query(Command)
        .filter(Command.server_id == server.id, Command.status == "pending")
        .order_by(Command.id.asc())
        .all()
    )
    result = []
    for c in pending:
        params_obj = None
        if c.params:
            try:
                params_obj = json.loads(c.params)
            except Exception:
                params_obj = c.params
        result.append({
            "id": c.id,
            "action": c.action,
            "params": params_obj,
            "issued_by": c.issued_by
        })
    return {"ok": True, "commands": result}

@router.post("/api/commands/{cmd_id}/status")
def api_command_status(
    cmd_id: int,
    body: dict = Body(...),
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Agent menandai status eksekusi command (misal: 'executing')."""
    cmd = db.query(Command).filter(Command.id == cmd_id, Command.server_id == server.id).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    st = str(body.get("status") or "executing").strip().lower()
    cmd.status = "success" if st == "executed" else (st if st in ("pending", "executing", "success", "failed") else "executing")
    db.commit()
    return {"ok": True}

@router.post("/api/commands/{cmd_id}/result")
def api_command_result(
    cmd_id: int,
    body: dict = Body(...),
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Agent mengirim hasil eksekusi perintah."""
    cmd = db.query(Command).filter(Command.id == cmd_id, Command.server_id == server.id).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd.status = "success" if body.get("status") in ("success", "executed") else "failed"
    cmd.result = json.dumps(body.get("result", "")) if isinstance(body.get("result"), (dict, list)) else str(body.get("result", ""))
    cmd.executed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

@router.get("/api/logs/pending")
def api_logs_pending(
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Agent mengambil antrean permintaan log."""
    pending = (
        db.query(LogRequest)
        .filter(LogRequest.server_id == server.id, LogRequest.status == "pending")
        .order_by(LogRequest.id.asc())
        .all()
    )
    return {
        "ok": True,
        "requests": [
            {
                "id": req.id,
                "unit": req.unit,
                "lines": req.lines,
                "detail": req.detail,
            }
            for req in pending
        ]
    }

@router.post("/api/logs/{req_id}/status")
def api_log_status(
    req_id: int,
    body: dict = Body(...),
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Agent menandai permintaan log sedang dieksekusi."""
    req = db.query(LogRequest).filter(LogRequest.id == req_id, LogRequest.server_id == server.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")
    req.status = body.get("status", "executing")
    db.commit()
    return {"ok": True}

_APT_UNITS = {"APT_UPDATE", "APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE", "APT_FIX", "PKG_UPGRADE", "PKG_CLEAN"}
_SHELL_UNIT = "SHELL"
_INTERACTIVE_UNITS = _APT_UNITS | {_SHELL_UNIT}
_CLEAN_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_stream_output(raw: str, max_chars: int = 120000, max_lines: int = 1500) -> str:
    lines = (raw or "").splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    out = "\n".join(lines)
    return out[-max_chars:] if len(out) > max_chars else out


@router.post("/api/logs/{req_id}/progress")
def api_log_progress(
    req_id: int,
    body: dict = Body(default={}),
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Receive streaming output chunks from agent during long-running APT/log operations."""
    chunk = body.get("chunk")
    if chunk is None:
        raise HTTPException(status_code=400, detail="chunk is required")
    req = db.query(LogRequest).filter(LogRequest.id == req_id, LogRequest.server_id == server.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")
    if req.status != "executing":
        return {"ok": True, "ignored": True}

    new_result = str(chunk) if body.get("replace") else (req.result or "") + str(chunk)
    req.result = _clean_stream_output(new_result)
    req.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/api/logs/{req_id}/input")
def api_log_input_send(
    req_id: int,
    body: dict = Body(default={}),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Forward operator stdin input to an executing interactive APT or shell request."""
    req = db.query(LogRequest).filter(LogRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")
    if not user.can_access_server(req.server_id):
        raise HTTPException(status_code=403, detail="Access denied for this server")
    if req.unit == _SHELL_UNIT and not (user.is_master_admin or user.has_perm("can_terminal")):
        raise HTTPException(status_code=403, detail="Access denied: terminal permission required")
    if req.unit in _APT_UNITS and not (user.is_master_admin or user.has_perm("can_apt")):
        raise HTTPException(status_code=403, detail="Access denied: APT permission required")
    if req.status != "executing" or req.unit not in _INTERACTIVE_UNITS:
        raise HTTPException(status_code=409, detail="Process is not currently executing")

    raw = body.get("data")
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="data must be a string")

    if req.unit == _SHELL_UNIT:
        raw = "".join(ch for ch in raw if ch != "\x00" and not "\x80" <= ch <= "\x9f")[-4096:]
        if not raw:
            return {"ok": True}
        db.execute(
            text(
                "UPDATE log_requests SET input_queue = CONCAT(COALESCE(input_queue, ''), :chunk) "
                "WHERE id = :rid AND CHAR_LENGTH(COALESCE(input_queue, '')) + CHAR_LENGTH(:chunk) <= 4096"
            ),
            {"chunk": raw, "rid": req_id},
        )
    else:
        cleaned = _CLEAN_CTRL_RE.sub("", raw.replace("\r", "")).replace("\n", "").replace("\t", " ")[:200].strip()
        req.input_data = (cleaned + "\n") if cleaned else "\n"
    req.input_at = datetime.utcnow()
    req.updated_at = req.input_at
    db.commit()
    return {"ok": True}


@router.get("/api/logs/{req_id}/input")
def api_log_input(
    req_id: int,
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Pop pending interactive stdin input for the agent (consumes once)."""
    req = db.query(LogRequest).filter(LogRequest.id == req_id, LogRequest.server_id == server.id).first()
    if not req or req.status != "executing":
        return {"data": None}

    if req.unit == _SHELL_UNIT:
        row = db.execute(text("SELECT input_queue FROM log_requests WHERE id=:rid FOR UPDATE"), {"rid": req_id}).first()
        data = row[0] if row and row[0] else None
        if data:
            db.execute(text("UPDATE log_requests SET input_queue=NULL, input_at=NULL WHERE id=:rid"), {"rid": req_id})
            db.commit()
        return {"data": data}

    if not req.input_data:
        return {"data": None}
    data = req.input_data
    req.input_data = None
    req.input_at = None
    db.commit()
    return {"data": data}

@router.post("/api/logs/{req_id}/result")
def api_log_result(
    req_id: int,
    body: dict = Body(...),
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Agent mengirim hasil log (misal journalctl atau auth log)."""
    req = db.query(LogRequest).filter(LogRequest.id == req_id, LogRequest.server_id == server.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")

    req.status = "success" if body.get("status") == "success" else "failed"
    req.result = body.get("result", "")
    req.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

@router.get("/api/agent/file-requests")
async def api_agent_file_requests(
    server: Server = Depends(get_server_by_agent_key),
):
    """Long-poll handler (15s) delivering pending Remote File Manager RPC requests to the target agent."""
    from routers.files import file_dispatcher

    reqs = await file_dispatcher.pop_pending(server.id)
    if reqs:
        return {"requests": reqs}

    event = await file_dispatcher.get_or_create_event(server.id)
    try:
        await asyncio.wait_for(event.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        pass

    reqs = await file_dispatcher.pop_pending(server.id)
    return {"requests": reqs}


@router.post("/api/agent/file-requests/{req_id}/result")
def api_agent_file_result(
    req_id: str,
    body: dict = Body(...),
    server: Server = Depends(get_server_by_agent_key),
):
    """Receive execution result of a Remote File Manager RPC operation from the target agent."""
    from routers.files import file_dispatcher

    ok = file_dispatcher.resolve(req_id, body)
    return {"ok": ok}


@router.post("/api/logs/request")
def api_logs_request_create(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create on-demand log retrieval request for target server agent."""
    try:
        sid = int(body.get("server_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid server_id")

    unit = str(body.get("unit") or "").strip()[:100]
    try:
        lines = max(10, min(int(body.get("lines") or 200), 2000))
    except (TypeError, ValueError):
        lines = 200

    if not VALID_UNIT_RE.match(unit):
        raise HTTPException(status_code=400, detail="Invalid log unit identifier")

    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Access denied for this asset")
    if not (user.is_master_admin or user.has_perm("can_audit") or user.has_perm("can_services")):
        raise HTTPException(status_code=403, detail="Permission can_audit or can_services is required")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    if not server.last_seen or (now - server.last_seen).total_seconds() > 60:
        raise HTTPException(status_code=409, detail="Asset is offline; on-demand log polling is unavailable")

    # Expire stale pending requests older than 2 minutes
    stale_cutoff = now - timedelta(minutes=2)
    db.query(LogRequest).filter(
        LogRequest.server_id == sid,
        LogRequest.status.in_(["pending", "executing"]),
        LogRequest.created_at < stale_cutoff,
    ).update({"status": "failed", "result": "[timeout]"}, synchronize_session=False)

    logreq = LogRequest(server_id=sid, unit=unit, lines=lines, status="pending")
    db.add(logreq)
    db.commit()
    db.refresh(logreq)

    # Cap completed log requests to latest 100 rows per server
    old_done = (
        db.query(LogRequest)
        .filter(LogRequest.server_id == sid, LogRequest.status.in_(["success", "failed"]))
        .order_by(desc(LogRequest.id))
        .offset(100)
        .all()
    )
    for row in old_done:
        db.delete(row)
    if old_done:
        db.commit()

    return {"ok": True, "id": logreq.id}


@router.get("/api/logs/request/{rid}")
def api_logs_request_poll(
    rid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Poll status and raw log payload of a LogRequest."""
    logreq = db.query(LogRequest).filter(LogRequest.id == rid).first()
    if not logreq:
        raise HTTPException(status_code=404, detail="Log request not found")
    if not user.can_access_server(logreq.server_id):
        raise HTTPException(status_code=403, detail="Access denied for this asset")
    if not (user.is_master_admin or user.has_perm("can_audit") or user.has_perm("can_services")):
        raise HTTPException(status_code=403, detail="Permission required")
    return {"ok": True, "id": logreq.id, "status": logreq.status, "result": logreq.result}

