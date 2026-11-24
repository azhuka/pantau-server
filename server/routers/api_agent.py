import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Body
from sqlalchemy.orm import Session
from core.database import get_db
from core.utils import hash_api_key
from models.server import Server
from models.command import Command, LogRequest
from services.telemetry_service import process_telemetry_report

router = APIRouter(tags=["Agent API"])

def get_server_by_agent_key(x_api_key: str = Header(alias="X-Api-Key"), db: Session = Depends(get_db)) -> Server:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Header X-Api-Key is missing")
    hashed = hash_api_key(x_api_key)
    server = db.query(Server).filter((Server.api_key == hashed) | (Server.api_key == x_api_key)).first()
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

@router.get("/api/commands")
def api_commands_pending(
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db),
):
    """Agent mengambil antrean perintah yang berstatus 'pending'."""
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

    cmd.status = body.get("status", "executing")
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

    cmd.status = "executed" if body.get("status") == "success" else "failed"
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

@router.post("/api/logs/{req_id}/progress")
def api_log_progress(req_id: int, body: dict = Body(default={})):
    """Penerimaan stream progres log."""
    return {"ok": True}

@router.get("/api/logs/{req_id}/input")
def api_log_input(req_id: int):
    """Polling input interaktif untuk eksekusi log."""
    return {"ok": True, "input": None}

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
    x_api_key: str = Header(alias="X-Api-Key", default=""),
    db: Session = Depends(get_db)
):
    """Long-poll handler (5s) untuk penjelajahan file agar loop agen tenang dan tidak membanjiri I/O server."""
    await asyncio.sleep(5.0)
    return {"requests": []}

@router.post("/api/agent/file-requests/{req_id}/result")
def api_agent_file_result(
    req_id: str,
    body: dict = Body(...),
    server: Server = Depends(get_server_by_agent_key),
    db: Session = Depends(get_db)
):
    """Penerimaan hasil eksekusi operasi file agen."""
    return {"ok": True}

