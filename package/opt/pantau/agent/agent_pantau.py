#!/usr/bin/env python3
"""
Agen Pantau v3.5 - Server Monitoring Agent (Production Package)
================================================================
- Auto-detect semua layanan listening (via sudo ss bila non-root)
- Health check dalam: HTTP response time, TCP response time
- Kinerja hardware/jaringan per siklus: CPU, load, memori, swap,
  disk, uptime, serta statistik interface (RX/TX + rate)
- Daftar akun user (login + sesi aktif) & unit layanan aktif
- Lapor ke Dashboard Pantau tiap interval
- Polling command dari Dashboard (restart/start/stop) dan eksekusi
  lewat wrapper /usr/local/sbin/pantau-restart (divalidasi + deny-list)
- Polling permintaan log layanan (journalctl / file syslog) dari
  Dashboard dan kirim hasil (hak baca journal via grup 'adm')

Instalasi (root):
    sudo bash package/install.sh

Config:
    /etc/pantau/config.json   (di-install idempotently oleh install.sh)
    fallback: config.json di direktori script

Environment variable (override config):
    MONITOR_SERVER_URL  - URL Dashboard Pantau
    MONITOR_API_KEY     - API Key server ini
    MONITOR_INTERVAL    - Interval laporan (detik)
"""

import http.client
import ipaddress
import json
import os
import pwd
import platform
import random
import re
import select
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

IS_ROOT = os.geteuid() == 0

ALLOWED_SYSTEMCTL_ACTIONS = frozenset({"restart", "start", "stop"})
VALID_PROCESS_NAME_RE = re.compile(r'^[a-zA-Z0-9@._:\-]{1,64}$')

PANTUAN_RESTART = "/usr/local/sbin/pantau-restart"
PANTUAN_FIREWALL = "/usr/local/sbin/pantau-firewall"
PANTUAN_UNAME = "agent_pantau"
SS_BIN = "/usr/bin/ss"
SYSLOG_FILE = "/var/log/syslog"
AUTH_FILE = "/var/log/auth.log"

_sudo_ss_warned = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config():
    base = {
        "server_url": "http://127.0.0.1:8400",
        "api_key": "",
        "interval_seconds": 10,
        "exclude_ports": [],
    }

    # Utamakan config produksi /etc/pantau, fallback config lokal
    for cfg_path in ("/etc/pantau/config.json", str(Path(__file__).parent / "config.json")):
        path = Path(cfg_path)
        if path.exists():
            try:
                with open(path) as f:
                    base.update(json.load(f))
            except (OSError, json.JSONDecodeError) as e:
                print(f"[WARN] Gagal baca {path}: {e}")
            break

    if v := os.environ.get("MONITOR_SERVER_URL"):
        base["server_url"] = v
    if v := os.environ.get("MONITOR_API_KEY"):
        base["api_key"] = v
    if v := os.environ.get("MONITOR_INTERVAL"):
        try:
            base["interval_seconds"] = max(5, int(v))
        except ValueError:
            pass

    if not base["api_key"]:
        print("[FATAL] API Key belum dikonfigurasi!")
        print("  Set MONITOR_API_KEY atau isi /etc/pantau/config.json")
        sys.exit(1)

    return base


# ---------------------------------------------------------------------------
# Service detection
# ---------------------------------------------------------------------------
def _run_cmd(cmd: list[str], timeout: int = 5) -> "subprocess.CompletedProcess | None":
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def run_ss(args: list[str]):
    """
    Jalankan ss dengan visibilitas nama proses milik user lain.
    - root             : ss langsung
    - non-root + sudo  : sudo -n /usr/bin/ss (requirement deteksi lengkap)
    - lainnya          : fallback ss langsung (visibilitas terbatas)
    """
    if IS_ROOT:
        return _run_cmd([SS_BIN] + args)
    res = _run_cmd(["/usr/bin/sudo", "-n", SS_BIN] + args)
    if res is not None and res.returncode == 0:
        return res
    global _sudo_ss_warned
    if res is not None and res.returncode != 0 and not _sudo_ss_warned:
        _sudo_ss_warned = True
        print(f"[WARN] sudo ss gagal (rc={res.returncode}), fallback ke ss tanpa hak root: "
              f"{(res.stderr or '').strip()[:120]}")
    return _run_cmd([SS_BIN] + args)


def get_process_path(pid: int) -> str:
    try:
        if sys.platform.startswith("linux"):
            return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        pass
    return ""


DEV_TOOL_NAME_HINTS = ("mainthread", "code-", "vscode", "electron", "jupyter")


def is_dev_tool(proc_name: str | None, pid: int | None) -> bool:
    """Filter tools dev (VS Code, Jupyter, dll) supaya tidak jadi service palsu."""
    if not proc_name:
        return False
    low = proc_name.lower()
    # Deteksi by nama — andal walau /proc milik user lain tidak bisa dibaca
    if low.startswith(DEV_TOOL_NAME_HINTS):
        return True
    if pid:
        path = get_process_path(pid)
        if ".vscode" in path or "vscode-server" in path:
            return True
        if "node" in path and "/usr/bin" not in path:
            return True
    return False


def guess_process_by_port(port: int) -> str | None:
    well_known = {
        22: "sshd", 25: "smtp", 53: "dns", 80: "http", 443: "https",
        3306: "mysql", 5432: "postgresql", 6379: "redis",
        8000: "uvicorn", 8400: "uvicorn", 9000: "uvicorn",
        8080: "http-alt", 8443: "https-alt", 27017: "mongodb",
    }
    return well_known.get(port)


def normalize_process_name(name: str) -> str:
    mapping = {
        "sshd": "sshd", "ssh": "sshd", "nginx": "nginx",
        "apache2": "apache2", "httpd": "httpd",
        "mysqld": "mysql", "mariadbd": "mysql",
        "postgres": "postgresql", "postgresql": "postgresql",
        "redis-server": "redis", "redis": "redis",
        "dockerd": "docker", "docker": "docker",
        "node": "nodejs", "python3": "python", "uvicorn": "uvicorn",
        "gunicorn": "gunicorn", "cron": "cron", "crond": "cron",
        "rsyslogd": "rsyslog", "chronyd": "ntp", "ntpd": "ntp",
        "mariadb-server": "mariadb",
    }
    lower = name.lower()
    for key, val in mapping.items():
        if key in lower:
            return val
    return name


def parse_ss_listening() -> list[dict]:
    result = run_ss(["-tlnp"])
    if result is None:
        return []

    EPHEMERAL_START = 32768
    services = []
    for line in result.stdout.strip().split("\n")[1:]:
        if not line.strip():
            continue
        port_match = re.search(r':(\d+)\s', line)
        if not port_match:
            continue
        port = int(port_match.group(1))

        proc_match = re.search(r'users:\(\("([^"]+)"', line)
        proc_name = proc_match.group(1) if proc_match else None
        pid_match = re.search(r'pid=(\d+)', line)
        pid = int(pid_match.group(1)) if pid_match else None

        if is_dev_tool(proc_name, pid):
            continue

        if not proc_name:
            guessed = guess_process_by_port(port)
            if not guessed:
                continue
            proc_name = guessed

        if port >= EPHEMERAL_START and not proc_match:
            continue

        proc_name = normalize_process_name(proc_name)
        bind_match = re.search(r'(\S+):' + str(port) + r'\s', line)
        bind_addr = bind_match.group(1) if bind_match else "0.0.0.0"

        services.append({
            "port": port,
            "process_name": proc_name,
            "service_name": proc_name,
            "bind_address": bind_addr,
        })
    return services


def count_established(port: int) -> int:
    result = run_ss(["-tn", "state", "established", f"( sport = :{port} )"])
    if result is None:
        return 0
    lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
    return max(0, len(lines) - 1)


def is_web_port(port: int) -> bool:
    """Port umum untuk web service."""
    return port in (80, 443, 8080, 8443, 8081, 8082, 3000, 5000)


# ---------------------------------------------------------------------------
# Health checks dalam
# ---------------------------------------------------------------------------
def _connect_host(addr: str | None) -> str:
    """
    Normalisasi bind address dari `ss` untuk dipakai koneksi health check.
    - potong suffix interface: '127.0.0.53%lo' -> '127.0.0.53'
    - buka kurung IPv6:        '[::1]' -> '::1'
    - wildcard dipetakan ke localhost
    """
    if not addr:
        return "127.0.0.1"
    if "%" in addr:
        addr = addr.split("%", 1)[0]
    addr = addr.strip().lstrip("[").rstrip("]")
    if addr in ("0.0.0.0", "::", "*", ""):
        return "127.0.0.1"
    if addr == "::1":
        return "::1"
    return addr


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirect TIDAK diikuti oleh health check.

    Probe harus menilai web server-nya sendiri, bukan isi halaman yang
    dialingihkan. Mengikuti redirect pernah membuat nginx yang `active`
    ditandai `down`: 301 -> https://domain-publik, lalu probe ikut gagal
    karena DNS/CDN publik tidak terjangkau dari server tersebut.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# ProxyHandler({}) mematikan proxies dari environment (http_proxy/https_proxy).
# Tanpa ini probe bisa keluar lewat proxy dan mengukur koneksi proxy, bukan
# service lokal yang sedang diukur.
_HTTP_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _NoRedirect
)

# Server membalas lalu menutup koneksi tanpa HTTP response yang valid
# (port nginx dibuka dengan `return 444`, keepalive salah, dsb). Port-nya
# hidup, jadi ini BUKAN "service mati" - hanya respons halamannya tidak benar.
_HTTP_BAD_RESPONSE = (
    http.client.RemoteDisconnected,
    http.client.BadStatusLine,
    http.client.IncompleteRead,
    http.client.ResponseNotReady,
    http.client.LineTooLong,
)

# TCP-nya sendiri gagal: ini baru service yang benar-benar tidak melayani.
_CONNECT_FAIL = (
    ConnectionRefusedError,
    ConnectionResetError,
    socket.timeout,
    TimeoutError,
    socket.gaierror,
    OSError,
)


def http_health_check(port: int, addr: str) -> dict:
    """
    HTTP health check: GET / tanpa follow redirect, ukur response time.

    Return: {response_time_ms, health_message, healthy}

    Setiap respons HTTP (200/301/403/404/500) berarti web server hidup dan
    dihitung `healthy` - yang penting service-nya melayani atau tidak.
    hanya kalau tidak ada satu byte pun yang kembali, atau handshake TLS gagal
    total karena sertifikat tidak bisa diverifikasi.
    """
    scheme = "https" if port in (443, 8443) else "http"
    host = _connect_host(addr)
    url = f"{scheme}://{host}:{port}/"

    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Host", f"{host}:{port}")
        req.add_header("User-Agent", "pantau-agent/health-check")
        req.add_header("Connection", "close")
        with _HTTP_OPENER.open(req, timeout=5) as resp:
            elapsed = (time.monotonic() - start) * 1000
            code = resp.status
            note = ""
            if code >= 500:
                note = " (halaman error, service hidup)"
            elif code in (301, 302, 307, 308):
                note = " (redirect, service hidup)"
            return {
                "response_time_ms": int(elapsed),
                "health_message": f"HTTP {code}{note}",
                "healthy": True,
            }
    except urllib.error.HTTPError as e:
        # 4xx/5xx tetap berarti ada proses yang melayani di port ini.
        elapsed = (time.monotonic() - start) * 1000
        return {
            "response_time_ms": int(elapsed),
            "health_message": f"HTTP {e.code} (service hidup)",
            "healthy": True,
        }
    except _HTTP_BAD_RESPONSE as e:
        # TCP connect jalan, tapi tidak ada HTTP response yang benar.
        elapsed = (time.monotonic() - start) * 1000
        return {
            "response_time_ms": int(elapsed),
            "health_message": f"Port terbuka, respons HTTP tidak valid: {type(e).__name__}",
            "healthy": True,
        }
    except ssl.SSLError as e:
        elapsed = (time.monotonic() - start) * 1000
        # TLS handshake gagal: port hidup, sertifikat/HTTPS-nya yang bermasalah.
        return {
            "response_time_ms": int(elapsed),
            "health_message": f"TLS gagal ({e.reason or type(e).__name__}), service hidup",
            "healthy": True,
        }
    except (urllib.error.URLError, OSError, ValueError) as e:
        elapsed = (time.monotonic() - start) * 1000
        reason = getattr(e, "reason", None)
        if isinstance(reason, ssl.SSLError):
            return {
                "response_time_ms": int(elapsed),
                "health_message": f"TLS gagal ({reason.reason or type(reason).__name__}), service hidup",
                "healthy": True,
            }
        if isinstance(reason, _HTTP_BAD_RESPONSE):
            return {
                "response_time_ms": int(elapsed),
                "health_message": f"Port terbuka, respons HTTP tidak valid: {type(reason).__name__}",
                "healthy": True,
            }
        if isinstance(reason, _CONNECT_FAIL):
            return {
                "response_time_ms": int(elapsed),
                "health_message": f"Tidak ada yang melayani: {reason}",
                "healthy": False,
            }
        return {
            "response_time_ms": int(elapsed),
            "health_message": f"Gagal connect: {e}",
            "healthy": False,
        }


# Jumlah kegagalan probe berurutan sebelum sebuah service ditandai "down"
# (anti-flapping; port yang benar-benar hilang tetap down via laporan tak-lengkap).
SERVICE_DOWN_AFTER_FAILS = 3

# Streak kegagalan probe per port (persist antar siklus proses agen).
_svc_fail_streak: dict[int, int] = {}

# Wrapper sudo sempit yang dipasang install.sh (hak minimum, idempoten).
PANTUAN_APT_CMD = "/usr/local/sbin/pantau-apt"
PANTUAN_HISTORY_CMD = "/usr/local/sbin/pantau-history"
PANTUAN_HOST_CMD = "/usr/local/sbin/pantau-host"

# Kuota output apt update/upgrade (praktis penuh; MEDIUMTEXT baseline 16MB,
# streaming server punya kuota sama).
APT_AGENT_OUTPUT_MAX = 4_000_000

# Tampilan LIVE hanya ekor output (seperti `tail -f`); hasil final tetap penuh.
APT_PROGRESS_TAIL_CHARS = 200_000

# Versi agen, dikirim ke dashboard di tiap laporan (badge "agen vX.Y").
AGENT_VERSION = "3.11.0"


def tcp_health_check(port: int, addr: str) -> dict:
    """TCP connect check: ukur response time."""
    host = _connect_host(addr)
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=5):
            elapsed = (time.monotonic() - start) * 1000
            return {
                "response_time_ms": int(elapsed),
                "health_message": "TCP connect OK",
                "healthy": True,
            }
    except (OSError, ValueError) as e:
        elapsed = (time.monotonic() - start) * 1000
        return {
            "response_time_ms": int(elapsed),
            "health_message": f"TCP connect gagal: {e}",
            "healthy": False,
        }


def run_health_check(svc: dict) -> dict:
    """Health check sesuai jenis service."""
    if is_web_port(svc["port"]):
        return http_health_check(svc["port"], svc.get("bind_address", "0.0.0.0"))
    return tcp_health_check(svc["port"], svc.get("bind_address", "0.0.0.0"))


def detect_all_services() -> list[dict]:
    listening = parse_ss_listening()

    seen_ports = set()
    unique = []
    for svc in listening:
        if svc["port"] in seen_ports:
            continue
        seen_ports.add(svc["port"])

        svc["active_connections"] = count_established(svc["port"])

        # Health check dalam
        health = run_health_check(svc)
        svc["response_time_ms"] = health["response_time_ms"]
        svc["health_message"] = health["health_message"]

        # Status up HANYA jika port LISTEN dan health check sehat.
        # Anti-flapping: "down" baru dicatat setelah beberapa kegagalan
        # beruntun, agar daemon yang lambat tidak tertera down-di-momen.
        _fail_streak = _svc_fail_streak.get(svc["port"], 0)
        if health["healthy"]:
            _svc_fail_streak[svc["port"]] = 0
            svc["status"] = "up"
        else:
            _svc_fail_streak[svc["port"]] = _fail_streak + 1
            svc["status"] = "down" if _fail_streak + 1 >= SERVICE_DOWN_AFTER_FAILS else "up"

        unique.append(svc)

    for stale in [p for p in _svc_fail_streak if p not in seen_ports]:
        del _svc_fail_streak[stale]

    return unique


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def http_json_request(cfg: dict, path: str, method: str = "GET", data: dict | None = None, timeout: int = 10):
    """HTTP JSON request dengan API key. Return (status_code, response_dict)."""
    url = cfg["server_url"].rstrip("/") + path
    body = json.dumps(data).encode("utf-8") if data else None

    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Api-Key", cfg["api_key"])

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            try:
                resp_data = json.loads(resp.read().decode() or "{}")
            except json.JSONDecodeError:
                resp_data = {}
            return code, resp_data
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, OSError) as e:
        print(f"[WARN] HTTP {path} gagal: {e}")
        return 0, {}


def send_report(cfg: dict, services: list, system: dict,
                accounts: list | None = None, units: list | None = None,
                apt: dict | None = None) -> bool:
    if len(services) > 100:
        services = services[:100]
    payload = {
        "hostname": get_hostname(),
        "ip_address": get_local_ip(),
        "services": services,
        "system": system,
        "kernel": _kernel_release(),
        "os_label": _os_pretty(),
        "arch": platform.machine(),
        "agent_version": AGENT_VERSION,
    }
    if accounts is not None:
        payload["accounts"] = accounts
    if units is not None:
        payload["units"] = units
    if apt is not None:
        payload["apt"] = apt
    payload["security"] = collect_security()

    for attempt in range(1, 4):
        code, _ = http_json_request(cfg, "/api/report", "POST", payload)
        if code == 200:
            return True
        if attempt == 3:
            print(f"[ERROR] Gagal kirim laporan (HTTP {code})")
            break
        time.sleep(2 * attempt + random.uniform(0, 1.5))
    return False


# ---------------------------------------------------------------------------
# Command execution (restart/start/stop)
# ---------------------------------------------------------------------------
def check_pending_commands(cfg: dict) -> list[dict]:
    """Polling antrian command dari Dashboard."""
    code, data = http_json_request(cfg, "/api/commands", "GET")
    if code == 200 and data:
        return data.get("commands", [])
    return []


def execute_command(cfg: dict, command: dict) -> dict:
    """
    Eksekusi command di server.
    - restart/start/stop : service via systemctl (root) / wrapper pantau-restart.
    - block_ip           : blokir IP sumber serangan via iptables (wrapper pantau-firewall).
    - restart_agent      : restart agen sendiri secara tertunda (respon terkirim dulu).
    - reboot_host/poweroff_host : reboot / poweroff OS via wrapper pantau-host.
                                 Eksekusi TERTUNDA ~4 dtk agar ack hasil sempat terkirim.
    """
    action = command.get("action", "restart")
    cmd_id = command.get("id")
    print(f"[CMD] Menjalankan '{action}' (id={cmd_id})")

    # Tandai executing
    http_json_request(cfg, f"/api/commands/{cmd_id}/status", "POST", {"status": "executing"})

    if action == "block_ip":
        result = _exec_block_ip(command)
    elif action == "restart_agent":
        result = _exec_restart_agent()
    elif action in ("reboot_host", "poweroff_host"):
        result = _exec_host_control(action)
    elif action not in ("restart", "start", "stop"):
        result = {
            "ok": False,
            "output": f"Aksi tidak dikenal oleh agen ini ('{action}') "
                      "— indikasi agen versi lama. Update agen: jalankan ulang install.sh.",
        }
    else:
        result = _exec_service_action(action, command)

    print(f"[CMD] Hasil: {result['output']}")
    return result


def _validate_ipv4(ip: str) -> bool:
    """IPv4 publik yang aman diblokir (bukan privat/loopback/link-local/multicast)."""
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved)


def _exec_block_ip(command: dict) -> dict:
    """Blokir IP sumber pendekatan SSH: iptables -I INPUT 1 -s <ip> -j DROP."""
    params = command.get("params") or {}
    ips = [str(i) for i in (params.get("ips") or [])][:10]
    if not ips:
        return {"ok": False, "output": "Tidak ada IP untuk diblokir."}
    outs: list = []
    ok_all = True
    for ip in ips:
        if not _validate_ipv4(ip):
            outs.append(f"{ip}: IP tidak valid / diblokir (privat/local/multicast)")
            ok_all = False
            continue
        if IS_ROOT:
            res = _run_native(["iptables", "-I", "INPUT", "1", "-s", ip, "-j", "DROP"],
                              f"iptables -I INPUT 1 -s {ip} -j DROP")
        else:
            res = _run_native(["/usr/bin/sudo", "-n", PANTUAN_FIREWALL, "block", ip],
                              f"sudo -n {PANTUAN_FIREWALL} block {ip}")
        if not res["ok"]:
            ok_all = False
        outs.append(f"{ip}: {res['output']}")
    note = " | aturan iptables volatile (hilang saat reboot): utk permanen gunakan iptables-persistent"
    return {"ok": ok_all, "output": ("; ".join(outs) + note)[:2000]}


def _exec_host_control(action: str) -> dict:
    """Reboot/poweroff OS — ditunda ~4 dtk agar respon ack sempat terkirim ke Dashboard.

    SEBELUM menjadwalkan, lakukan preflight 'check' via wrapper pantau-host:
    - kalau wrapper/sudoers belum terpasang, sudo -n gagal -> lapor kegagalan NYATA
      (jangan asal "akan dimatikan") supaya admin tahu harus update agen.
    - kalau systemd tidak terpasang (container/WSL), lapor jelas.
    Baru proses nyata dijadwalkan (pola sama seperti restart_agent) via wrapper.
    """
    sub_action = "reboot" if action == "reboot_host" else "poweroff"

    def _run_wrapper(*args: str) -> tuple[bool, str]:
        if IS_ROOT:
            p = subprocess.run([PANTUAN_HOST_CMD, *args],
                               capture_output=True, text=True, timeout=30)
        else:
            p = subprocess.run(["/usr/bin/sudo", "-n", PANTUAN_HOST_CMD, *args],
                               capture_output=True, text=True, timeout=30)
        out = (p.stdout or "").strip() or p.stderr.strip() or ""
        return p.returncode == 0, out[:1200]

    # Preflight check (tanpa efek samping)
    ok_check, msg_check = _run_wrapper("check")
    if not ok_check:
        return {"ok": False,
                "output": f"Perintah {sub_action} DIBATALKAN: wrapper pantau-host belum "
                          f"terpasang/diizinkan di server ini. {msg_check} "
                          "-- jalankan ulang package install.sh (agen v3.6+)."}
    if "systemd TIDAK berjalan" in msg_check or "TIDAK berjalan" in msg_check:
        return {"ok": False,
                "output": f"Perintah {sub_action} DIBATALKAN: {msg_check}"}

    label = f"{PANTUAN_HOST_CMD} {sub_action}"
    if not IS_ROOT:
        label = f"/usr/bin/sudo -n {label}"
    try:
        # PENTING: tanpa redirect shell ('>> log') di sini — redirect dijalankan
        # SELAKU user pantau (sebelum sudo) dan gagal karena log milik root,
        # sehingga poweroff tak pernah dieksekusi. Wrapper yang menulis log
        # (lewat sudo, sebagai root) setelah memvalidasi argumen.
        subprocess.Popen(
            ["/bin/sh", "-c", f"sleep 4; {label}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
        verb = "di-reboot" if sub_action == "reboot" else "di-matikan (poweroff)"
        return {"ok": True,
                "output": f"Perintah diterima: server akan {verb} dalam ±4 detik. "
                          "Dashboard akan terputus dari server ini."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "output": f"Gagal menjadwalkan {sub_action}: {e}"}


def _exec_restart_agent() -> dict:
    """Jadwalkan restart agen ~2 dtk setelah respon terkirim (proses lama ia yang kill diri sendiri).

    Tanpa sudo: systemd unit agent_pantau memakai Restart=always, jadi agen
    cukup TERMINATE dirinya sendiri secara tertunda; systemd yang menghidupkan ulang.
    """
    try:
        subprocess.Popen(
            ["/bin/sh", "-c", f"sleep 2; kill -TERM {os.getpid()}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
        return {"ok": True, "output": "Restart agen (agent_pantau) dijadwalkan otomatis (systemd akan menghidupkan ulang)."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "output": f"Gagal menjadwalkan restart agen: {e}"}


def _exec_service_action(action: str, command: dict) -> dict:
    process_name = command.get("process_name", "")
    service_name = command.get("service_name", "")

    if action not in ALLOWED_SYSTEMCTL_ACTIONS:
        return {"ok": False, "output": f"Aksi tidak diizinkan: {action}"}

    if not process_name:
        return {"ok": False, "output": "process_name kosong dari dashboard"}

    if not VALID_PROCESS_NAME_RE.match(process_name):
        return {"ok": False, "output": f"Nama proses tidak valid: {process_name}"}

    # SELALU lewat wrapper pantau-restart (deny-list + sanitasi unit), termasuk
    # saat berjalan sebagai root — deny-list tidak boleh terlewati.
    cmd = [PANTUAN_RESTART, action, process_name]
    label = f"{PANTUAN_RESTART} {action} {process_name}"
    if not IS_ROOT:
        cmd = ["/usr/bin/sudo", "-n", *cmd]
        label = f"sudo -n {label}"
    result = _run_native(cmd, label)
    del service_name
    return result


def _run_native(cmd: list[str], label: str) -> dict:
    """Jalankan command dan kembalikan {'ok': bool, 'output': str}."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        ok = proc.returncode == 0
        output = (proc.stdout or proc.stderr).strip()
        return {
            "ok": ok,
            "output": output or f"{label} rc={proc.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"Timeout eksekusi: {label}"}
    except FileNotFoundError as e:
        return {"ok": False, "output": f"Perintah tidak tersedia: {e}"}


def report_command_result(cfg: dict, command_id: int, result: dict):
    """Lapor hasil eksekusi command ke Dashboard."""
    status = "success" if result["ok"] else "failed"
    http_json_request(
        cfg, f"/api/commands/{command_id}/result", "POST",
        {"status": status, "result": result["output"][:2000]},
    )


def poll_and_execute_commands(cfg: dict):
    """Cek command pending lalu eksekusi satu per satu."""
    commands = check_pending_commands(cfg)
    for cmd in commands:
        result = execute_command(cfg, cmd)
        report_command_result(cfg, cmd["id"], result)


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------
def get_hostname() -> str:
    return socket.gethostname()


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _kernel_release() -> str:
    try:
        return os.uname().release
    except Exception:
        return ""


def _os_pretty() -> str:
    """Nama distribusi + versi (mis. 'Ubuntu 22.04.3 LTS'), dari /etc/os-release."""
    try:
        fields = {}
        with open("/etc/os-release", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    fields[k] = v.strip().strip('"')
        pretty = fields.get("PRETTY_NAME")
        if pretty:
            return pretty
        name = fields.get("NAME", "")
        ver = fields.get("VERSION_ID", "") or fields.get("VERSION", "")
        return (name + " " + ver).strip()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Performance hardware / jaringan / akun / unit layanan / log layanan
# ---------------------------------------------------------------------------
_prev_cpu: tuple[float, float] | None = None
_net_prev: dict[str, tuple[int, int]] = {}
_net_prev_t: float = 0.0
DISK_TYPES = ("ext4", "ext3", "ext2", "xfs", "btrfs", "zfs", "vfat", "ntfs", "f2fs", "overlay")


def _cpu_percent() -> float:
    """Utilisasi CPU dari delta dua pembacaan /proc/stat."""
    global _prev_cpu

    def read_stat():
        try:
            with open("/proc/stat") as f:
                parts = f.readline().split()
        except OSError:
            return None
        if len(parts) < 5 or not parts[0].startswith("cpu"):
            return None
        nums = [int(x) for x in parts[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        return idle, sum(nums)

    now = time.monotonic()
    cur = read_stat()
    if cur is None:
        return 0.0
    if _prev_cpu is None:
        _prev_cpu = cur
        return 0.0
    idle_d = cur[0] - _prev_cpu[0]
    total_d = cur[1] - _prev_cpu[1]
    _prev_cpu = cur
    if total_d <= 0:
        return 0.0
    return max(0.0, min(100.0, (1.0 - idle_d / total_d) * 100.0))


def _read_meminfo() -> dict:
    mem = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0]
                    val = "".join(c for c in parts[1] if c.isdigit())
                    if val:
                        mem[key] = int(val) * 1024  # kB -> bytes
    except OSError:
        pass
    return mem


def collect_disks() -> list[dict]:
    out = []
    try:
        with open("/proc/mounts") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        mount, fstype = parts[1], parts[2]
        if fstype not in DISK_TYPES or len(out) >= 20:
            continue
        try:
            st = os.statvfs(mount)
        except OSError:
            continue
        total = st.f_frsize * st.f_blocks
        used = total - st.f_frsize * st.f_bavail
        pct = round(used * 100.0 / total, 1) if total else 0.0
        out.append({
            "mount": mount, "type": fstype,
            "total": total, "used": used, "pct": pct,
        })
    return out


def collect_net() -> list[dict]:
    global _net_prev, _net_prev_t
    ifaces = []
    try:
        with open("/proc/net/dev") as f:
            lines = f.read().splitlines()[2:]
    except OSError:
        return ifaces

    now = time.monotonic()
    dt = (now - _net_prev_t) if _net_prev_t else 0.0
    for line in lines:
        parts = line.replace(":", " ", 1).split()
        if len(parts) < 10:
            continue
        name = parts[0]
        rx, tx = int(parts[1]), int(parts[9])
        rx_rate = tx_rate = 0
        prev = _net_prev.get(name)
        if prev is not None and dt > 0:
            rx_rate = max(0, (rx - prev[0])) / dt
            tx_rate = max(0, (tx - prev[1])) / dt
        is_up = 0
        try:
            with open(f"/sys/class/net/{name}/operstate") as f:
                is_up = 1 if f.read().strip() == "up" else 0
        except OSError:
            pass
        ifaces.append({
            "iface": name, "rx": rx, "tx": tx,
            "rx_rate": int(rx_rate), "tx_rate": int(tx_rate), "is_up": is_up,
        })
        _net_prev[name] = (rx, tx)
    _net_prev_t = now
    return [i for i in ifaces if not i["iface"].startswith("lo")][:16]


def collect_system() -> dict:
    mem = _read_meminfo()
    mem_total = mem.get("MemTotal", 0)
    mem_avail = mem.get("MemAvailable", mem_total)
    mem_used = mem_total - mem_avail
    swap_total = mem.get("SwapTotal", 0)
    swap_used = swap_total - mem.get("SwapFree", swap_total)

    loads = [0.0, 0.0, 0.0]
    uptime = None
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        for i, v in enumerate(parts[:3]):
            try:
                loads[i] = float(v)
            except ValueError:
                pass
    except OSError:
        pass
    try:
        with open("/proc/uptime") as f:
            uptime = int(float(f.read().split()[0]))
    except (OSError, ValueError, IndexError):
        pass

    procs = 0
    try:
        procs = sum(1 for e in os.listdir("/proc") if e.isdigit())
    except OSError:
        pass

    return {
        "cpu": _cpu_percent(),
        "load1": loads[0], "load5": loads[1], "load15": loads[2],
        "mem_total": mem_total, "mem_used": mem_used, "mem_avail": mem_avail,
        "swap_total": swap_total, "swap_used": swap_used,
        "procs": procs, "uptime": uptime,
        "disks": collect_disks(),
        "net": collect_net(),
    }


def _parse_lastlog() -> dict[str, str]:
    result = {}
    res = _run_cmd(["lastlog"], timeout=10)
    if res is None:
        return result
    for line in res.stdout.splitlines()[1:]:
        parts = line.split(None, 1)
        if parts:
            result[parts[0]] = parts[1] if len(parts) > 1 else ""
    return result


def _parse_who() -> list[dict]:
    sessions = []
    res = _run_cmd(["who"], timeout=5)
    if res is None:
        return sessions
    for line in res.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        entry = {"user": parts[0], "tty": parts[1] if len(parts) > 1 else ""}
        if len(parts) >= 3:
            entry["time"] = " ".join(parts[2:4])
            src = " ".join(parts[4:]).strip("()")
            entry["from"] = src or ""
        sessions.append(entry)
    return sessions


def collect_accounts() -> list[dict]:
    lastlog = _parse_lastlog()
    who = _parse_who()
    sessions_by_user: dict[str, list[dict]] = {}
    for s in who:
        sessions_by_user.setdefault(s["user"], []).append(s)

    accounts = []
    try:
        entries = list(pwd.getpwall())
    except Exception:
        entries = []
    for pw in sorted(entries, key=lambda e: e.pw_uid):
        sessions = sessions_by_user.get(pw.pw_name, [])
        # Fokus akun manusia: uid >= 1000, root, atau yang sedang logged-in
        if (pw.pw_uid >= 1000 or pw.pw_uid == 0 or sessions) and pw.pw_uid != 65534:
            accounts.append({
                "user": pw.pw_name,
                "uid": pw.pw_uid,
                "shell": pw.pw_shell or "",
                "last_login": lastlog.get(pw.pw_name, ""),
                "sessions": sessions[:5],
            })
        if len(accounts) >= 60:
            break
    return accounts


def collect_units() -> list[str]:
    res = _run_cmd(
        ["systemctl", "list-units", "--type=service", "--state=running",
         "--no-pager", "--no-legend"],
        timeout=10,
    )
    units = []
    if res is None:
        return units
    for line in res.stdout.splitlines():
        parts = line.split()
        if parts and parts[0].endswith(".service"):
            units.append(parts[0][:-8])
    return sorted(set(units))


def _last_apt_update_iso() -> str | None:
    """Perkiraan kapan 'apt update' terakhir berjalan.

    Berdasarkan mtime terbaru isi /var/lib/apt/lists (daftar paket)
    dan /var/cache/apt/pkgcache.bin (ditulis ulang tiap apt update).
    Bukan kebutuhan root; hanya baca metadata.
    """
    latest = 0.0
    for base in ("/var/lib/apt/lists", "/var/cache/apt"):
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            try:
                m = os.path.getmtime(os.path.join(base, name))
            except OSError:
                continue
            if m > latest:
                latest = m
    if not latest:
        return None
    return datetime.fromtimestamp(latest).isoformat(timespec="seconds")


def collect_apt() -> dict | None:
    """Jumlah paket OS yang bisa di-upgrade (Debian/Ubuntu, via apt).

    Mengembalikan {"upgradable": N, "last_update": "<ISO>"}, atau None
    bila apt tidak tersedia / bukan sistem debian.
    """
    if not (os.path.exists("/usr/bin/apt") or os.path.exists("/usr/bin/apt-get")):
        return None
    apt = {
        "upgradable": 0,
        "packages": [],
        "last_update": _last_apt_update_iso(),
    }
    res = _run_cmd(["/usr/bin/apt", "list", "--upgradable", "-qq"], timeout=20)
    if res is None:
        return apt
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or "/" not in line or line.lower().startswith("listing"):
            continue
        if "upgradable" in line.lower() or "upgradeable" in line.lower():
            parts = line.split()
            name = parts[0].split("/")[0] if parts else ""
            if name:
                apt["upgradable"] += 1
                apt["packages"].append({
                    "name": name,
                    "version": parts[1] if len(parts) > 1 else "",
                })
    return apt


def _apt_cmd(kind: str):
    """Command apt (lewat wrapper sempit) + timeout per jenis aksi."""
    if kind == "APT_UPDATE":
        return ["/usr/bin/sudo", "-n", PANTUAN_APT_CMD, "update"], 300
    if kind == "APT_UPGRADE":
        return ["/usr/bin/sudo", "-n", PANTUAN_APT_CMD, "upgrade"], 900
    if kind == "APT_UPGRADE_INTERACT":
        # Interaktif menunggu admin mengetik; timeout lebih longgar, dan HANYA
        # diakhiri bila proses benar-benar tidak bergerak (mis. admin lupa).
        return ["/usr/bin/sudo", "-n", PANTUAN_APT_CMD, "upgrade-interact"], 3600
    if kind == "APT_DIST_UPGRADE":
        return ["/usr/bin/sudo", "-n", PANTUAN_APT_CMD, "dist-upgrade"], 3600
    if kind == "APT_FIX":
        # Reparasi dpkg & pemulihan paket rusak
        return ["/usr/bin/sudo", "-n", PANTUAN_APT_CMD, "fix"], 1800
    raise ValueError(f"unit apt tidak dikenal: {kind}")


def _apt_sudo_denied_hint(err: str) -> str:
    """Pesan bantuan bila wrapper/sudoers belum tersedia di host klien."""
    return (
        "[apt tidak dapat dijalankan] hak sudo agen 'pantau' untuk wrapper "
        "pantau-apt belum tersedia di host ini.\n"
        "Perbaiki (sebagai root di host ini):\n"
        "  cd <folder-paket-pantau>/package && sudo bash install.sh\n"
        "(memasang ulang sudoers + wrapper pantau-apt; aman/idempotent.)\n"
        "Rincian teknis:\n" + (err or "")
    )


_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|.)")
_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def _keep_sgr(text: str) -> str:
    """Buang semua escape sequence KECUALI SGR (warna), sisakan \\r \\b \\t \\n.

    Untuk stream apt: dashboard merender ulang kodenya sendiri supaya output
    di kotak terminal terlihat sama seperti di SSH (warna + gerak kursor),
    bukan teks polos. Escape lain (kursor, layar, OSC) dibuang karena tidak
    berarti apa-apa di luar terminal sungguhan.
    """
    if not text:
        return ""

    def _repl(m: re.Match) -> str:
        return m.group(0) if _SGR_RE.fullmatch(m.group(0)) else ""

    cleaned = _ANSI_RE.sub(_repl, text).replace("\x00", "")
    # SGR disisihkan dulu pakai placeholder, baru karakter kontrol (termasuk
    # ESC) dibuang, lalu placeholder dikembalikan menjadi escape sungguhan.
    kept: list[str] = []

    def _stash(m: re.Match) -> str:
        kept.append(m.group(0))
        return f"\ue000{len(kept) - 1}\ue001"

    cleaned = _SGR_RE.sub(_stash, cleaned)
    cleaned = "".join(c for c in cleaned
                      if c >= " " or c in "\n\r\b\t\ue000\ue001")
    for idx, code in enumerate(kept):
        cleaned = cleaned.replace(f"\ue000{idx}\ue001", code)
    return cleaned

# Pola prompt interaktif yang masih mungkin muncul walau wrapper sudah
# non-interaktif (mis. skrip post-install milik vendor). Offset [ ... ] adalah
# jawaban default yang dipakai, jadi kita TIDAK menebak: kalau polanya tak
# dikenal, proses dibiarkan dan admin diberi petunjuk cara memperbaikinya.
_APT_PROMPT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"What would you like to do about it \?"), "N\n"),
    (re.compile(r"^\s*(?:Y or I)\s*:\s*install the package maintainer's version", re.M), "N\n"),
    (re.compile(r"\[default=N\]", re.I), "N\n"),
    (re.compile(r"Press \[Enter\] to continue", re.I), "\n"),
    (re.compile(r"Do you want to continue\? \[Y/n\]", re.I), "y\n"),
]
# Diam tanpa output > detik ini = anggap sedang menunggu input.
_APT_PROMPT_IDLE_SECS = 45.0


def _apt_prompt_answer(tail: str) -> tuple[str | None, str]:
    """Deteksi prompt interaktif pada output terakhir.

    Kembalikan (jawaban, penjelasan) bila polanya dikenali; (None, "") bila
    tidak ada prompt atau polanya tak dikenal (biarkan, jangan menebak).
    """
    if not tail:
        return None, ""
    # Hanya baris terakhir yang relevan: prompt selalu di ujung output.
    last = tail.rstrip().splitlines()[-1] if tail.rstrip() else ""
    if not last.strip():
        return None, ""
    for pat, answer in _APT_PROMPT_RULES:
        if pat.search(last):
            return answer, ("prompt dpkg interaktif terdeteksi "
                            f"(jawaban otomatis: {answer.strip() or 'Enter'})")
    return None, ""


def _looks_like_prompt(tail: str) -> bool:
    """Heuristik: baris terakhir mirip prompt yang belum terjawab."""
    if not tail:
        return False
    last = tail.rstrip().splitlines()[-1] if tail.rstrip() else ""
    return last.rstrip().endswith(("?", "??", "):", "]:"))


def _stdin_writer_thread(cfg: dict, rid: int, proc) -> None:
    """Terus ambil jawaban admin dari dashboard lalu tulis ke stdin proses.

    Berhenti saat proses selesai. Semua error ditelan supaya tidak mematikan
    proses apt; admin cukup mengetik ulang bila gagal terkirim.
    """
    while True:
        time.sleep(0.4)
        if proc.poll() is not None:
            return
        try:
            code, data = http_json_request(cfg, f"/api/logs/{rid}/input", "GET", timeout=8)
        except Exception:  # noqa: BLE001 — loop diagnostik, jangan matikan apa pun
            continue
        if code != 200:
            continue
        text = data.get("data")
        if not text:
            continue
        try:
            proc.stdin.write(text.encode("utf-8", errors="replace"))
            proc.stdin.flush()
            # Tidak ada baris tambahan di output: pty sudah menggema karakter
            # yang diketik, persis seperti di terminal. Hanya log agen.
            print(f"[APT] jawaban terkirim ke proses: {text.strip()!r}")
        except (OSError, ValueError):
            return  # proses sudah mati / pipe tertutup


def _clean_output_chunk(text: str) -> str:
    """Bersihkan chunk output mentah: buang kode ANSI & NUL saja (KEEP \r)."""
    if not text:
        return ""
    return _ANSI_RE.sub("", text).replace("\x1b", "").replace("\x00", "")


def _sgr_on(prev: str, params: str) -> str:
    """Gaya aktif setelah kode SGR baru (kode kosong / 0 = reset)."""
    return "" if params in ("", "0") else params


def _render_cells(cells: list[tuple[str, str]], upto: int) -> str:
    """Rakit baris dari sel (gaya, karakter) sambil menyisipkan kode SGR.

    SGR diteruskan ke dashboard agar kotak terminal di browser bisa mewarnai
    teks persis seperti di SSH — jadi hasilnya tetap "seperti terminal".
    """
    parts: list[str] = []
    run: str | None = None
    for idx in range(upto):
        style, ch = cells[idx]
        if style != run:
            if run is not None:            # hanya reset bila memang ada gaya
                parts.append("\x1b[0m")
            if style:
                parts.append("\x1b[%sm" % style)
            run = style
        parts.append(ch)
    if run:
        parts.append("\x1b[0m")
    return "".join(parts).rstrip("\t ")


def termify(raw: str) -> str:
    """Emulasi layar terminal utk output yang memakai \\r (frame progress).

    Di terminal SSH, `\\r` hanya memindahkan kursor ke awal baris; isi yang lama
    TETAP terlihat kecuali ditimpa huruf baru. `\\n` menutup baris. Fungsi ini
    meniru persis itu (buffer sel + posisi kursor), sehingga hasilnya sama
    dengan yang tampil di layar saat menjalankan apt update/upgrade via SSH:
    frame `Reading package lists... 81%` → `82%` … → `Done` hanya jadi satu
    baris, dan baris "Reading package lists... Done" tidak hilang.

    Warna (SGR) ikut dipertahankan: tiap sel menyimpan gaya aktifnya, lalu
    `_render_cells` menyisipkan ulang kode SGR per rentang warna.
    """
    out: list[str] = []
    cells: list[tuple[str, str]] = []
    style = ""
    p = 0
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "\x1b":
            m = _SGR_RE.match(raw, i)
            if m:
                style = _sgr_on(style, m.group(1))
                i = m.end()
                continue
            i += 1  # escape lain: abaikan
            continue
        if c == "\r":
            p = 0
            i += 1
            continue
        if c == "\n":
            out.append(_render_cells(cells, len(cells)) + "\n")
            cells = []
            p = 0
            i += 1
            continue
        if c == "\b":
            p = max(p - 1, 0)
            i += 1
            continue
        if c == "\t":
            while True:
                if p >= len(cells):
                    cells.append((style, " "))
                else:
                    cells[p] = (style, " ")
                p += 1
                if p % 8 == 0:
                    break
            i += 1
            continue
        if ord(c) < 32:
            i += 1
            continue
        if p >= len(cells):
            while len(cells) < p:
                cells.append((style, " "))
            cells.append((style, c))
        else:
            cells[p] = (style, c)
        p += 1
        i += 1
    return "".join(out) + _render_cells(cells, len(cells))


def _tail_parts(parts: list[str], budget: int) -> str:
    """Gabungkan potongan paling akhir sampai mendekati `budget` karakter."""
    out: list[str] = []
    total = 0
    for p in reversed(parts):
        out.append(p)
        total += len(p)
        if total >= budget:
            break
    out.reverse()
    return "".join(out)


_APT_RUN_LOCK = threading.Lock()
_APT_RUNNING = False


def _run_apt_in_thread(cfg: dict, rid: int, kind: str):
    """Rekan thread utk _run_apt_inner dengan jaminan TIDAK tumpang-tindih dua apt."""
    global _APT_RUNNING
    with _APT_RUN_LOCK:
        if _APT_RUNNING:
            print(f"[APT] {kind} (rid={rid}) DITOLAK: proses apt lain sedang berjalan")
            http_json_request(cfg, f"/api/logs/{rid}/result", "POST",
                              {"status": "failed",
                               "result": "Dibatalkan: proses apt lain masih berjalan di server ini."})
            return
        _APT_RUNNING = True
    try:
        _run_apt_inner(cfg, rid, kind)
    finally:
        with _APT_RUN_LOCK:
            _APT_RUNNING = False


def _run_apt_inner(cfg: dict, rid: int, kind: str):
    """Jalankan apt update/upgrade DENGAN STREAMING live ke Dashboard.

    Proses dijalankan lewat wrapper pantau-apt -> script (pty), jadi outputnya
    PERSIS seperti terminal SSH (termasuk frame progress \r). Output dibaca
    dalam potongan biner, dibersihkan, lalu dikirim ke /progress tiap ~1,2
    detik agar admin melihat proses berjalan. Hasil final TIDAK dipotong
    (kuota APT_AGENT_OUTPUT_MAX = 4MB, praktis selengkap SSH).
    """
    try:
        cmd, timeout = _apt_cmd(kind)
    except ValueError as e:
        print(f"[APT] {kind} (rid={rid}) -> invalid: {e}")
        http_json_request(cfg, f"/api/logs/{rid}/result", "POST",
                          {"status": "failed", "result": str(e)[:200]})
        return

    output_parts: list[str] = []
    raw_len = 0
    truncated = False
    last_post = 0.0
    started = time.monotonic()
    last_activity = started
    prompt_answers = 0
    hint_shown = False
    failed = False
    errmsg = ""
    interactive = (kind in ("APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE", "APT_FIX"))

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.PIPE, start_new_session=True)
    except OSError as e:
        proc = None
        failed, errmsg = True, f"[gagal menjalankan apt: {e}]"

    if proc is not None and interactive:
        # Mode interaktif: admin yang menjawab, agen TIDAK menebak. Thread ini
        # hanya menyalin jawaban dari Dashboard ke stdin proses.
        input_thread = threading.Thread(
            target=_stdin_writer_thread, args=(cfg, rid, proc),
            name=f"apt-input-{rid}", daemon=True)
        input_thread.start()

    if proc is not None:
        while True:
            now = time.monotonic()
            if now - started > timeout:
                try:
                    # Bunuh SELURUH grup proses apt/dpkg (bukan hanya sh), biar
                    # tidak ada anak proses yang tertinggal/orphan.
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError, PermissionError):
                    pass
                failed, errmsg = True, f"timeout {int(timeout)} dtk, proses apt dihentikan paksa"
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
                break
            try:
                rdy = select.select([proc.stdout], [], [], 1.0)[0]
            except (OSError, ValueError):
                break
            if rdy:
                raw = proc.stdout.read1(4096)
                if raw:
                    # Stream apt: biarkan \r + warna SGR lewat agar dashboard
                    # bisa merender terminal sungguhan (bukan teks polos).
                    text = _keep_sgr(raw.decode("utf-8", errors="replace"))
                    if text:
                        output_parts.append(text)
                        raw_len += len(text)
                        last_activity = time.monotonic()
                elif proc.poll() is not None:
                    break
            # --- Jaring pengaman: proses diam lama = mungkin menunggu jawaban ---
            if raw_len and (now - last_activity) >= _APT_PROMPT_IDLE_SECS:
                tail = termify(_tail_parts(output_parts, 2000))
                answer, why = _apt_prompt_answer(tail)
                note = ""
                if interactive:
                    # JANGAN menjawab dan jangan juga menulis apa pun: seperti
                    # di terminal, proses diam sampai admin mengetik baris
                    # berikutnya (kursor berkedip di UI yang menandakan).
                    pass
                elif answer and prompt_answers < 3:
                    try:
                        proc.stdin.write(answer.encode())
                        proc.stdin.flush()
                        prompt_answers += 1
                        note = f"\n[pantau] {why}\n"
                    except (OSError, ValueError):
                        note = ""
                elif not answer and not hint_shown and _looks_like_prompt(tail):
                    hint_shown = True
                    note = ("\n[pantau] Proses berhenti & menunggu jawaban pada prompt yang tidak "
                            "dikenali, sehingga tidak bisa dilanjut otomatis.\n"
                            "         Selesaikan manual di server ini:  sudo dpkg --configure -a\n"
                            "         lalu ulangi Update OS dari Dashboard.\n")
                if note:
                    output_parts.append(note)
                    raw_len += len(note)
                    last_activity = time.monotonic()
            if raw_len and (time.monotonic() - last_post >= 1.2):
                tail = termify(_tail_parts(output_parts, APT_PROGRESS_TAIL_CHARS))
                if tail:
                    http_json_request(cfg, f"/api/logs/{rid}/progress", "POST",
                                      {"chunk": tail, "replace": True})
                    last_post = time.monotonic()
            if raw_len > APT_AGENT_OUTPUT_MAX:
                excess = raw_len - APT_AGENT_OUTPUT_MAX
                while excess > 0 and output_parts:
                    part = output_parts[0]
                    if len(part) <= excess:
                        excess -= len(part)
                        output_parts.pop(0)
                    else:
                        output_parts[0] = part[excess:]
                        excess = 0
                raw_len = APT_AGENT_OUTPUT_MAX
                truncated = True
        if proc.returncode is None:
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass

    full = termify("".join(output_parts))
    if truncated and full:
        note = "[catatan: output potongan awal dibuang agen karena melebihi kuota]\n\n"
        full = note + full.strip("\n") + "\n"
    elif full:
        full = full.strip("\n")

    live = full
    if truncated or raw_len > APT_PROGRESS_TAIL_CHARS:
        live = termify(_tail_parts(output_parts, APT_PROGRESS_TAIL_CHARS))
    if live:
        http_json_request(cfg, f"/api/logs/{rid}/progress", "POST",
                          {"chunk": live, "replace": True})

    # Hasil terminal (persis SSH): frame progress sudah "menimpa" via termify.

    try:
        apt = collect_apt()
    except Exception:
        apt = None

    partial = termify(_tail_parts(output_parts, 40000)).strip("\n")
    if failed:
        result_ok = False
        msg = (errmsg + ("\n\n[output sebagian]\n" + partial)) if partial else errmsg
    elif proc is not None and proc.returncode != 0:
        result_ok = False
        msg = _apt_sudo_denied_hint(full or f"rc={proc.returncode}")
    else:
        result_ok = True
        msg = json.dumps({
            "type": kind,
            "output": full[-APT_AGENT_OUTPUT_MAX:],
            "apt": apt,
        })

    result = {"status": "success" if result_ok else "failed", "result": msg}
    print(f"[APT] {kind} (rid={rid}) -> {result['status']} (result {len(msg)} byte)")
    http_json_request(cfg, f"/api/logs/{rid}/result", "POST", result)


def fetch_log_lines(unit: str, lines: int) -> str:
    """Ambil log layanan: unit journal, atau file SYSLOG/AUTH."""
    if unit == "SYSLOG":
        return _tail_file(SYSLOG_FILE, lines)
    if unit == "AUTH":
        return _tail_file(AUTH_FILE, lines)
    res = _run_cmd(
        ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"],
        timeout=30,
    )
    if res is None:
        return "[gagal menjalankan journalctl]"
    out = res.stdout.rstrip()
    if not out:
        msg = (res.stderr or "").strip()
        return msg or f"[tidak ada entri untuk unit {unit}]"
    return out


def collect_user_logins(max_events: int = 50) -> list:
    """Aktivitas login user dari /var/log/auth.log (sukses/gagal/sesi baru).

    Baca potongan akhir file (±2 MB) agar cepat walau file besar. Cocok untuk
    kartu "Log Aktivitas User" pada Dashboard.
    """
    patterns = [
        ("sukses", re.compile(
            r"Accepted (?P<method>password|publickey|keyboard-interactive|gssapi-with-mic) "
            r"for (?:invalid user )?(?P<user>[\w.-]+) from (?P<from>[\da-fA-F:.]+)")),
        ("gagal", re.compile(
            r"Failed password for (?:invalid user )?(?P<user>[\w.-]+) from (?P<from>[\da-fA-F:.]+)")),
        ("gagal", re.compile(
            r"Invalid user (?P<user>[\w.-]+) from (?P<from>[\da-fA-F:.]+)")),
        ("gagal", re.compile(
            r"Maximum authentication attempts exceeded for (?:invalid user )?"
            r"(?P<user>[\w.-]+) from (?P<from>[\da-fA-F:.]+)")),
        ("sesi", re.compile(r"New session \d+ of user (?P<user>[\w.-]+)\.")),
        ("sudo", re.compile(
            r"sudo(?:\[\d+\])?:\s+(?P<user>[\w.-]+)\s*:\s+.+?USER=\S+\s*;\s*"
            r"COMMAND=(?P<cmd>.+)$")),
    ]
    events: list[dict] = []
    try:
        with open("/var/log/auth.log", "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 8 * 1024 * 1024)
            f.seek(size - chunk)
            data = f.read().decode("utf-8", errors="replace")
    except OSError:
        return events
    for line in data.splitlines():
        ts = line[:19] if len(line) >= 19 else ""
        for kind, regex in patterns:
            m = regex.search(line)
            if not m:
                continue
            g = m.groupdict()
            user = g.get("user", "?")
            if user == "pantau":          # aktivitas agen sendiri = noise
                break
            if "invalid user" in line and kind == "gagal":
                user = "(invalid) " + user
            src = g.get("from") or "(lokal)"
            if kind == "sudo":
                method = g.get("cmd", "")
            else:
                method = g.get("method") or ("ssh" if kind != "sesi" else "console")
            ev = {"ts": ts, "user": user, "type": kind, "from": src, "method": method}
            if events and events[-1] == ev:
                continue
            events.append(ev)
            break
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[: max(0, max_events)]


_security_cache: dict = {"at": 0.0, "data": None}


def collect_security() -> dict:
    """Ringkasan keamanan dari /var/log/auth.log (window ±4 MB terakhir).

    Dipakai indikator 'status masalah' pada Dashboard (serangan/brute force).
    Dihitung maksimal sekali per 60 detik karena auth.log sering ditulis.

    Kembalikan: {"failed", "invalid_users", "source_ips": {ip: n}, "window": [start,end]}
    """
    now = time.monotonic()
    if _security_cache["data"] is not None and now - _security_cache["at"] < 60:
        return _security_cache["data"]

    out: dict = {"failed": 0, "invalid_users": 0, "source_ips": {}, "window": []}
    try:
        with open(AUTH_FILE, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 4 * 1024 * 1024)
            f.seek(size - chunk)
            data = f.read().decode("utf-8", errors="replace")
    except OSError:
        _security_cache["data"] = out
        _security_cache["at"] = now
        return out

    lines = data.splitlines()
    if lines:
        out["window"] = [lines[0][:19], lines[-1][:19]]
    last_ts = None
    for line in lines:
        # "Invalid user" hanya baris info; upaya nyata dihitung dari baris
        # "Failed password"/"Maximum authentication" agar tidak dobel.
        is_invalid = "Invalid user" in line
        is_failed = ("Failed password" in line
                     or "Maximum authentication attempts" in line)
        if not (is_invalid or is_failed):
            continue
        if is_failed:
            out["failed"] += 1
        if is_invalid:
            out["invalid_users"] += 1
        m = re.search(r"from ([\da-fA-F:.]+)", line)
        ip = m.group(1) if m else "?"
        out["source_ips"][ip] = out["source_ips"].get(ip, 0) + 1
        mts = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line) \
            or re.match(r"^(\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2})", line)
        if mts:
            last_ts = mts.group(1)
    if last_ts:
        try:
            if "T" in last_ts:
                _dt = datetime.fromisoformat(last_ts)
            else:
                _dt = datetime.strptime(
                    last_ts + " " + str(datetime.now().year), "%b %d %H:%M:%S %Y")
            # Normalisasi ke UTC agar terbaca absen-tenang yang benar di server
            # yang membandingkan dengan datetime.utcnow() (zona host klien apa pun).
            _dt = _dt.astimezone(timezone.utc).replace(tzinfo=None)
            out["last_seen"] = _dt.isoformat(timespec="seconds")
        except ValueError:
            out.pop("last_seen", None)
    out["source_ips"] = dict(
        sorted(out["source_ips"].items(), key=lambda kv: -kv[1])[:15])
    _security_cache["data"] = out
    _security_cache["at"] = now
    return out


_HIST_EPOCH = re.compile(r"^#(\d{9,11})$")                      # bash: baris before command (#epoch)
_HIST_ZSH = re.compile(r"^: (\d{9,11}):\d*;(.*)$")              # zsh: : <epoch>:<status>;<command>
_HIST_FISH_CMD = re.compile(r"^- cmd:\s*(.*)$")                 # fish: - cmd: <command>
_HIST_FISH_WHEN = re.compile(r"^\s+when:\s*(\d{9,11})$")        # fish:   when: <epoch>


def _parse_history_entries(raw: str) -> list:
    """Parse konten file history (bash/zsh/fish) -> [(epoch|None, command)] urut waktu.

    epoch None = tidak ada timestamp (bash tanpa HISTTIMEFORMAT, atau baris bawaan
    fish tanpa 'when'). Urutan tetap mengikuti baris file (kronologis).
    """
    entries: list = []
    pending_epoch = None
    for ln in raw.splitlines():
        s = ln.rstrip("\r\n")
        if not s:
            continue
        m = _HIST_EPOCH.match(s)
        if m:
            pending_epoch = int(m.group(1))
            continue
        m = _HIST_ZSH.match(s)
        if m:
            cmd = m.group(2).strip()
            if cmd:
                entries.append((int(m.group(1)), cmd))
            continue
        m = _HIST_FISH_CMD.match(s)
        if m:
            cmd = m.group(1).strip()
            if cmd:
                entries.append((None, cmd))
            continue
        m = _HIST_FISH_WHEN.match(s)
        if m and entries and entries[-1][0] is None:
            entries[-1] = (int(m.group(1)), entries[-1][1])
            continue
        if s.startswith("#"):          # komentar/baris penanda tak dikenal
            continue
        cmd = s.strip()
        if not cmd:
            continue
        if pending_epoch is not None:
            entries.append((pending_epoch, cmd))   # bash: timestamp baris previous
            pending_epoch = None
        else:
            entries.append((None, cmd))
    return [e for e in entries if e and e[1]]


def _collect_user_history(user: str, max_lines: int) -> list:
    """Riwayat perintah user (bash/zsh/fish), paling baru di atas.

    Wrapper sudo hanya membaca file history di /home/<user> atau /root;
    format diurai di sini. Setiap entri: {"ts": epoch|None, "cmd": str}.
    """
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,32}", str(user)):
        return []
    res = _run_cmd(["/usr/bin/sudo", "-n", PANTUAN_HISTORY_CMD, str(user)], timeout=15)
    if res is None or res.returncode != 0:
        return []
    entries = _parse_history_entries(res.stdout or "")
    return [{"ts": t, "cmd": c} for t, c in reversed(entries)][:max_lines]


def _tail_file(path: str, lines: int) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 65536)
            f.seek(size - chunk)
            data = f.read().decode("utf-8", errors="replace")
        out = data.splitlines()[-lines:]
        return "\n".join(out)
    except OSError as e:
        return f"[gagal membaca {path}: {e}]"


def poll_log_requests(cfg: dict):
    """Ambil permintaan log antrian dari Dashboard, eksekusi, kirim hasil."""
    code, data = http_json_request(cfg, "/api/logs/pending", "GET")
    if code != 200 or not data:
        return
    requests = data.get("requests", [])[:5]
    for req in requests:
        try:
            rid = int(req["id"])
        except (KeyError, TypeError, ValueError):
            continue
        unit = str(req.get("unit", ""))
        try:
            lines = int(req.get("lines", 200))
        except (TypeError, ValueError):
            lines = 200
        lines = max(10, min(lines, 2000))
        http_json_request(cfg, f"/api/logs/{rid}/status", "POST", {"status": "executing"})

        if not re.fullmatch(r"[A-Za-z0-9@_.:+-]{1,100}", unit):
            result = {"status": "failed", "result": "Nama unit tidak valid"}
        elif unit in ("APT_UPDATE", "APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE", "APT_FIX"):
            threading.Thread(
                target=_run_apt_in_thread, args=(cfg, rid, unit), daemon=True
            ).start()
            continue
        elif unit == "USER_ACTIVITY":
            try:
                username = str(req.get("detail", "") or "")
                logins = [
                    e for e in collect_user_logins(500)
                    if e.get("user") == username
                    or e.get("user", "").endswith(" " + username)
                ]
                history = _collect_user_history(username, lines)
                text = json.dumps({"logins": logins, "history": history})
                result = {"status": "success", "result": text[:60000]}
                print(f"[LOG] Aktivitas user '{username}' -> {result['status']} "
                      f"({len(logins)} login, {len(history)} perintah)")
            except Exception as e:
                result = {"status": "failed", "result": f"[error internal: {e}]"}
        else:
            try:
                text = fetch_log_lines(unit, lines)
                result = {"status": "success", "result": text[:40000]}
            except Exception as e:
                result = {"status": "failed", "result": f"[error internal: {e}]"}
        print(f"[LOG] Log '{unit}' ({lines} baris) -> {result['status']}")
        http_json_request(cfg, f"/api/logs/{rid}/result", "POST", result)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
prev_services: dict[int, str] = {}
last_apt: dict | None = None
_tick = 0


def main():
    print("=" * 60)
    print(f"  Agen Pantau v{AGENT_VERSION} (Production Package)")
    print("=" * 60)

    cfg = load_config()
    server_url = cfg.get("server_url", "")
    if (server_url.startswith("http://")
            and "127.0.0.1" not in server_url
            and "localhost" not in server_url):
        print(
            f"[PERINGATAN KEAMANAN] server_url menggunakan HTTP (bukan HTTPS): {server_url}. "
            "API key dikirim tanpa enkripsi! Pertimbangkan untuk menggunakan HTTPS "
            "dengan reverse proxy (Nginx + TLS) di sisi server."
        )

    print(f"[INFO] Server URL  : {cfg['server_url']}")
    print(f"[INFO] Interval    : {cfg['interval_seconds']} detik")
    print(f"[INFO] Hostname    : {get_hostname()}")
    print(f"[INFO] IP Address  : {get_local_ip()}")
    print(f"[INFO] Mode        : {'root' if IS_ROOT else 'user pantau (sudo ss/wrapper)'}")
    print()

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        print(f"\n[INFO] Signal {sig} diterima, menghentikan agen...")
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    run_once(cfg)

    while running:
        time.sleep(cfg["interval_seconds"])
        if running:
            run_once(cfg)


def run_once(cfg: dict):
    """Muatan satu siklus; error apa pun di-quarantine agar agen tidak mati."""
    try:
        _run_once(cfg)
    except Exception:
        traceback.print_exc()
        print("[ERROR] Satu siklus gagal; agen tetap berjalan.")


def _run_once(cfg: dict):
    global prev_services, last_apt, _tick
    _tick += 1

    # 1. Deteksi services + snapshot kinerja
    services = detect_all_services()
    system = collect_system()

    current_ports = {s["port"]: s["service_name"] for s in services}
    new_ports = set(current_ports) - set(prev_services)
    removed_ports = set(prev_services) - set(current_ports)

    for p in new_ports:
        print(f"  [NEW] Service baru: {current_ports[p]} (port {p})")
    for p in removed_ports:
        print(f"  [GONE] Service hilang: {prev_services[p]} (port {p})")

    prev_services = current_ports

    print(f"  {'Service':15s} {'Port':>6s} {'Status':6s} {'Conns':>5s} {'Resp(ms)':>9s}")
    total_conns = 0
    for s in services:
        total_conns += s["active_connections"]
        print(
            f"  {s['service_name']:15s} {s['port']:>6d} {s['status']:6s} "
            f"{s['active_connections']:>5d} {s['response_time_ms']:>9d}"
        )

    # Akun, unit layanan, dan info apt cukup dilaporkan beberapa siklus sekali
    accounts = units = apt = None
    if _tick % 3 == 1:
        accounts = collect_accounts()
        units = collect_units()
    if _tick % 6 == 2:
        last_apt = collect_apt()
    apt = last_apt

    if send_report(cfg, services, system, accounts, units, apt):
        print(f"[OK] Laporan terkirim ({len(services)} services, {total_conns} conns, "
              f"CPU {system['cpu']:.0f}%)")
    else:
        print("[FAIL] Gagal mengirim laporan")

    # 2. Polling command dari Dashboard
    try:
        poll_and_execute_commands(cfg)
    except Exception as e:
        print(f"[WARN] Polling command error: {e}")

    # 3. Polling permintaan log layanan dari Dashboard
    try:
        poll_log_requests(cfg)
    except Exception as e:
        print(f"[WARN] Polling log error: {e}")

    print()


if __name__ == "__main__":
    main()