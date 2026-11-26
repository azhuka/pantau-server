"""In-App Activity Console & Live Event Stream Service (SSE + 100-entry ring buffer)."""

import asyncio
from collections import deque
from datetime import datetime
import json
import re
import secrets
from typing import AsyncGenerator, Dict, List, Set

MAX_RING_BUFFER = 100
_ring_buffer: deque = deque(maxlen=MAX_RING_BUFFER)
_subscribers: Set[asyncio.Queue] = set()

REDACT_PATTERNS = [
    (re.compile(r"(password|pwd|secret|token|api_key|auth_key|bearer)\s*[:=]\s*([^\s,;]+)", re.IGNORECASE), r"\1=[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"pantau_session=[a-zA-Z0-9_\.-]+"), "pantau_session=[REDACTED]"),
]


def _redact_text(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    cleaned = text
    for pattern, repl in REDACT_PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    return cleaned


def broadcast_activity(
    level: str,
    module: str,
    host: str,
    message: str,
    details: str = "",
) -> None:
    """Broadcast a runtime event to active SSE subscribers and store in the ring buffer."""
    now = datetime.utcnow()
    item = {
        "id": secrets.token_hex(6),
        "time": now.strftime("%H:%M:%S"),
        "timestamp": now.isoformat(),
        "level": (level or "INFO").upper(),
        "module": (module or "SYSTEM").upper(),
        "host": host or "control-plane",
        "message": _redact_text(message),
        "details": _redact_text(details),
    }
    _ring_buffer.append(item)

    dead_queues = []
    for q in _subscribers:
        try:
            if q.qsize() >= 50:
                try:
                    q.get_nowait()
                except Exception:
                    pass
            q.put_nowait(item)
        except Exception:
            dead_queues.append(q)

    for dq in dead_queues:
        _subscribers.discard(dq)


def get_recent_activities(limit: int = 50) -> List[Dict]:
    """Return recent activity events from the in-memory ring buffer."""
    return list(_ring_buffer)[-limit:]


async def subscribe_activities() -> AsyncGenerator[str, None]:
    """Async SSE generator streaming live activity events with 15s keepalive pings."""
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.add(q)
    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {json.dumps(item)}\n\n"
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    finally:
        _subscribers.discard(q)
