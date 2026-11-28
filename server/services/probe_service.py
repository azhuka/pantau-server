"""Synthetic Probing Engine (HTTP/HTTPS, TCP, ICMP)."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import socket
import ssl
import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from models.probe import ProbeLog, ProbeTarget

logger = logging.getLogger("pantau.prober")


@dataclass
class ProbeResult:
    """Result of a single synthetic probe execution."""

    status: str  # 'up', 'down', 'degraded'
    latency_ms: Optional[float] = None
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    ssl_expires_at: Optional[datetime] = None
    ssl_days_remaining: Optional[int] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "latency_ms": round(self.latency_ms, 1) if self.latency_ms is not None else None,
            "status_code": self.status_code,
            "error_message": self.error_message,
            "ssl_expires_at": self.ssl_expires_at.isoformat() if self.ssl_expires_at else None,
            "ssl_days_remaining": self.ssl_days_remaining,
            "details": self.details,
        }


def parse_expected_status(spec: Optional[str]) -> list[tuple[int, int]]:
    """Parse expected HTTP status spec (e.g., '200', '200,201', '2xx', '200-299')."""
    if not spec or not spec.strip():
        return [(200, 299)]
    ranges: list[tuple[int, int]] = []
    for tok in [t.strip().lower() for t in spec.split(",") if t.strip()]:
        if tok.endswith("xx") and len(tok) == 3 and tok[0].isdigit():
            base = int(tok[0]) * 100
            ranges.append((base, base + 99))
        elif "-" in tok:
            parts = tok.split("-", 1)
            if parts[0].isdigit() and parts[1].isdigit():
                ranges.append((int(parts[0]), int(parts[1])))
        elif tok.isdigit():
            v = int(tok)
            ranges.append((v, v))
    return ranges or [(200, 299)]


def _status_matches(code: int, ranges: list[tuple[int, int]]) -> bool:
    return any(lo <= code <= hi for lo, hi in ranges)


def _check_ssl_expiry(hostname: str, port: int = 443, timeout: float = 5.0) -> tuple[Optional[datetime], Optional[int]]:
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(ssl.SSLSocket if False else __import__("socket").create_connection((hostname, port), timeout=timeout), server_hostname=hostname) as ssock:
            cert = ssock.getpeercert()
            not_after = cert.get("notAfter")
            if not_after:
                exp = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                days = (exp - datetime.utcnow()).days
                return exp, days
    except Exception:
        pass
    return None, None


def _validate_probe_host(host: str) -> Optional[str]:
    """Block SSRF against loopback, link-local/cloud metadata, multicast, and unspecified addresses."""
    import ipaddress

    clean = (host or "").strip().strip("[]").lower()
    if not clean:
        return "Target host is empty"
    if clean in ("localhost", "localhost.localdomain", "metadata.google.internal"):
        return f"Blocked probe target host: {clean}"
    try:
        infos = socket.getaddrinfo(clean, None)
    except socket.gaierror:
        return None
    for info in infos:
        addr_str = info[4][0].split("%")[0]
        try:
            ip = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            return f"Blocked probe target IP ({addr_str})"
    return None


async def execute_probe(probe_data: dict[str, Any]) -> ProbeResult:
    """Execute an HTTP/HTTPS, TCP, or ICMP probe asynchronously."""
    ptype = (probe_data.get("probe_type") or "http").lower()
    target = str(probe_data.get("target") or "").strip()
    timeout_s = max(1, min(30, int(probe_data.get("timeout_seconds") or 5)))
    latency_thresh = int(probe_data.get("latency_threshold_ms") or 1000)

    if not target:
        return ProbeResult(status="down", error_message="Target is empty")

    if ptype in ("http", "https"):
        url = target if target.startswith(("http://", "https://")) else f"{ptype}://{target}"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return ProbeResult(status="down", error_message="Invalid HTTP/HTTPS target URL")
        blocked = await asyncio.to_thread(_validate_probe_host, parsed.hostname)
        if blocked:
            return ProbeResult(status="down", error_message=blocked)
        method = (probe_data.get("http_method") or "GET").upper()
        ssl_verify = bool(probe_data.get("ssl_verify", True))
        expected_ranges = parse_expected_status(probe_data.get("expected_status"))
        keyword = (probe_data.get("keyword_match") or "").strip()

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(verify=ssl_verify, timeout=timeout_s, follow_redirects=False) as client:
                resp = await client.request(method, url)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if not _status_matches(resp.status_code, expected_ranges):
                return ProbeResult(
                    status="down",
                    latency_ms=latency_ms,
                    status_code=resp.status_code,
                    error_message=f"Unexpected HTTP status {resp.status_code}",
                )
            if keyword and keyword not in resp.text:
                return ProbeResult(
                    status="down",
                    latency_ms=latency_ms,
                    status_code=resp.status_code,
                    error_message=f"Keyword '{keyword}' not found in response",
                )
            ssl_exp, ssl_days = (None, None)
            if url.startswith("https://"):
                parsed = urlparse(url)
                if parsed.hostname:
                    ssl_exp, ssl_days = await asyncio.to_thread(
                        _check_ssl_expiry, parsed.hostname, parsed.port or 443, float(timeout_s)
                    )
            status = "degraded" if latency_ms > latency_thresh else "up"
            return ProbeResult(
                status=status,
                latency_ms=latency_ms,
                status_code=resp.status_code,
                ssl_expires_at=ssl_exp,
                ssl_days_remaining=ssl_days,
            )
        except httpx.TimeoutException:
            return ProbeResult(status="down", error_message=f"HTTP request timeout ({timeout_s}s)")
        except Exception as exc:
            return ProbeResult(status="down", error_message=str(exc)[:240])

    if ptype == "tcp":
        host = target
        port = probe_data.get("port")
        if not port and ":" in target:
            h, p_str = target.rsplit(":", 1)
            if p_str.isdigit():
                host, port = h, int(p_str)
        if not port:
            return ProbeResult(status="down", error_message="TCP port is required")
        blocked = await asyncio.to_thread(_validate_probe_host, host)
        if blocked:
            return ProbeResult(status="down", error_message=blocked)
        t0 = time.perf_counter()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=timeout_s)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            status = "degraded" if latency_ms > latency_thresh else "up"
            return ProbeResult(status=status, latency_ms=latency_ms)
        except asyncio.TimeoutError:
            return ProbeResult(status="down", error_message=f"TCP connection timeout ({timeout_s}s)")
        except Exception as exc:
            return ProbeResult(status="down", error_message=str(exc)[:240])

    if ptype == "icmp":
        host = urlparse(target).hostname or target
        blocked = await asyncio.to_thread(_validate_probe_host, host)
        if blocked:
            return ProbeResult(status="down", error_message=blocked)
        t0 = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", str(timeout_s), host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s + 2)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if proc.returncode != 0:
                err = (stderr or stdout).decode("utf-8", errors="ignore").strip().splitlines()
                return ProbeResult(status="down", error_message=(err[-1] if err else "ICMP host unreachable")[:240])
            status = "degraded" if latency_ms > latency_thresh else "up"
            return ProbeResult(status=status, latency_ms=latency_ms)
        except asyncio.TimeoutError:
            return ProbeResult(status="down", error_message=f"ICMP ping timeout ({timeout_s}s)")
        except Exception as exc:
            return ProbeResult(status="down", error_message=str(exc)[:240])

    return ProbeResult(status="down", error_message=f"Unsupported probe type: {ptype}")


def record_probe_execution(db: Session, probe_id: int, res: ProbeResult, checked_at: datetime) -> None:
    """Persist ProbeLog and update ProbeTarget state."""
    probe = db.query(ProbeTarget).filter(ProbeTarget.id == probe_id).first()
    if not probe:
        return

    log = ProbeLog(
        probe_id=probe_id,
        checked_at=checked_at,
        status=res.status,
        latency_ms=round(res.latency_ms, 1) if res.latency_ms is not None else None,
        status_code=res.status_code,
        error_message=res.error_message[:250] if res.error_message else None,
    )
    db.add(log)

    probe.last_checked_at = checked_at
    probe.last_latency_ms = round(res.latency_ms, 1) if res.latency_ms is not None else None
    probe.last_status_code = res.status_code
    probe.last_error = res.error_message[:250] if res.error_message else None
    if res.ssl_expires_at is not None:
        probe.ssl_expires_at = res.ssl_expires_at
        probe.ssl_days_remaining = res.ssl_days_remaining

    if res.status == "down":
        probe.consecutive_failures = (probe.consecutive_failures or 0) + 1
        probe.consecutive_successes = 0
        thresh = probe.consecutive_threshold or 1
        if probe.consecutive_failures >= thresh:
            probe.status = "down"
    else:
        probe.consecutive_successes = (probe.consecutive_successes or 0) + 1
        probe.consecutive_failures = 0
        probe.status = res.status
        from models.problem import ServerProblem
        open_probs = db.query(ServerProblem).filter(
            ServerProblem.key == f"probe_failed:{probe_id}",
            ServerProblem.resolved_at.is_(None),
        ).all()
        for op in open_probs:
            op.resolved_at = checked_at
            op.updated_at = checked_at
            op.resolved_note = "auto"

    since_24h = checked_at - timedelta(hours=24)
    recent_logs = db.query(ProbeLog.status).filter(ProbeLog.probe_id == probe_id, ProbeLog.checked_at >= since_24h).all()
    if recent_logs:
        ok_cnt = sum(1 for (st,) in recent_logs if st in ("up", "degraded"))
        probe.uptime_24h = round((ok_cnt / len(recent_logs)) * 100.0, 2)

    db.commit()


async def run_due_probes(db_factory) -> None:
    """Run all active probes whose interval has elapsed without blocking the event loop."""
    now = datetime.utcnow()

    def _load_due_items() -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        with db_factory() as db:
            active = db.query(ProbeTarget).filter(ProbeTarget.is_active == 1).all()
            for p in active:
                interval = max(10, int(p.interval_seconds or 60))
                if p.last_checked_at is None or (now - p.last_checked_at).total_seconds() >= interval:
                    items.append({
                        "id": p.id,
                        "probe_type": p.probe_type,
                        "target": p.target,
                        "port": p.port,
                        "timeout_seconds": p.timeout_seconds,
                        "http_method": p.http_method,
                        "expected_status": p.expected_status,
                        "keyword_match": p.keyword_match,
                        "ssl_verify": bool(p.ssl_verify),
                        "latency_threshold_ms": p.latency_threshold_ms,
                    })
        return items

    due_items = await asyncio.to_thread(_load_due_items)
    if not due_items:
        return

    sem = asyncio.Semaphore(10)

    def _save_probe_result(probe_id: int, res: ProbeResult) -> None:
        with db_factory() as db:
            record_probe_execution(db, probe_id, res, datetime.utcnow())

    async def _run_one(item: dict[str, Any]) -> None:
        async with sem:
            res = await execute_probe(item)
            await asyncio.to_thread(_save_probe_result, item["id"], res)

    await asyncio.gather(*[_run_one(i) for i in due_items], return_exceptions=True)
