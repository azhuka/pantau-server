"""Modul Synthetic HTTP & ICMP Probing (Prober Engine & Scheduler) untuk Pantau Server.

Mendukung pemantauan proaktif dan agentless dari server pusat:
- HTTP / HTTPS (Status Code, Latency, Keyword Match, SSL Certificate Expiration)
- ICMP Ping (Packet Loss %, RTT Min/Avg/Max)
- TCP Port Handshake (Port Health & Handshake Latency)
- Anti-Flapping / Consecutive Thresholding
- Auto-Remediation / Auto-Resolve Insiden pada ServerProblem
- Penghitungan Rolling SLA Uptime 24 Jam & 30 Hari
- Eksekusi Asinkron dengan Concurrency Limiter
"""

import asyncio
import datetime
import json
import logging
import re
import socket
import ssl
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session

try:
    from models import ProbeLog, ProbeTarget, Server, ServerProblem
except ImportError:
    from server.models import ProbeLog, ProbeTarget, Server, ServerProblem

logger = logging.getLogger("pantau.prober")

DEFAULT_USER_AGENT = "Pantau-Prober/1.0 (+https://pantau.internal)"
MAX_CONCURRENT_PROBES = 15
PROBE_TICK_INTERVAL_SECS = 5
PROBE_LOG_RETENTION_DAYS = 30


@dataclass
class ProbeResult:
    """Hasil eksekusi satu pengujian probe."""

    status: str  # 'up', 'down', 'degraded'
    latency_ms: Optional[float] = None
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    ssl_expires_at: Optional[datetime.datetime] = None
    ssl_days_remaining: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "latency_ms": round(self.latency_ms, 1) if self.latency_ms is not None else None,
            "status_code": self.status_code,
            "error_message": self.error_message,
            "ssl_expires_at": self.ssl_expires_at.isoformat() if self.ssl_expires_at else None,
            "ssl_days_remaining": self.ssl_days_remaining,
            "details": self.details,
        }


def parse_expected_status(spec: Optional[str]) -> List[Tuple[int, int]]:
    """Urai spesifikasi kode status yang diharapkan (misal: '200', '200,201,204', '2xx', '200-299')."""
    if not spec or not spec.strip():
        return [(200, 200)]

    ranges = []
    tokens = [t.strip().lower() for t in spec.split(",") if t.strip()]
    for tok in tokens:
        if tok.endswith("xx") and len(tok) == 3 and tok[0].isdigit():
            base = int(tok[0]) * 100
            ranges.append((base, base + 99))
        elif "-" in tok:
            parts = tok.split("-", 1)
            try:
                lo, hi = int(parts[0].strip()), int(parts[1].strip())
                ranges.append((min(lo, hi), max(lo, hi)))
            except ValueError:
                pass
        elif tok.isdigit():
            val = int(tok)
            ranges.append((val, val))
    return ranges or [(200, 200)]


def is_status_code_match(code: int, expected_ranges: List[Tuple[int, int]]) -> bool:
    """Cek apakah HTTP status code berada dalam salah satu rentang yang diharapkan."""
    for lo, hi in expected_ranges:
        if lo <= code <= hi:
            return True
    return False


def inspect_remote_ssl_certificate(
    host: str, port: int = 443, timeout: float = 5.0
) -> Tuple[Optional[datetime.datetime], Optional[int], Optional[str]]:
    """Periksa tanggal kedaluwarsa sertifikat SSL/TLS remote menggunakan ssl socket standar."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # agar tetap bisa baca expire date walau cert internal/self-signed
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    # Bila CERT_NONE mengembalikan dict kosong pada beberapa distro, coba CERT_OPTIONAL
                    try:
                        ctx_opt = ssl.create_default_context()
                        with socket.create_connection((host, port), timeout=timeout) as sock2:
                            with ctx_opt.wrap_socket(sock2, server_hostname=host) as ssock2:
                                cert = ssock2.getpeercert()
                    except Exception:
                        pass
                if cert and "notAfter" in cert:
                    not_after_str = cert["notAfter"]
                    # Format baku: 'May 10 12:00:00 2026 GMT'
                    expire_dt = datetime.datetime.strptime(
                        not_after_str, "%b %d %H:%M:%S %Y %Z"
                    ).replace(tzinfo=datetime.timezone.utc)
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    days_remaining = (expire_dt - now_utc).days
                    return expire_dt.replace(tzinfo=None), days_remaining, None
        return None, None, None
    except Exception as exc:
        return None, None, str(exc)


async def probe_http(
    target_url: str,
    method: str = "GET",
    headers_dict: Optional[Dict[str, str]] = None,
    body_data: Optional[str] = None,
    expected_status_spec: str = "200",
    keyword_match: Optional[str] = None,
    ssl_verify: bool = True,
    timeout_seconds: float = 5.0,
    latency_threshold_ms: float = 2000.0,
    ssl_expiry_threshold_days: int = 14,
) -> ProbeResult:
    """Eksekusi HTTP/HTTPS synthetic probe."""
    url = target_url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "http://" + url

    parsed = urlparse(url)
    is_https = parsed.scheme == "https"
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if is_https else 80)

    # Siapkan headers
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
    if headers_dict:
        req_headers.update(headers_dict)

    expected_ranges = parse_expected_status(expected_status_spec)

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            verify=ssl_verify,
            timeout=timeout_seconds,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        ) as client:
            resp = await client.request(
                method=method.upper(),
                url=url,
                headers=req_headers,
                content=body_data if body_data else None,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            status_code = resp.status_code

            # Periksa SSL Expiry jika HTTPS
            ssl_expires_at = None
            ssl_days_remaining = None
            if is_https:
                exp_dt, days_left, _ = await asyncio.to_thread(
                    inspect_remote_ssl_certificate, host, port, min(timeout_seconds, 4.0)
                )
                ssl_expires_at = exp_dt
                ssl_days_remaining = days_left

            # 1. Validasi Kode Status
            if not is_status_code_match(status_code, expected_ranges):
                return ProbeResult(
                    status="down",
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error_message=f"HTTP {status_code} (diharapkan: {expected_status_spec})",
                    ssl_expires_at=ssl_expires_at,
                    ssl_days_remaining=ssl_days_remaining,
                    details={"response_headers": dict(resp.headers), "url": str(resp.url)},
                )

            # 2. Validasi Keyword Match (Abaikan jika kosong atau string literal 'None')
            if keyword_match is not None:
                kw = str(keyword_match).strip()
                if kw and kw != "None" and kw.lower() != "none":
                    if kw not in resp.text:
                        return ProbeResult(
                            status="down",
                            latency_ms=latency_ms,
                            status_code=status_code,
                            error_message=f"Kata kunci '{kw}' tidak ditemukan dalam respons",
                            ssl_expires_at=ssl_expires_at,
                            ssl_days_remaining=ssl_days_remaining,
                            details={"body_snippet": resp.text[:200]},
                        )

            # 3. Validasi Kadaluarsa SSL
            if is_https and ssl_days_remaining is not None:
                if ssl_days_remaining < 0:
                    return ProbeResult(
                        status="down",
                        latency_ms=latency_ms,
                        status_code=status_code,
                        error_message=f"Sertifikat SSL kedaluwarsa ({abs(ssl_days_remaining)} hari lalu)",
                        ssl_expires_at=ssl_expires_at,
                        ssl_days_remaining=ssl_days_remaining,
                    )
                elif ssl_days_remaining <= ssl_expiry_threshold_days:
                    return ProbeResult(
                        status="degraded",
                        latency_ms=latency_ms,
                        status_code=status_code,
                        error_message=f"Sertifikat SSL segera habis (sisa {ssl_days_remaining} hari)",
                        ssl_expires_at=ssl_expires_at,
                        ssl_days_remaining=ssl_days_remaining,
                    )

            # 4. Validasi Latensi Tinggi (Degraded)
            if latency_threshold_ms and latency_ms > latency_threshold_ms:
                return ProbeResult(
                    status="degraded",
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error_message=f"Latensi tinggi ({latency_ms:.1f}ms > {latency_threshold_ms:.0f}ms)",
                    ssl_expires_at=ssl_expires_at,
                    ssl_days_remaining=ssl_days_remaining,
                )

            # Sukses Penuh
            return ProbeResult(
                status="up",
                latency_ms=latency_ms,
                status_code=status_code,
                error_message=None,
                ssl_expires_at=ssl_expires_at,
                ssl_days_remaining=ssl_days_remaining,
                details={"url": str(resp.url), "bytes": len(resp.content)},
            )

    except httpx.ConnectTimeout:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            status="down",
            latency_ms=latency_ms,
            error_message=f"Timeout saat koneksi ke {host}:{port} ({timeout_seconds:.0f}s)",
        )
    except httpx.ReadTimeout:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            status="down",
            latency_ms=latency_ms,
            error_message=f"Timeout membaca respons ({timeout_seconds:.0f}s)",
        )
    except ssl.SSLError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            status="down",
            latency_ms=latency_ms,
            error_message=f"Kegagalan SSL/TLS Handshake: {exc}",
        )
    except httpx.ConnectError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            status="down",
            latency_ms=latency_ms,
            error_message=f"Gagal terhubung (Connection Refused / Host Unreachable)",
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            status="down",
            latency_ms=latency_ms,
            error_message=f"Galat HTTP: {str(exc)[:120]}",
        )


async def probe_icmp(
    target_host: str,
    timeout_seconds: float = 5.0,
    packet_count: int = 3,
    latency_threshold_ms: float = 2000.0,
) -> ProbeResult:
    """Eksekusi ICMP Ping probe via /usr/bin/ping secara non-blocking."""
    host = target_host.strip()
    # Hapus scheme atau port jika dimasukkan pengguna tidak sengaja
    if "://" in host:
        host = urlparse(host).hostname or host
    if ":" in host and not host.count(":") > 1:  # bukan IPv6
        host = host.split(":", 1)[0]

    # Validasi sanitasi host untuk keamanan command execution
    if not re.match(r"^[a-zA-Z0-9.\-_:]+$", host):
        return ProbeResult(
            status="down",
            error_message=f"Format host tidak valid: '{host}'",
        )

    t0 = time.perf_counter()
    w_secs = max(1, int(timeout_seconds))
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/ping",
            "-c",
            str(packet_count),
            "-W",
            str(w_secs),
            host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_seconds + 3.0
        )
        latency_total = (time.perf_counter() - t0) * 1000.0
        out = stdout_bytes.decode("utf-8", errors="ignore")
        err = stderr_bytes.decode("utf-8", errors="ignore")

        # Parsing packet loss %
        loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet\s+loss", out)
        packet_loss = float(loss_match.group(1)) if loss_match else 100.0

        # Parsing RTT: min/avg/max/mdev = 0.014/0.017/0.023/0.004 ms
        rtt_match = re.search(
            r"rtt\s+min/avg/max/mdev\s*=\s*([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+)\s*ms",
            out,
        )
        avg_rtt = float(rtt_match.group(2)) if rtt_match else None

        if packet_loss >= 100.0 or proc.returncode != 0 and avg_rtt is None:
            return ProbeResult(
                status="down",
                latency_ms=None,
                error_message=f"Host tidak merespons (100% packet loss)",
                details={"packet_loss_pct": 100.0, "raw_output": out[:200]},
            )

        # Jika ada packet loss > 0%
        if packet_loss > 0.0:
            return ProbeResult(
                status="degraded",
                latency_ms=avg_rtt or latency_total,
                error_message=f"Packet loss terdeteksi: {packet_loss:.0f}% (RTT {avg_rtt or 0:.1f}ms)",
                details={"packet_loss_pct": packet_loss, "rtt_avg": avg_rtt},
            )

        # Jika latensi melebihi ambang batas
        if latency_threshold_ms and avg_rtt and avg_rtt > latency_threshold_ms:
            return ProbeResult(
                status="degraded",
                latency_ms=avg_rtt,
                error_message=f"Latensi ICMP tinggi ({avg_rtt:.1f}ms > {latency_threshold_ms:.0f}ms)",
                details={"packet_loss_pct": 0.0, "rtt_avg": avg_rtt},
            )

        # Sukses Penuh
        return ProbeResult(
            status="up",
            latency_ms=avg_rtt if avg_rtt is not None else latency_total,
            error_message=None,
            details={"packet_loss_pct": 0.0, "rtt_avg": avg_rtt},
        )

    except asyncio.TimeoutError:
        return ProbeResult(
            status="down",
            error_message=f"Ping timeout setelah {timeout_seconds:.0f} detik",
        )
    except Exception as exc:
        return ProbeResult(
            status="down",
            error_message=f"Galat ICMP: {str(exc)[:120]}",
        )


async def probe_tcp(
    target_host: str,
    port: int,
    timeout_seconds: float = 5.0,
    latency_threshold_ms: float = 2000.0,
) -> ProbeResult:
    """Eksekusi TCP Handshake probe (apakah port terbuka dan merespons)."""
    host = target_host.strip()
    if "://" in host:
        host = urlparse(host).hostname or host

    if not port or port < 1 or port > 65535:
        return ProbeResult(
            status="down",
            error_message=f"Nomor port TCP tidak valid: {port}",
        )

    t0 = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout_seconds
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

        if latency_threshold_ms and latency_ms > latency_threshold_ms:
            return ProbeResult(
                status="degraded",
                latency_ms=latency_ms,
                error_message=f"Handshake TCP lambat ({latency_ms:.1f}ms > {latency_threshold_ms:.0f}ms)",
            )

        return ProbeResult(
            status="up",
            latency_ms=latency_ms,
            error_message=None,
            details={"port": port, "host": host},
        )

    except asyncio.TimeoutError:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            status="down",
            latency_ms=latency_ms,
            error_message=f"Timeout ({timeout_seconds:.0f}s) ke {host}:{port}",
        )
    except ConnectionRefusedError:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            status="down",
            latency_ms=latency_ms,
            error_message=f"Koneksi ditolak (port {port} tertutup)",
        )
    except socket.gaierror as exc:
        return ProbeResult(
            status="down",
            error_message=f"Gagal resolusi nama domain '{host}': {exc}",
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            status="down",
            latency_ms=latency_ms,
            error_message=f"Galat TCP: {str(exc)[:120]}",
        )


async def execute_probe(probe_data: Dict[str, Any]) -> ProbeResult:
    """Router eksekusi probe berdasarkan tipe probe ('http', 'https', 'ping', 'tcp')."""
    ptype = (probe_data.get("probe_type") or "http").lower()
    target = probe_data.get("target") or ""
    port = probe_data.get("port")
    timeout = float(probe_data.get("timeout_seconds") or 5.0)
    lat_thresh = float(probe_data.get("latency_threshold_ms") or 2000.0)

    if ptype in ("http", "https"):
        method = probe_data.get("http_method") or "GET"
        raw_headers = probe_data.get("http_headers")
        headers_dict = None
        if raw_headers:
            if isinstance(raw_headers, str):
                try:
                    headers_dict = json.loads(raw_headers)
                except Exception:
                    pass
            elif isinstance(raw_headers, dict):
                headers_dict = raw_headers

        body = probe_data.get("http_body")
        expected_status = probe_data.get("expected_status") or "200"
        raw_kw = probe_data.get("keyword_match")
        keyword = str(raw_kw).strip() if (raw_kw is not None and str(raw_kw).strip() and str(raw_kw).strip().lower() != "none") else None
        ssl_verify = bool(probe_data.get("ssl_verify", 1))
        ssl_days_thresh = int(probe_data.get("ssl_expiry_threshold_days") or 14)

        return await probe_http(
            target_url=target,
            method=method,
            headers_dict=headers_dict,
            body_data=body,
            expected_status_spec=expected_status,
            keyword_match=keyword,
            ssl_verify=ssl_verify,
            timeout_seconds=timeout,
            latency_threshold_ms=lat_thresh,
            ssl_expiry_threshold_days=ssl_days_thresh,
        )

    elif ptype == "ping":
        return await probe_icmp(
            target_host=target,
            timeout_seconds=timeout,
            packet_count=3,
            latency_threshold_ms=lat_thresh,
        )

    elif ptype == "tcp":
        port_num = int(port or 80)
        return await probe_tcp(
            target_host=target,
            port=port_num,
            timeout_seconds=timeout,
            latency_threshold_ms=lat_thresh,
        )

    return ProbeResult(
        status="down",
        error_message=f"Tipe probe tidak didukung: '{ptype}'",
    )


def sync_probe_incident(
    db: Session,
    probe: ProbeTarget,
    result: ProbeResult,
    now: datetime.datetime,
) -> None:
    """Sinkronisasi insiden ServerProblem dengan status probe target."""
    prob_key = f"probe_failed:{probe.id}"

    # Cari insiden terbuka yang berkaitan dengan probe ini
    open_prob = (
        db.query(ServerProblem)
        .filter(
            ServerProblem.probe_id == probe.id,
            ServerProblem.key == prob_key,
            ServerProblem.resolved_at.is_(None),
        )
        .first()
    )

    if result.status in ("down", "degraded"):
        sev = "danger" if result.status == "down" else "warning"
        status_word = "GAGAL" if result.status == "down" else "TERGANGGU"
        err_msg = result.error_message or "Endpoint tidak merespons"
        msg = f"Probe {probe.name} ({probe.target}) {status_word}: {err_msg}"
        tip = (
            f"Periksa status endpoint '{probe.target}'. Uji manual via menu Probing atau periksa "
            f"jaringan firewall menuju target. Dipantau oleh Synthetic Prober pusat."
        )

        ctx_dict = {
            "probe_id": probe.id,
            "probe_name": probe.name,
            "probe_type": probe.probe_type,
            "target": probe.target,
            "port": probe.port,
            "status": result.status,
            "latency_ms": round(result.latency_ms, 1) if result.latency_ms else None,
            "status_code": result.status_code,
            "error": result.error_message,
            "ssl_days_remaining": result.ssl_days_remaining,
            "checked_at": now.isoformat(),
        }
        ctx_str = json.dumps(ctx_dict, ensure_ascii=False)

        if open_prob:
            open_prob.severity = sev
            open_prob.message = msg[:255]
            open_prob.tip = tip[:500]
            open_prob.last_active_at = now
            open_prob.updated_at = now
            open_prob.context = ctx_str
        else:
            new_p = ServerProblem(
                server_id=probe.server_id,
                probe_id=probe.id,
                key=prob_key,
                severity=sev,
                message=msg[:255],
                tip=tip[:500],
                started_at=now,
                updated_at=now,
                last_active_at=now,
                context=ctx_str,
            )
            db.add(new_p)

    elif result.status == "up" and open_prob:
        # Pemulihan otomatis saat probe kembali sehat
        open_prob.resolved_at = now
        open_prob.updated_at = now
        open_prob.resolved_note = "auto"


def calculate_rolling_uptime(db: Session, probe_id: int) -> Tuple[float, float]:
    """Hitung persentase SLA uptime rolling 24 jam dan 30 hari dari probe_logs."""
    now = datetime.datetime.utcnow()
    cutoff_24h = now - datetime.timedelta(hours=24)
    cutoff_30d = now - datetime.timedelta(days=30)

    # 24 Jam
    stats_24h = (
        db.query(
            func.count(ProbeLog.id).label("total"),
            func.sum(func.if_(ProbeLog.status.in_(["up", "degraded"]), 1, 0)).label("up_cnt"),
        )
        .filter(ProbeLog.probe_id == probe_id, ProbeLog.checked_at >= cutoff_24h)
        .first()
    )
    tot_24 = stats_24h.total or 0
    up_24 = stats_24h.up_cnt or 0
    uptime_24h = round((up_24 / tot_24) * 100.0, 2) if tot_24 > 0 else 100.0

    # 30 Hari
    stats_30d = (
        db.query(
            func.count(ProbeLog.id).label("total"),
            func.sum(func.if_(ProbeLog.status.in_(["up", "degraded"]), 1, 0)).label("up_cnt"),
        )
        .filter(ProbeLog.probe_id == probe_id, ProbeLog.checked_at >= cutoff_30d)
        .first()
    )
    tot_30 = stats_30d.total or 0
    up_30 = stats_30d.up_cnt or 0
    uptime_30d = round((up_30 / tot_30) * 100.0, 2) if tot_30 > 0 else 100.0

    return uptime_24h, uptime_30d


def record_probe_execution(
    db: Session, probe_id: int, result: ProbeResult, now: Optional[datetime.datetime] = None
) -> ProbeTarget:
    """Simpan hasil eksekusi probe ke tabel probe_targets & probe_logs serta kelola anti-flapping."""
    if now is None:
        now = datetime.datetime.utcnow()

    probe = db.query(ProbeTarget).filter(ProbeTarget.id == probe_id).first()
    if not probe:
        raise ValueError(f"Probe ID {probe_id} tidak ditemukan")

    # 1. Catat ke ProbeLog (Time-series)
    log_entry = ProbeLog(
        probe_id=probe.id,
        checked_at=now,
        status=result.status,
        latency_ms=result.latency_ms,
        status_code=result.status_code,
        error_message=result.error_message[:255] if result.error_message else None,
    )
    db.add(log_entry)

    # 2. Logika Anti-Flapping / Consecutive Threshold
    consec_thresh = max(1, getattr(probe, "consecutive_threshold", 2) or 2)
    if result.status in ("down", "degraded"):
        probe.consecutive_failures = (probe.consecutive_failures or 0) + 1
        probe.consecutive_successes = 0

        # Hanya ubah status operasional ke DOWN/DEGRADED dan picu alarm bila sudah melebihi ambang batas
        if probe.consecutive_failures >= consec_thresh:
            probe.status = result.status
            sync_probe_incident(db, probe, result, now)
    else:
        # Status UP
        probe.consecutive_successes = (probe.consecutive_successes or 0) + 1
        probe.consecutive_failures = 0
        probe.status = "up"
        sync_probe_incident(db, probe, result, now)

    # 3. Perbarui metrik telemetri terkini pada ProbeTarget
    probe.last_checked_at = now
    probe.last_latency_ms = result.latency_ms
    probe.last_status_code = result.status_code
    probe.last_error = result.error_message[:255] if result.error_message else None

    if result.ssl_expires_at is not None:
        probe.ssl_expires_at = result.ssl_expires_at
    if result.ssl_days_remaining is not None:
        probe.ssl_days_remaining = result.ssl_days_remaining

    # 4. Hitung rolling uptime SLA
    try:
        up_24, up_30 = calculate_rolling_uptime(db, probe.id)
        probe.uptime_24h = up_24
        probe.uptime_30d = up_30
    except Exception as exc:
        logger.debug("Hitung SLA gagal sementara: %s", exc)

    db.commit()
    return probe


class ProbeScheduler:
    """Scheduler background otonom untuk menjalankan probe berkala."""

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_prune = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="synthetic-prober", daemon=True
        )
        self._thread.start()
        logger.info("[prober] Synthetic Probing Engine aktif (interval %ds)", PROBE_TICK_INTERVAL_SECS)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            logger.info("[prober] Synthetic Probing Engine dihentikan")

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._worker_loop())
        finally:
            self._loop.close()

    async def _worker_loop(self) -> None:
        sem = asyncio.Semaphore(MAX_CONCURRENT_PROBES)

        while not self._stop_event.is_set():
            try:
                # 1. Bersihkan log tua tiap 1 jam
                now_mono = time.monotonic()
                if now_mono - self._last_prune > 3600:
                    self._last_prune = now_mono
                    self._prune_old_logs()

                # 2. Ambil daftar probe yang waktunya dieksekusi
                due_probes = self._fetch_due_probes()
                if due_probes:
                    tasks = [self._execute_single_probe_guarded(sem, p_data) for p_data in due_probes]
                    await asyncio.gather(*tasks, return_exceptions=True)

            except Exception as exc:
                logger.error("[prober] Galat pada siklus pengecekan: %s", exc)

            # Tunggu interval siklus
            for _ in range(PROBE_TICK_INTERVAL_SECS * 2):
                if self._stop_event.is_set():
                    break
                await asyncio.sleep(0.5)

    def _fetch_due_probes(self) -> List[Dict[str, Any]]:
        """Ambil probe aktif yang perlu dieksekusi dari database."""
        now_utc = datetime.datetime.utcnow()
        due = []
        with self.session_factory() as db:
            try:
                active_probes = (
                    db.query(ProbeTarget)
                    .filter(ProbeTarget.is_active == 1)
                    .all()
                )
                for p in active_probes:
                    interval = max(10, p.interval_seconds or 60)
                    if p.last_checked_at is None:
                        is_due = True
                    else:
                        elapsed = (now_utc - p.last_checked_at).total_seconds()
                        is_due = elapsed >= interval

                    if is_due:
                        due.append({
                            "id": p.id,
                            "probe_type": p.probe_type,
                            "target": p.target,
                            "port": p.port,
                            "timeout_seconds": p.timeout_seconds,
                            "latency_threshold_ms": p.latency_threshold_ms,
                            "http_method": p.http_method,
                            "http_headers": p.http_headers,
                            "http_body": p.http_body,
                            "expected_status": p.expected_status,
                            "keyword_match": p.keyword_match,
                            "ssl_verify": p.ssl_verify,
                            "ssl_expiry_threshold_days": p.ssl_expiry_threshold_days,
                        })
            except Exception as exc:
                logger.warning("[prober] Gagal query probe jatuh tempo: %s", exc)
        return due

    async def _execute_single_probe_guarded(
        self, sem: asyncio.Semaphore, p_data: Dict[str, Any]
    ) -> None:
        """Eksekusi probe dengan batasan semafor konkurensi."""
        async with sem:
            probe_id = p_data["id"]
            try:
                result = await execute_probe(p_data)
                now = datetime.datetime.utcnow()

                # Tulis hasil ke database di thread pool sinkron
                await asyncio.to_thread(self._persist_result, probe_id, result, now)
            except Exception as exc:
                logger.warning("[prober] Gagal eksekusi probe ID %d: %s", probe_id, exc)

    def _persist_result(
        self, probe_id: int, result: ProbeResult, now: datetime.datetime
    ) -> None:
        with self.session_factory() as db:
            try:
                record_probe_execution(db, probe_id, result, now)
            except Exception as exc:
                db.rollback()
                logger.error("[prober] Gagal simpan hasil probe ID %d: %s", probe_id, exc)

    def _prune_old_logs(self) -> None:
        """Pangkas catatan probe_logs yang lebih tua dari retensi (30 hari)."""
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=PROBE_LOG_RETENTION_DAYS)
        with self.session_factory() as db:
            try:
                deleted = (
                    db.query(ProbeLog)
                    .filter(ProbeLog.checked_at < cutoff)
                    .delete(synchronize_session=False)
                )
                db.commit()
                if deleted:
                    logger.info("[prober] Pembersihan retensi: %d catatan probe lama dihapus", deleted)
            except Exception as exc:
                db.rollback()
                logger.warning("[prober] Gagal pangkas log probe lama: %s", exc)
