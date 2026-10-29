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

import fcntl
import glob
import grp
import hashlib
import http.client
import ipaddress
import json
import os
import platform
import pty
import pwd
import random
import re
import select
import shutil
import signal
import socket
import ssl
import struct
import subprocess
import sys
import termios
import threading
import time
import traceback
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

IS_ROOT = os.geteuid() == 0

ALLOWED_SYSTEMCTL_ACTIONS = frozenset({"restart", "start", "stop", "reload", "enable", "disable"})
VALID_PROCESS_NAME_RE = re.compile(r'^[a-zA-Z0-9@._:\-]{1,64}$')

PANTAU_RESTART = "/usr/local/sbin/pantau-restart"
PANTAU_FIREWALL = "/usr/local/sbin/pantau-firewall"
PANTAU_FILE_CMD = "/usr/local/sbin/pantau-file"
PANTAU_USER_CMD = "/usr/local/sbin/pantau-user"
PANTAU_CRON_CMD = "/usr/local/sbin/pantau-cron"
PANTAU_SSL_CMD = "/usr/local/sbin/pantau-ssl"
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
        "interval_seconds": 5,
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


DEV_TOOL_NAME_HINTS = (
    "mainthread", "code-", "vscode", "electron", "jupyter",
    "chrome", "chromedriver", "google-chrome", "chromium", "selenium", "playwright", "pytest",
)


def is_dev_tool(proc_name: str | None, pid: int | None) -> bool:
    """Filter tools dev (VS Code, Jupyter, test runners, dll) supaya tidak jadi service palsu."""
    if not proc_name:
        return False
    low = proc_name.lower()
    # Deteksi by nama — andal walau /proc milik user lain tidak bisa dibaca
    if any(hint in low for hint in DEV_TOOL_NAME_HINTS):
        return True
    if pid:
        path = get_process_path(pid)
        if ".vscode" in path or "vscode-server" in path:
            return True
        if "node" in path and "/usr/bin" not in path:
            return True
        if any(hint in path.lower() for hint in ("chrome", "chromedriver", "selenium", "playwright")):
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
        "master": "smtpd", "postfix": "smtpd",
        "zabbix_agent2": "zabbix-agent2", "zabbix_agent": "zabbix-agent",
        "zabbix-agent2": "zabbix-agent2", "zabbix-agent": "zabbix-agent",
    }
    lower = name.lower()
    for key, val in mapping.items():
        if key in lower:
            return val
    return name


def get_systemd_unit_from_pid(pid: int | None) -> str | None:
    """Ekstrak nama unit systemd dari /proc/<pid>/cgroup secara akurat."""
    if not pid:
        return None
    try:
        with open(f"/proc/{pid}/cgroup", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.search(r'/([^/]+)\.service', line)
                if m:
                    unit = m.group(1)
                    if not unit.startswith("session-") and not unit.startswith("user@"):
                        return unit
    except Exception:
        pass
    return None


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

        # Cek unit systemd nyata dari PID cgroup untuk akurasi maksimal
        unit_name = get_systemd_unit_from_pid(pid)
        if unit_name:
            proc_name = normalize_process_name(unit_name)
        else:
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
_ssl_ctx = ssl._create_unverified_context() if hasattr(ssl, "_create_unverified_context") else None
_HTTP_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=_ssl_ctx) if _ssl_ctx else urllib.request.HTTPSHandler(),
    _NoRedirect
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
PANTAU_APT_CMD = "/usr/local/sbin/pantau-apt"
PANTAU_HISTORY_CMD = "/usr/local/sbin/pantau-history"
PANTAU_HOST_CMD = "/usr/local/sbin/pantau-host"
PANTAU_SHELL_CMD = "/usr/local/sbin/pantau-shell"

# Kuota output apt update/upgrade (praktis penuh; MEDIUMTEXT baseline 16MB,
# streaming server punya kuota sama).
APT_AGENT_OUTPUT_MAX = 4_000_000

# Tampilan LIVE hanya ekor output (seperti `tail -f`); hasil final tetap penuh.
APT_PROGRESS_TAIL_CHARS = 200_000

# Terminal Bawaan: shell root interaktif milik admin dashboard. Berjalan di pty
# sehingga echo/warna/SIGINT berperilaku seperti SSH.
SHELL_TIMEOUT_SECS = 8 * 3600          # 8 jam; admin boleh stepping away
SHELL_OUTPUT_MAX = 8_000_000           # kuota output satu sesi shell
SHELL_PROGRESS_TAIL_CHARS = 250_000
SHELL_IDLE_POLL_SECS = 0.15            # jeda antar-pendelikan stdin dari dashboard (responsif)
# Shell harus terasa "langsung": kirim output tiap ada perubahan (tahanminimal
# 120ms supaya satu ketikan tidak jadi 10 request), bukan dikelompokkan 1,2 dtk
# seperti apt. Didukung polling 250ms di sisi dashboard.
SHELL_POST_MIN_SECS = 0.12

# Versi agen, dikirim ke dashboard di tiap laporan (badge "agen vX.Y").
AGENT_VERSION = "4.8.36"


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
    body = json.dumps(data).encode("utf-8") if data is not None else None

    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", f"AgentPantau/{AGENT_VERSION}")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Api-Key", cfg["api_key"])

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            try:
                resp_data = json.loads(resp.read().decode() or "{}")
            except Exception:
                resp_data = {}
            return code, resp_data
    except urllib.error.HTTPError as e:
        try:
            resp_data = json.loads(e.read().decode("utf-8", errors="replace") or "{}")
        except Exception:
            resp_data = {}
        return e.code, resp_data
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        return 0, {}
    except Exception:
        return 0, {}


def send_report(cfg: dict, services: list, system: dict,
                accounts: list | None = None, units: list | None = None,
                apt: dict | None = None, packages_changed: bool = False) -> bool:
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
    if packages_changed:
        payload["packages_changed"] = True
    payload["security"] = collect_security()
    payload["cron_jobs"] = collect_cron_jobs()
    payload["firewall"] = collect_firewall()
    payload["listening_ports"] = collect_listening_ports()
    payload["ssl_certs"] = collect_ssl_certs()
    payload["system_logs"] = collect_system_logs()
    payload["hardware_specs"] = collect_hardware_specs()
    payload["groups"] = collect_groups()

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
    elif action == "unblock_ip":
        result = _exec_unblock_ip(command)
    elif action in ("firewall_enable", "firewall_disable", "firewall_reload"):
        result = _exec_firewall_toggle(action)
    elif action == "firewall_port_rule":
        result = _exec_firewall_port_rule(command)
    elif action == "kill_process":
        result = _exec_kill_process(command)
    elif action in ("user_create", "user_lock", "user_unlock", "user_delete", "session_terminate", "terminate_session"):
        result = _exec_user_action(action, command)
    elif action in ("cron_add", "cron_toggle", "cron_delete", "cron_run_now"):
        result = _exec_cron_action(action, command)
    elif action in ("ssl_path_add", "ssl_path_remove"):
        result = _exec_ssl_action(action, command)
    elif action == "restart_agent":
        result = _exec_restart_agent()
    elif action == "update_agent":
        result = _exec_update_agent(cfg, command)
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
            res = _run_native(["/usr/bin/sudo", "-n", PANTAU_FIREWALL, "block", ip],
                              f"sudo -n {PANTAU_FIREWALL} block {ip}")
        if not res["ok"]:
            ok_all = False
        outs.append(f"{ip}: {res['output']}")
    note = " | aturan iptables volatile (hilang saat reboot): utk permanen gunakan iptables-persistent"
    return {"ok": ok_all, "output": ("; ".join(outs) + note)[:2000]}


def _exec_unblock_ip(command: dict) -> dict:
    """Buka blokir IP: iptables -D INPUT -s <ip> -j DROP."""
    params = command.get("params") or {}
    ips = [str(i) for i in (params.get("ips") or [])][:10]
    if not ips:
        return {"ok": False, "output": "Tidak ada IP untuk dibuka blokirnya."}
    outs: list = []
    ok_all = True
    for ip in ips:
        if not _validate_ipv4(ip):
            outs.append(f"{ip}: IP tidak valid / diblokir")
            ok_all = False
            continue
        if IS_ROOT:
            res = _run_native(["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"],
                              f"iptables -D INPUT -s {ip} -j DROP")
        else:
            res = _run_native(["/usr/bin/sudo", "-n", PANTAU_FIREWALL, "unblock", ip],
                              f"sudo -n {PANTAU_FIREWALL} unblock {ip}")
        if not res["ok"]:
            ok_all = False
        outs.append(f"{ip}: {res['output']}")
    return {"ok": ok_all, "output": ("; ".join(outs))[:2000]}


def _exec_firewall_toggle(action: str) -> dict:
    """Aktifkan, nonaktifkan, atau reload firewall UFW via wrapper pantau-firewall."""
    sub_map = {
        "firewall_enable": "enable",
        "firewall_disable": "disable",
        "firewall_reload": "reload",
    }
    sub = sub_map.get(action)
    if not sub:
        return {"ok": False, "output": f"Aksi firewall tidak valid: {action}"}
    if IS_ROOT:
        res = _run_native([PANTAU_FIREWALL, sub], f"{PANTAU_FIREWALL} {sub}")
    else:
        res = _run_native(["/usr/bin/sudo", "-n", PANTAU_FIREWALL, sub],
                          f"sudo -n {PANTAU_FIREWALL} {sub}")
    # Bersihkan cache firewall agar deteksi status langsung diperbarui pada siklus berikutnya
    _fw_cache["at"] = 0.0
    return {"ok": res["ok"], "output": res["output"][:2000]}


def _exec_kill_process(command: dict) -> dict:
    """Hentikan proses tertentu via wrapper pantau-restart kill <pid> <signal>."""
    params = command.get("params") or {}
    pid = str(params.get("pid", "")).strip()
    signal_name = str(params.get("signal", "TERM")).strip().upper()
    if signal_name not in ("TERM", "15", "KILL", "9", "STOP", "19", "CONT", "18"):
        signal_name = "TERM"

    if not pid.isdigit() or int(pid) <= 1:
        return {"ok": False, "output": f"PID tidak valid atau dilindungi: {pid}"}

    # Proteksi tambahan sisi Python: jangan izinkan bunuh PID agen sendiri
    if int(pid) == os.getpid():
        return {"ok": False, "output": "Tidak dapat menghentikan proses agen monitor itu sendiri!"}

    cmd = [PANTAU_RESTART, "kill", pid, signal_name]
    label = f"{PANTAU_RESTART} kill {pid} {signal_name}"
    if not IS_ROOT:
        cmd = ["/usr/bin/sudo", "-n", *cmd]
        label = f"sudo -n {label}"

    res = _run_native(cmd, label)
    # Bersihkan cache proses agar pemindaian berikutnya langsung memuat daftar segar
    _top_procs_cache["at"] = 0.0
    return {"ok": res.get("ok", False), "output": res.get("output", "Gagal mengirim sinyal ke proses")[:2000]}


PANTAU_USER_SCRIPT_BODY = r"""#!/usr/bin/env bash
#
# pantau-user - Wrapper terbatas pengelolaan akun pengguna sistem Linux
# untuk Agen Pantau.
#
# Jalur sudo NOPASSWD berguardrail ketat.
#
set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }

ACTION="${1:-}"
shift 2>/dev/null || true

# Daftar akun terproteksi yang tidak boleh disentuh
is_protected_user() {
    local u="$1"
    case "$u" in
        root|pantau|daemon|bin|sys|sync|games|man|lp|mail|news|uucp|proxy|www-data|backup|list|irc|gnats|nobody|systemd*|_apt|messagebus|sshd)
            return 0
            ;;
    esac
    # Cek UID jika user ada (seluruh akun sistem UID < 1000 termasuk UID 0 dilindungi)
    if id -u "$u" >/dev/null 2>&1; then
        local uid
        uid="$(id -u "$u")"
        if [ "$uid" -lt 1000 ]; then
            return 0
        fi
    fi
    return 1
}

validate_username() {
    local u="$1"
    if [[ ! "$u" =~ ^[a-z_][a-z0-9_-]{1,31}$ ]]; then
        fail "Nama pengguna tidak valid: '$u' (harus diawali huruf kecil/underscore, maks 32 karakter)"
    fi
}

case "$ACTION" in
    create)
        USERNAME="${1:-}"
        SHELL_PATH="${2:-/bin/bash}"
        IS_SUDO="${3:-0}"
        COMMENT="${4:-Dibuat via Pantau Server}"
        PASSWORD="${5:-}"

        [ -n "$USERNAME" ] || fail "Username wajib diisi"
        validate_username "$USERNAME"

        if id "$USERNAME" >/dev/null 2>&1; then
            fail "Pengguna '$USERNAME' sudah ada di sistem"
        fi

        # Validasi shell
        if [ ! -x "$SHELL_PATH" ] && [ "$SHELL_PATH" != "/usr/sbin/nologin" ] && [ "$SHELL_PATH" != "/bin/false" ]; then
            SHELL_PATH="/bin/bash"
        fi

        # Sanitasi komentar GECOS: hapus colon dan newline agar tidak merusak format /etc/passwd
        COMMENT="${COMMENT//:/ }"
        COMMENT="${COMMENT//$'\n'/ }"
        COMMENT="${COMMENT//$'\r'/ }"

        useradd -m -s "$SHELL_PATH" -c "$COMMENT" "$USERNAME" || fail "Gagal membuat pengguna '$USERNAME'"

        if [ -n "$PASSWORD" ]; then
            if [[ "$PASSWORD" == *$'\n'* ]] || [[ "$PASSWORD" == *$'\r'* ]]; then
                fail "Karakter newline pada password tidak diizinkan"
            fi
            echo "${USERNAME}:${PASSWORD}" | chpasswd 2>/dev/null || fail "Gagal mengatur password awal pengguna '$USERNAME'"
        else
            # Best practice POSIX/Linux untuk akun SSH key / tanpa password lokal:
            # Gunakan token unroutable '*' agar akun tidak terkunci disabled ('!') dan dapat di-unlock kapan saja
            usermod -p '*' "$USERNAME" 2>/dev/null || true
        fi

        if [ "$IS_SUDO" = "1" ] || [ "$IS_SUDO" = "true" ]; then
            usermod -aG sudo "$USERNAME" 2>/dev/null || usermod -aG wheel "$USERNAME" 2>/dev/null || true
        fi

        echo "OK: Pengguna '$USERNAME' berhasil dibuat (Shell: $SHELL_PATH, Sudo: $IS_SUDO)"
        ;;

    lock)
        USERNAME="${1:-}"
        [ -n "$USERNAME" ] || fail "Username wajib diisi"
        validate_username "$USERNAME"

        if is_protected_user "$USERNAME"; then
            fail "Pengguna '$USERNAME' adalah akun sistem penting dan dilarang dikunci!"
        fi

        passwd -l "$USERNAME" >/dev/null 2>&1 || usermod -L "$USERNAME" >/dev/null 2>&1 || fail "Gagal mengunci akun '$USERNAME'"
        echo "OK: Akun '$USERNAME' berhasil dikunci"
        ;;

    unlock)
        USERNAME="${1:-}"
        [ -n "$USERNAME" ] || fail "Username wajib diisi"
        validate_username "$USERNAME"

        if is_protected_user "$USERNAME"; then
            fail "Pengguna '$USERNAME' adalah akun sistem penting!"
        fi

        # Deteksi status password di /etc/shadow
        shadow_pwd="$(grep "^${USERNAME}:" /etc/shadow 2>/dev/null | cut -d: -f2 || true)"
        if [ "$shadow_pwd" = "!" ] || [ "$shadow_pwd" = "!*" ] || [ "$shadow_pwd" = "!!" ] || [ -z "$shadow_pwd" ]; then
            usermod -p '*' "$USERNAME" 2>/dev/null || fail "Gagal membuka kunci akun '$USERNAME'"
            echo "OK: Akun '$USERNAME' berhasil dibuka kuncinya"
        else
            if passwd -u "$USERNAME" >/dev/null 2>&1 || usermod -U "$USERNAME" >/dev/null 2>&1; then
                echo "OK: Akun '$USERNAME' berhasil dibuka kuncinya"
            else
                usermod -p '*' "$USERNAME" 2>/dev/null || fail "Gagal membuka kunci akun '$USERNAME'"
                echo "OK: Akun '$USERNAME' berhasil dibuka kuncinya"
            fi
        fi
        ;;

    delete)
        USERNAME="${1:-}"
        REMOVE_HOME="${2:-0}"
        [ -n "$USERNAME" ] || fail "Username wajib diisi"
        validate_username "$USERNAME"

        if is_protected_user "$USERNAME"; then
            fail "Pengguna '$USERNAME' adalah akun sistem terlindungi dan dilarang dihapus!"
        fi

        # Hentikan proses yang masih dijalankan user sebelum dihapus
        pkill -u "$USERNAME" 2>/dev/null || true
        sleep 0.5

        if [ "$REMOVE_HOME" = "1" ] || [ "$REMOVE_HOME" = "true" ]; then
            userdel -r "$USERNAME" 2>/dev/null || userdel "$USERNAME" || fail "Gagal menghapus pengguna '$USERNAME'"
        else
            userdel "$USERNAME" || fail "Gagal menghapus pengguna '$USERNAME'"
        fi

        echo "OK: Pengguna '$USERNAME' berhasil dihapus"
        ;;

    list-locked)
        passwd -Sa 2>/dev/null | awk '$2=="L" || $2=="LK" {print $1}' || true
        ;;

    terminate-session)
        TTY="${1:-}"
        [ -n "$TTY" ] || fail "Parameter TTY wajib diisi (misal: pts/0, pts/1, tty1)"
        TTY="${TTY#/dev/}"
        if [[ ! "$TTY" =~ ^(pts/[0-9]+|tty[0-9]+)$ ]]; then
            fail "Format terminal TTY tidak valid: '$TTY' (hanya pts/N atau ttyN yang diizinkan)"
        fi

        # 1. Hentikan seluruh proses yang terikat dengan terminal tersebut
        pkill -9 -t "$TTY" 2>/dev/null || true
        # 2. Paksa putus descriptor device jika masih menempel
        if [ -e "/dev/$TTY" ]; then
            fuser -k -9 "/dev/$TTY" 2>/dev/null || true
        fi
        echo "OK: Sesi terminal '$TTY' berhasil diputus paksa"
        ;;

    *)
        fail "Aksi tidak dikenal: '$ACTION' (harus create, lock, unlock, delete, list-locked, terminate-session)"
        ;;
esac
"""


def ensure_pantau_user_updated(force: bool = False) -> bool:
    """Memastikan wrapper /usr/local/sbin/pantau-user mendukung fitur terbaru (misal: terminate-session).
    Jika berkas belum ada, versi usang, atau force=True, otomatis perbarui via root langsung atau sudo pantau-file.
    """
    try:
        cur_content = ""
        if not force and os.path.isfile(PANTAU_USER_CMD):
            try:
                with open(PANTAU_USER_CMD, "r", encoding="utf-8", errors="replace") as f:
                    cur_content = f.read()
            except Exception:
                pass
            if "terminate-session" in cur_content:
                return True

        content_to_write = PANTAU_USER_SCRIPT_BODY.strip() + "\n"
        if IS_ROOT:
            with open(PANTAU_USER_CMD, "w", encoding="utf-8") as f:
                f.write(content_to_write)
            os.chmod(PANTAU_USER_CMD, 0o750)
            print("[USER] Wrapper /usr/local/sbin/pantau-user berhasil diperbarui (root)")
            return True

        # Jika user 'pantau', gunakan sudo pantau-file jika tersedia
        pantau_file = "/usr/local/sbin/pantau-file"
        if os.path.isfile(pantau_file):
            payload_write = json.dumps({
                "action": "write",
                "params": {"path": PANTAU_USER_CMD, "content": content_to_write, "make_backup": False}
            })
            pw = subprocess.run(["/usr/bin/sudo", "-n", pantau_file], input=payload_write, text=True, capture_output=True, timeout=10)
            try:
                out_data = json.loads(pw.stdout or "{}")
            except Exception:
                out_data = {}
            if pw.returncode == 0 and out_data.get("ok"):
                payload_chmod = json.dumps({
                    "action": "chmod",
                    "params": {"path": PANTAU_USER_CMD, "mode": "0750"}
                })
                subprocess.run(["/usr/bin/sudo", "-n", pantau_file], input=payload_chmod, text=True, capture_output=True, timeout=10)
                print("[USER] Wrapper /usr/local/sbin/pantau-user berhasil diperbarui via pantau-file")
                return True
    except Exception as e:
        print(f"[USER WARN] Gagal memperbarui {PANTAU_USER_CMD}: {e}")
    return False


def _exec_user_action(action: str, command: dict) -> dict:
    """Kelola akun pengguna sistem & pemutusan sesi terminal via wrapper pantau-user."""
    ensure_pantau_user_updated()
    params = command.get("params") or {}
    if action in ("session_terminate", "terminate_session"):
        tty = str(params.get("tty", "")).strip().lstrip("/dev/")
        if not tty:
            return {"ok": False, "output": "Parameter TTY terminal (misal: pts/0) wajib diisi."}
        if not re.match(r"^(pts/\d+|tty\d+)$", tty):
            return {"ok": False, "output": f"Format terminal TTY '{tty}' tidak valid (hanya pts/N atau ttyN)."}
        cmd = [PANTAU_USER_CMD, "terminate-session", tty]
        label = f"{PANTAU_USER_CMD} terminate-session {tty}"
        if not IS_ROOT:
            cmd = ["/usr/bin/sudo", "-n", *cmd]
            label = f"sudo -n {label}"
        res = _run_native(cmd, label)
        # Jika wrapper lama di disk menolak aksi karena belum terbarui, paksa pembaruan mandiri lalu coba lagi sekali
        if not res.get("ok") and "Aksi tidak dikenal" in res.get("output", ""):
            print("[USER] Terdeteksi pantau-user versi lama, memperbarui paksa wrapper dan mengulang...")
            if ensure_pantau_user_updated(force=True):
                res = _run_native(cmd, label)
        return {"ok": res.get("ok", False), "output": res.get("output", "")[:2000]}

    username = str(params.get("username", "")).strip().lower()
    if not username:
        return {"ok": False, "output": "Nama pengguna (username) wajib diisi."}

    cmd = [PANTAU_USER_CMD]
    if action == "user_create":
        shell = str(params.get("shell", "/bin/bash")).strip()
        is_sudo = "1" if params.get("is_sudo") in (1, True, "1", "true") else "0"
        comment = str(params.get("comment", "Dibuat via Pantau Server")).strip()
        password = str(params.get("password", "")).strip()
        cmd.extend(["create", username, shell, is_sudo, comment, password])
    elif action == "user_lock":
        cmd.extend(["lock", username])
    elif action == "user_unlock":
        cmd.extend(["unlock", username])
    elif action == "user_delete":
        remove_home = "1" if params.get("remove_home") in (1, True, "1", "true") else "0"
        cmd.extend(["delete", username, remove_home])
    else:
        return {"ok": False, "output": f"Aksi pengguna tidak valid: {action}"}

    display_cmd = list(cmd)
    if action == "user_create" and len(display_cmd) >= 7 and display_cmd[6]:
        display_cmd[6] = "******"
    label = " ".join(display_cmd)
    if not IS_ROOT:
        cmd = ["/usr/bin/sudo", "-n", *cmd]
        label = f"sudo -n {label}"

    res = _run_native(cmd, label)
    return {"ok": res.get("ok", False), "output": res.get("output", "")[:2000]}


def _exec_cron_action(action: str, command: dict) -> dict:
    """Kelola tugas terjadwal (cron) via wrapper pantau-cron."""
    params = command.get("params") or {}
    cmd = [PANTAU_CRON_CMD]

    if action == "cron_add":
        ident = str(params.get("ident", "")).strip()
        minute = str(params.get("minute", "*")).strip()
        hour = str(params.get("hour", "*")).strip()
        dom = str(params.get("dom", "*")).strip()
        month = str(params.get("month", "*")).strip()
        dow = str(params.get("dow", "*")).strip()
        target_user = str(params.get("user", "root")).strip()
        cron_cmd = str(params.get("command", "")).strip()
        if not ident or not cron_cmd:
            return {"ok": False, "output": "Identifikasi tugas dan perintah cron wajib diisi."}
        cmd.extend(["add", ident, minute, hour, dom, month, dow, target_user, cron_cmd])
    elif action == "cron_toggle":
        ident = str(params.get("ident", "")).strip()
        mode = str(params.get("mode", "enable")).strip().lower()
        if not ident:
            return {"ok": False, "output": "Identifikasi tugas cron wajib diisi."}
        cmd.extend(["toggle", ident, mode])
    elif action == "cron_delete":
        ident = str(params.get("ident", "")).strip()
        if not ident:
            return {"ok": False, "output": "Identifikasi tugas cron wajib diisi."}
        cmd.extend(["delete", ident])
    elif action == "cron_run_now":
        target_user = str(params.get("user", "root")).strip()
        cron_cmd = str(params.get("command", "")).strip()
        if not cron_cmd:
            return {"ok": False, "output": "Perintah cron wajib diisi."}
        cmd.extend(["run", target_user, cron_cmd])
    else:
        return {"ok": False, "output": f"Aksi cron tidak valid: {action}"}

    label = " ".join(cmd)
    if not IS_ROOT:
        cmd = ["/usr/bin/sudo", "-n", *cmd]
        label = f"sudo -n {label}"

    res = _run_native(cmd, label)
    _cron_cache["at"] = 0.0
    return {"ok": res.get("ok", False), "output": res.get("output", "")[:2000]}


def _exec_firewall_port_rule(command: dict) -> dict:
    """Atur aturan buka/tutup port firewall via wrapper pantau-firewall."""
    params = command.get("params") or {}
    port_spec = str(params.get("port", "")).strip()
    rule_type = str(params.get("rule", "deny")).strip().lower()
    if not port_spec:
        return {"ok": False, "output": "Spesifikasi port wajib diisi."}

    sub = "deny-port" if rule_type in ("deny", "block", "deny-port") else "allow-port"
    cmd = [PANTAU_FIREWALL, sub, port_spec]
    label = f"{PANTAU_FIREWALL} {sub} {port_spec}"
    if not IS_ROOT:
        cmd = ["/usr/bin/sudo", "-n", *cmd]
        label = f"sudo -n {label}"

    res = _run_native(cmd, label)
    _fw_cache["at"] = 0.0
    return {"ok": res.get("ok", False), "output": res.get("output", "")[:2000]}


def _exec_ssl_action(action: str, command: dict) -> dict:
    """Kelola path berkas sertifikat SSL kustom via wrapper pantau-ssl."""
    params = command.get("params") or {}
    cert_path = str(params.get("path", "")).strip()
    if not cert_path:
        return {"ok": False, "output": "Path berkas sertifikat SSL wajib diisi."}

    sub = "add-path" if action == "ssl_path_add" else "remove-path"
    cmd = [PANTAU_SSL_CMD, sub, cert_path]
    label = f"{PANTAU_SSL_CMD} {sub} {cert_path}"
    if not IS_ROOT:
        cmd = ["/usr/bin/sudo", "-n", *cmd]
        label = f"sudo -n {label}"

    res = _run_native(cmd, label)
    _ssl_cache["at"] = 0.0
    return {"ok": res.get("ok", False), "output": res.get("output", "")[:2000]}


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
            p = subprocess.run([PANTAU_HOST_CMD, *args],
                               capture_output=True, text=True, timeout=30)
        else:
            p = subprocess.run(["/usr/bin/sudo", "-n", PANTAU_HOST_CMD, *args],
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
        # Deteksi false positive dari wrapper pantau-host versi lama pada sistem dengan status degraded.
        # Jika /run/systemd/system ada, systemd aktif dan siap menerima reboot/poweroff (termasuk pada Proxmox LXC).
        if os.path.isdir("/run/systemd/system"):
            try:
                new_host_script = (
                    "#!/usr/bin/env bash\n"
                    "set -u\n"
                    'ACTION="${1:-}"\n'
                    'LOG="/var/log/pantau-host.log"\n'
                    "fail() { echo \"$*\" >&2; echo \"FAIL $(date -Is) [${ACTION}] $*\" >> \"$LOG\" 2>/dev/null; exit 1; }\n"
                    'case "$ACTION" in\n'
                    '    reboot)   CMD="/usr/bin/systemctl -i reboot || /usr/bin/systemctl --force reboot || /sbin/reboot -f || /sbin/shutdown -r now || /sbin/init 6" ;;\n'
                    '    poweroff) CMD="/usr/bin/systemctl -i poweroff || /usr/bin/systemctl --force poweroff || /sbin/poweroff -f || /sbin/shutdown -h now || /sbin/init 0" ;;\n'
                    '    check)    CMD="" ;;\n'
                    '    *)        fail "Aksi tidak dikenal: \'${ACTION}\'" ;;\n'
                    "esac\n"
                    "[ -x /usr/bin/systemctl ] || fail \"/usr/bin/systemctl tidak ditemukan\"\n"
                    'mkdir -p "$(dirname "$LOG")" 2>/dev/null || true\n'
                    'if [ -z "$CMD" ]; then\n'
                    '    echo "INFO $(date -Is) [check] dipanggil oleh: ${SUDO_USER:-<langsung>}" >> "$LOG" 2>/dev/null\n'
                    "    if [ -d /run/systemd/system ]; then\n"
                    "        state=\"$(/usr/bin/systemctl is-system-running 2>/dev/null || echo 'active')\"\n"
                    "        echo \"systemd OK ($state) — siap terima reboot|poweroff.\"\n"
                    "        exit 0\n"
                    "    fi\n"
                    "    echo \"systemd TIDAK berjalan sebagai host (mis. container/WSL) — reboot/poweroff TIDAK akan mematikan mesin ini.\"\n"
                    "    exit 0\n"
                    "fi\n"
                    'echo "INFO $(date -Is) [${ACTION}] mengeksekusi: $CMD" >> "$LOG" 2>/dev/null\n'
                    '/bin/sh -c "$CMD"\n'
                    "rc=$?\n"
                    '[ $rc -ne 0 ] && fail "gagal (rc=$rc): $CMD"\n'
                    'echo "OK: $ACTION dieksekusi."\n'
                )
                run_file_op("write", {"path": PANTAU_HOST_CMD, "content": new_host_script})
                run_file_op("chmod", {"path": PANTAU_HOST_CMD, "mode": "0755"})
            except Exception:
                pass
        else:
            return {"ok": False,
                    "output": f"Perintah {sub_action} DIBATALKAN: {msg_check}"}

    label = f"{PANTAU_HOST_CMD} {sub_action}"
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


def _exec_update_agent(cfg: dict, command: dict) -> dict:
    """Unduh dan pasang pembaruan agent_pantau.py secara otomatis dan aman (Enterprise OTA Update).

    Alur Keamanan & Kriptografi:
    1. Baca instruksi OTA (target URL & hash SHA-256 yang diharapkan dari dashboard).
    2. Unduh berkas biner/skrip agen baru ke memori/berkas sementara.
    3. Validasi kriptografi SHA-256: hitung hashlib.sha256(unduhan). Jika berbeda dari expected,
       TOLAK SEKETIKA (mencegah manipulasi/peretasan/berkas korup).
    4. Validasi sintaks Python dengan py_compile.compile. Jika sintaks korup, batalkan.
    5. Ganti berkas target (/opt/pantau/agent/agent_pantau.py) secara atomik (mode 0755).
    6. Jadwalkan restart otomatis (_exec_restart_agent) via systemd watchdog.
    """
    params = command.get("params") or {}
    expected_sha256 = str(params.get("sha256") or "").strip().lower()
    target_url = str(params.get("url") or "").strip()
    target_version = str(params.get("version") or "").strip()

    server_url = str(cfg.get("server_url", "")).rstrip("/")
    api_key = str(cfg.get("api_key", ""))
    urls = []
    if target_url:
        urls.append(target_url)
    if server_url:
        urls.append(f"{server_url}/api/agent/latest-code")
    urls.append("https://raw.githubusercontent.com/azhuka/pantau-server/master/package/opt/pantau/agent/agent_pantau.py")

    # Hilangkan duplikasi URL
    seen_urls = set()
    unique_urls = []
    for u in urls:
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique_urls.append(u)

    code_bytes = None
    fetch_err = []
    for url in unique_urls:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": f"AgentPantau/{AGENT_VERSION}",
                    "X-Api-Key": api_key,
                }
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 10000 and b"AGENT_VERSION" in data:
                        code_bytes = data
                        print(f"[OTA] Berhasil mengunduh berkas agen dari {url} ({len(data)} bytes)")
                        break
                    else:
                        fetch_err.append(f"{url}: ukuran/isi tidak valid ({len(data)} bytes)")
                else:
                    fetch_err.append(f"{url}: HTTP {resp.status}")
        except Exception as e:
            fetch_err.append(f"{url}: {e}")

    if not code_bytes:
        return {
            "ok": False,
            "output": f"Gagal mengunduh berkas agen terbaru: {'; '.join(fetch_err)}"
        }

    # Verifikasi Kriptografis SHA-256 wajib dan mutlak
    if not expected_sha256 or len(expected_sha256) != 64 or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256.lower()):
        return {
            "ok": False,
            "output": "Pembaruan ditolak: Hash SHA-256 target wajib disertakan oleh dashboard (64 karakter hex)."
        }

    actual_sha256 = hashlib.sha256(code_bytes).hexdigest().lower()
    if actual_sha256 != expected_sha256.lower():
        msg = (
            f"Verifikasi integritas SHA-256 GAGAL! Hash unduhan ({actual_sha256}) "
            f"tidak cocok dengan instruksi dashboard ({expected_sha256}). "
            "Pembaruan dibatalkan demi mencegah eksekusi berkas tidak terverifikasi."
        )
        print(f"[SECURITY ALERT] {msg}")
        return {"ok": False, "output": msg}
    print(f"[OTA] Integritas SHA-256 terverifikasi: {actual_sha256}")

    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="pantau_ota_", suffix=".py")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(code_bytes)
            f.flush()
            os.fsync(f.fileno())

        # Validasi 1: Uji kompilasi sintaks Python in-memory
        try:
            compile(code_bytes, tmp_path, "exec")
        except Exception as se:
            return {
                "ok": False,
                "output": f"Pembaruan ditolak: Validasi sintaks Python gagal: {se}"
            }

        # Validasi 2: Pre-flight isolated runtime execution check
        # Jalankan subproses terisolasi untuk memastikan modul dapat dimuat interpreter
        # tanpa NameError, ImportError, atau SyntaxError, dan keluar seketika dengan code 0.
        try:
            test_proc = subprocess.run(
                [sys.executable, tmp_path, "--test-runtime"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if test_proc.returncode != 0:
                err_detail = (test_proc.stderr or test_proc.stdout or f"exit code {test_proc.returncode}").strip()
                print(f"[OTA REJECTED] Pre-flight runtime check gagal (exit {test_proc.returncode}): {err_detail}")
                return {
                    "ok": False,
                    "output": (
                        f"Pembaruan ditolak: Pre-flight runtime check gagal (exit code {test_proc.returncode}). "
                        f"Berkas target aman dan tidak disentuh. Detail: {err_detail[:400]}"
                    )
                }
            print(f"[OTA] Pre-flight runtime check sukses: {test_proc.stdout.strip()}")
        except subprocess.TimeoutExpired:
            print("[OTA REJECTED] Pre-flight runtime check timeout (>15 detik)")
            return {
                "ok": False,
                "output": "Pembaruan ditolak: Pre-flight runtime check timeout (>15 detik). Berkas target tidak disentuh."
            }
        except Exception as e:
            print(f"[OTA REJECTED] Eksekusi pre-flight runtime check gagal: {e}")
            return {
                "ok": False,
                "output": f"Pembaruan ditolak: Eksekusi pre-flight runtime check gagal ({e}). Berkas target tidak disentuh."
            }

        try:
            code_str = code_bytes.decode("utf-8", errors="replace")
            ver_match = re.search(r'AGENT_VERSION\s*=\s*["\']([^"\']+)["\']', code_str)
            new_version = ver_match.group(1) if ver_match else (target_version or "baru")
        except Exception:
            code_str = code_bytes.decode("utf-8", errors="replace")
            new_version = target_version or "baru"

        target_path = "/opt/pantau/agent/agent_pantau.py"
        script_path = os.path.abspath(__file__)
        if not os.path.exists(target_path) and os.path.exists(script_path):
            target_path = script_path

        target_dir = os.path.dirname(target_path)
        backup_path = f"{target_path}.bak"

        # -----------------------------------------------------------------
        # Atomic Backup: Amankan berkas aktif yang saat ini berjalan ke .bak
        # -----------------------------------------------------------------
        if os.path.exists(target_path):
            backup_ok = False
            backup_err = ""
            if IS_ROOT or (os.path.exists(target_dir) and os.access(target_dir, os.W_OK)):
                try:
                    tmp_bak = f"{backup_path}.tmp.{os.getpid()}"
                    with open(target_path, "rb") as rf, open(tmp_bak, "wb") as wf:
                        wf.write(rf.read())
                        wf.flush()
                        os.fsync(wf.fileno())
                    os.chmod(tmp_bak, 0o755)
                    os.replace(tmp_bak, backup_path)
                    backup_ok = True
                    print(f"[OTA] Cadangan berkas aktif dibuat di {backup_path}")
                except Exception as be:
                    backup_err = str(be)
                    print(f"[OTA] Gagal membuat cadangan langsung: {be}")

            if not backup_ok:
                try:
                    with open(target_path, "r", encoding="utf-8", errors="replace") as cur_f:
                        cur_content = cur_f.read()
                    res_bak = run_file_op("write", {"path": backup_path, "content": cur_content})
                    if res_bak.get("ok"):
                        run_file_op("chmod", {"path": backup_path, "mode": "0755"})
                        backup_ok = True
                        print(f"[OTA] Cadangan berkas aktif dibuat via pantau-file di {backup_path}")
                    else:
                        backup_err = res_bak.get("error", "pantau-file error")
                        print(f"[OTA] Peringatan pantau-file backup: {backup_err}")
                except Exception as be:
                    backup_err = str(be)
                    print(f"[OTA] Peringatan pembuatan cadangan: {be}")

            # Validasi kesehatan file cadangan yang baru saja dibuat
            if backup_ok and os.path.exists(backup_path):
                try:
                    chk_bak = subprocess.run(
                        [sys.executable, backup_path, "--test-runtime"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if chk_bak.returncode != 0:
                        backup_ok = False
                        backup_err = f"Uji integritas berkas cadangan gagal (exit code {chk_bak.returncode})"
                except Exception as che:
                    backup_ok = False
                    backup_err = f"Uji integritas berkas cadangan gagal: {che}"

            if not backup_ok:
                return {
                    "ok": False,
                    "output": (
                        f"Pembaruan ditolak: Gagal membuat cadangan berkas aktif ({backup_err}). "
                        "Berkas target aman dan tidak disentuh demi perlindungan anti-bricking."
                    )
                }

        written = False
        if IS_ROOT or (os.path.exists(target_dir) and os.access(target_dir, os.W_OK)):
            try:
                tmp_target = f"{target_path}.tmp.{os.getpid()}"
                with open(tmp_target, "wb") as wf:
                    wf.write(code_bytes)
                    wf.flush()
                    os.fsync(wf.fileno())
                os.chmod(tmp_target, 0o755)
                os.replace(tmp_target, target_path)
                written = True
            except OSError as e:
                print(f"[OTA] Tulis langsung gagal ({e}), beralih ke wrapper pantau-file...")

        if not written:
            res_write = run_file_op("write", {"path": target_path, "content": code_str})
            if not res_write.get("ok"):
                return {
                    "ok": False,
                    "output": f"Gagal menulis berkas agen ke {target_path}: {res_write.get('error', 'unknown error')}"
                }
            run_file_op("chmod", {"path": target_path, "mode": "0755"})
            written = True

        # -----------------------------------------------------------------
        # Verifikasi Pasca-Tulis & Auto-Rollback:
        # -----------------------------------------------------------------
        post_check_ok = False
        post_err_detail = ""
        try:
            post_check = subprocess.run(
                [sys.executable, target_path, "--test-runtime"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if post_check.returncode == 0:
                post_check_ok = True
            else:
                post_err_detail = (post_check.stderr or post_check.stdout or f"exit code {post_check.returncode}").strip()
        except subprocess.TimeoutExpired:
            post_err_detail = "Pre-flight runtime check pasca-tulis timeout (>15 detik)"
        except Exception as pce:
            post_err_detail = f"Eksekusi uji pasca-tulis gagal: {pce}"

        if not post_check_ok:
            print(f"[OTA ERROR] Verifikasi pasca-tulis gagal ({post_err_detail}). Memulai auto-rollback...")
            rollback_done = False
            candidate_backups = [backup_path]
            if os.path.exists(target_dir):
                try:
                    ts_baks = sorted(glob.glob(f"{target_path}.bak.*"), reverse=True)
                    candidate_backups.extend(ts_baks)
                except Exception:
                    pass

            for cand_bak in candidate_backups:
                if not os.path.exists(cand_bak):
                    continue
                try:
                    chk = subprocess.run(
                        [sys.executable, cand_bak, "--test-runtime"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if chk.returncode != 0:
                        continue
                except Exception:
                    continue

                if IS_ROOT or (os.path.exists(target_dir) and os.access(target_dir, os.W_OK)):
                    try:
                        tmp_rb = f"{target_path}.rollback.{os.getpid()}"
                        with open(cand_bak, "rb") as rf, open(tmp_rb, "wb") as wf:
                            wf.write(rf.read())
                            wf.flush()
                            os.fsync(wf.fileno())
                        os.chmod(tmp_rb, 0o755)
                        os.replace(tmp_rb, target_path)
                        rollback_done = True
                        print(f"[OTA] Berhasil rollback target ke cadangan sehat {cand_bak}")
                        break
                    except Exception as rbe:
                        print(f"[OTA] Gagal rollback langsung ke {cand_bak}: {rbe}")

                if not rollback_done:
                    try:
                        with open(cand_bak, "r", encoding="utf-8", errors="replace") as bf:
                            bak_content = bf.read()
                        res_rb = run_file_op("write", {"path": target_path, "content": bak_content})
                        if res_rb.get("ok"):
                            run_file_op("chmod", {"path": target_path, "mode": "0755"})
                            rollback_done = True
                            print(f"[OTA] Berhasil rollback via pantau-file ke {cand_bak}")
                            break
                    except Exception as rbe:
                        print(f"[OTA] Gagal rollback pantau-file: {rbe}")

            return {
                "ok": False,
                "output": (
                    f"Pembaruan gagal saat verifikasi integritas target ({post_err_detail[:200]}). "
                    f"{'Rollback instan ke cadangan sehat berhasil.' if rollback_done else 'Rollback darurat gagal.'}"
                )
            }

        # Sanitasi dan perbarui unit service systemd jika masih memakai direktif sandbox usang
        # atau belum memiliki ExecStartPre auto-recovery multi-layer.
        clean_service_unit = (
            "[Unit]\n"
            "Description=Pantau Monitoring Agent (agent_pantau)\n"
            "Wants=network-online.target\n"
            "After=network-online.target\n"
            "StartLimitIntervalSec=0\n\n"
            "[Service]\n"
            "Type=simple\n"
            "User=pantau\n"
            "Group=pantau\n"
            "ExecStartPre=+-/bin/sh -c 'if [ ! -f /opt/pantau/agent/agent_pantau.py ] || ! /usr/bin/python3 /opt/pantau/agent/agent_pantau.py --test-runtime >/dev/null 2>&1; then found_bak=\"\"; for b in /opt/pantau/agent/agent_pantau.py.bak $(ls -t /opt/pantau/agent/agent_pantau.py.bak.* 2>/dev/null); do if [ -f \"$b\" ] && /usr/bin/python3 \"$b\" --test-runtime >/dev/null 2>&1; then found_bak=\"$b\"; break; fi; done; if [ -n \"$found_bak\" ]; then logger -t agent_pantau \"Auto-rollback: file utama rusak/hilang, memulihkan dari cadangan $found_bak\"; cp -f \"$found_bak\" /opt/pantau/agent/agent_pantau.py && chmod 755 /opt/pantau/agent/agent_pantau.py; fi; fi'\n"
            "ExecStart=/opt/pantau/agent/agent_pantau.py\n"
            "Restart=always\n"
            "RestartSec=5\n"
            "Nice=5\n"
            "StandardOutput=journal\n"
            "StandardError=journal\n\n"
            "# CATATAN ARSITEKTUR KEAMANAN:\n"
            "# Isolasi mount namespace (PrivateTmp, ProtectSystem, ProtectKernel*, dll.) sengaja tidak digunakan.\n"
            "# Sesuai standar Linux & systemd, direktif tersebut secara otomatis memaksa kernel menyematkan flag\n"
            "# PR_SET_NO_NEW_PRIVS pada Linux Container (LXC/Proxmox CT unprivileged), yang akan memblokir eskalasi\n"
            "# sudo oleh biner wrapper. Keamanan agen sepenuhnya dijamin oleh isolasi user 'pantau' (tanpa shell login)\n"
            "# dan pembatasan ketat whitelist perintah pada /etc/sudoers.d/pantau-agent.\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )
        svc_path = "/etc/systemd/system/agent_pantau.service"
        needs_reload = False
        try:
            if os.path.exists(svc_path):
                curr_svc = ""
                try:
                    with open(svc_path, "r", encoding="utf-8", errors="replace") as sf:
                        curr_svc = sf.read()
                except Exception:
                    pass
                sandbox_keywords = (
                    "ProtectKernelModules", "PrivateTmp", "ProtectKernelTunables",
                    "ProtectControlGroups", "ProtectClock", "\nEOF"
                )
                if any(k in curr_svc for k in sandbox_keywords) or "found_bak" not in curr_svc:
                    print("[OTA] Konfigurasi isolasi namespace usang atau ExecStartPre multi-layer belum terpasang, memperbarui...")
                    if IS_ROOT:
                        with open(svc_path, "w", encoding="utf-8") as sf:
                            sf.write(clean_service_unit)
                        os.chmod(svc_path, 0o644)
                        needs_reload = True
                    else:
                        rw = run_file_op("write", {"path": svc_path, "content": clean_service_unit})
                        if rw.get("ok"):
                            run_file_op("chmod", {"path": svc_path, "mode": "0644"})
                            needs_reload = True
        except Exception as e:
            print(f"[OTA] Peringatan saat sanitasi service unit: {e}")

        if needs_reload:
            try:
                if IS_ROOT:
                    subprocess.run(["systemctl", "daemon-reload"], timeout=10)
                elif os.path.exists(PANTAU_CRON_CMD):
                    subprocess.run(["/usr/bin/sudo", "-n", PANTAU_CRON_CMD, "run", "root", "systemctl daemon-reload"], timeout=10)
                elif os.path.exists(PANTAU_SHELL_CMD):
                    subprocess.run(["/usr/bin/sudo", "-n", PANTAU_SHELL_CMD], input="systemctl daemon-reload\nexit\n", text=True, timeout=10)
                print("[OTA] systemctl daemon-reload berhasil dieksekusi.")
            except Exception as e:
                print(f"[OTA] Gagal reload systemd daemon: {e}")

        try:
            ensure_pantau_user_updated(force=True)
            ensure_pantau_apt_updated()
        except Exception as we:
            print(f"[OTA] Peringatan saat pembaruan wrapper mandiri: {we}")

        _exec_restart_agent()

        return {
            "ok": True,
            "output": f"Push OTA sukses ke v{new_version} (SHA-256: {actual_sha256[:12]}… terverifikasi). Restart otomatis dijadwalkan."
        }
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _exec_service_action(action: str, command: dict) -> dict:
    process_name = command.get("process_name", "")
    service_name = command.get("service_name", "")

    if action not in ALLOWED_SYSTEMCTL_ACTIONS:
        return {"ok": False, "output": f"Aksi tidak diizinkan: {action}"}

    candidates = []
    for name in (process_name, service_name):
        if name and VALID_PROCESS_NAME_RE.match(name) and name not in candidates:
            candidates.append(name)
        if name and "_" in name:
            hyphen_name = name.replace("_", "-")
            if VALID_PROCESS_NAME_RE.match(hyphen_name) and hyphen_name not in candidates:
                candidates.append(hyphen_name)

    if not candidates:
        return {"ok": False, "output": "Nama proses/service kosong atau tidak valid"}

    last_res = None
    for cand in candidates:
        cmd = [PANTAU_RESTART, action, cand]
        label = f"{PANTAU_RESTART} {action} {cand}"
        if not IS_ROOT:
            cmd = ["/usr/bin/sudo", "-n", *cmd]
            label = f"sudo -n {label}"
        last_res = _run_native(cmd, label)
        if last_res.get("ok"):
            return last_res

    return last_res or {"ok": False, "output": f"Gagal mengeksekusi {action} pada {candidates}"}



def _run_native(cmd: list[str], label: str) -> dict:
    """Jalankan command dan kembalikan {'ok': bool, 'output': str}."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        ok = proc.returncode == 0
        stdout_clean = (proc.stdout or "").strip()
        stderr_clean = (proc.stderr or "").strip()
        if not ok and stderr_clean:
            output = f"{stderr_clean}\n{stdout_clean}".strip() if stdout_clean else stderr_clean
        else:
            output = stdout_clean or stderr_clean
        return {
            "ok": ok,
            "output": output or f"{label} rc={proc.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"Timeout eksekusi: {label}"}
    except FileNotFoundError as e:
        return {"ok": False, "output": f"Perintah tidak tersedia: {e}"}
    except Exception as e:
        return {"ok": False, "output": f"Gagal mengeksekusi {label}: {e}"}


def report_command_result(cfg: dict, command_id: int, result: dict):
    """Lapor hasil eksekusi command ke Dashboard."""
    status = "success" if result["ok"] else "failed"
    http_json_request(
        cfg, f"/api/commands/{command_id}/result", "POST",
        {"status": status, "result": result["output"][:2000]},
    )


def poll_and_execute_commands(cfg: dict) -> bool:
    """Cek command pending lalu eksekusi satu per satu. Return True bila ada aksi yang dieksekusi."""
    commands = check_pending_commands(cfg)
    executed = False
    for cmd in commands:
        result = execute_command(cfg, cmd)
        report_command_result(cfg, cmd["id"], result)
        executed = True
    return executed


def _command_worker_loop(cfg: dict) -> None:
    """Worker background untuk merespons dan mengeksekusi perintah kontrol layanan seketika (1.0 dtk)."""
    while True:
        try:
            had_cmd = poll_and_execute_commands(cfg)
            if had_cmd:
                try:
                    # Beri jeda sangat singkat (300ms) agar systemd merampungkan transisi status,
                    # lalu segera kirim laporan telemetri terbaru ke server tanpa menunggu interval siklus utama
                    time.sleep(0.3)
                    run_once(cfg)
                except Exception as e:
                    print(f"[WARN] Gagal kirim laporan instan pasca-command: {e}")
        except Exception:
            pass
        time.sleep(1.0)


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
_disk_prev: dict[str, dict] = {}
_disk_prev_t: float = 0.0
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


def _find_storage_bin(name: str) -> str | None:
    p = shutil.which(name)
    if p and os.path.isfile(p):
        return p
    for candidate in (f"/usr/sbin/{name}", f"/usr/bin/{name}", f"/sbin/{name}", f"/bin/{name}", f"/usr/local/sbin/{name}"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def collect_disk_smart_health(disk_name: str, disk_model: str = "", platform_type: str = "") -> dict:
    """Kumpulkan status kesehatan S.M.A.R.T. / NVMe, suhu, dan sisa umur drive."""
    res = {
        "is_virtual": False,
        "health": "healthy",
        "status_label": "PASSED",
        "temp_c": None,
        "wearout_pct": None,
        "wearout_remaining": None,
        "reallocated_sectors": None,
        "power_on_hours": None,
        "device_type": "disk",
        "serial": "",
        "firmware": "",
        "detail": "Normal",
    }

    # 1. Cek disk virtual (LXC rootfs, QEMU, VirtIO, VMWare, dsb.)
    name_clean = disk_name.lower().strip()
    model_clean = (disk_model or "").upper()
    is_virt = False

    if name_clean == "rootfs" or platform_type in ("lxc", "docker", "podman", "container"):
        is_virt = True
    elif any(vk in model_clean for vk in ("QEMU", "VBOX", "VMWARE", "VIRTIO", "XEN", "KVM", "BOCHS", "BHYVE", "CONTAINER", "VIRTUAL")):
        is_virt = True
    elif platform_type == "vm" and model_clean in ("HARDDISK", "DISK", "VIRTUAL DISK", ""):
        is_virt = True
    else:
        sys_path = f"/sys/block/{disk_name}"
        if os.path.islink(sys_path):
            try:
                target = os.readlink(sys_path)
                if "virtio" in target or "/virtual/" in target:
                    is_virt = True
            except Exception:
                pass

    if is_virt:
        res["is_virtual"] = True
        res["health"] = "healthy"
        res["status_label"] = "Virtual (Host)"
        res["device_type"] = "virtual"
        res["detail"] = "Virtual (Host Managed)"
        return res

    dev_path = f"/dev/{disk_name}" if not disk_name.startswith("/dev/") else disk_name
    raw_json = None

    # 2. Cek perangkat NVMe via nvme-cli
    nvme_bin = _find_storage_bin("nvme")
    if "nvme" in disk_name and nvme_bin:
        for cmd_prefix in ([["sudo", "-n", nvme_bin], [nvme_bin]] if os.geteuid() != 0 else [[nvme_bin]]):
            try:
                p = subprocess.run(
                    cmd_prefix + ["smart-log", dev_path, "-o", "json"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=3,
                )
                if p.returncode == 0 and p.stdout.strip().startswith("{"):
                    raw_nvme = json.loads(p.stdout)
                    res["device_type"] = "nvme"
                    crit_warn = raw_nvme.get("critical_warning", 0)
                    pct_used = raw_nvme.get("percent_used")
                    avail_sp = raw_nvme.get("avail_spare")
                    sp_thresh = raw_nvme.get("spare_thresh", 10)
                    media_errs = raw_nvme.get("media_errors", 0)
                    temp_k = raw_nvme.get("temperature")
                    if temp_k and temp_k > 200:
                        res["temp_c"] = temp_k - 273
                    poh = raw_nvme.get("power_on_hours")
                    if poh is not None:
                        res["power_on_hours"] = poh

                    if pct_used is not None:
                        res["wearout_pct"] = int(pct_used)
                        res["wearout_remaining"] = max(0, 100 - int(pct_used))

                    # Evaluasi kesehatan NVMe
                    if crit_warn != 0 or (media_errs and media_errs > 10):
                        res["health"] = "critical"
                        res["status_label"] = "CRITICAL"
                        res["detail"] = f"NVMe Critical Warning: {crit_warn}, Media Errors: {media_errs}"
                    elif (res["temp_c"] and res["temp_c"] >= 65) or (pct_used is not None and pct_used >= 90) or (avail_sp is not None and avail_sp <= sp_thresh):
                        res["health"] = "warning"
                        res["status_label"] = "WARNING"
                        if res["temp_c"] and res["temp_c"] >= 65:
                            res["detail"] = f"Suhu tinggi: {res['temp_c']}°C"
                        elif pct_used is not None and pct_used >= 90:
                            res["detail"] = f"Sisa umur tipis: {res['wearout_remaining']}%"
                        else:
                            res["detail"] = f"Spare blocks menipis: {avail_sp}%"
                    else:
                        res["health"] = "healthy"
                        res["status_label"] = "PASSED"
                        res["detail"] = "Normal (NVMe)"
                    return res
            except Exception:
                pass

    # 3. Query via smartctl (-i -H -A -j)
    smartctl_bin = _find_storage_bin("smartctl")
    if smartctl_bin:
        for cmd_prefix in ([["sudo", "-n", smartctl_bin], [smartctl_bin]] if os.geteuid() != 0 else [[smartctl_bin]]):
            try:
                p = subprocess.run(
                    cmd_prefix + ["-i", "-H", "-A", "-j", dev_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=4,
                )
                if p.stdout.strip().startswith("{"):
                    raw_json = json.loads(p.stdout)
                    break
            except Exception:
                pass

    if raw_json:
        # Cek apakah smartctl mengindikasikan drive lacks SMART capability
        smart_sup = raw_json.get("smart_support") or {}
        if smart_sup.get("available") is False:
            res["is_virtual"] = True
            res["health"] = "healthy"
            res["status_label"] = "Virtual (Host)"
            res["device_type"] = "virtual"
            res["detail"] = "Virtual (Host Managed)"
            return res

        res["serial"] = raw_json.get("serial_number") or ""
        res["firmware"] = raw_json.get("firmware_version") or raw_json.get("scsi_revision") or ""
        res["device_type"] = raw_json.get("device", {}).get("type") or raw_json.get("device_type") or "disk"

        # NVMe info via smartctl
        nvme_info = raw_json.get("nvme_smart_health_information_log")
        if nvme_info:
            res["device_type"] = "nvme"
            crit_warn = nvme_info.get("critical_warning", 0)
            pct_used = nvme_info.get("percentage_used")
            avail_sp = nvme_info.get("available_spare")
            sp_thresh = nvme_info.get("available_spare_threshold", 10)
            media_errs = nvme_info.get("media_errors", 0)
            temp = nvme_info.get("temperature")
            if temp and 0 < temp < 150:
                res["temp_c"] = temp
            if pct_used is not None:
                res["wearout_pct"] = int(pct_used)
                res["wearout_remaining"] = max(0, 100 - int(pct_used))

            if crit_warn != 0 or (media_errs and media_errs > 10):
                res["health"] = "critical"
                res["status_label"] = "CRITICAL"
                res["detail"] = f"NVMe Critical Warning: {crit_warn}, Media Errors: {media_errs}"
            elif (res["temp_c"] and res["temp_c"] >= 65) or (pct_used is not None and pct_used >= 90) or (avail_sp is not None and avail_sp <= sp_thresh):
                res["health"] = "warning"
                res["status_label"] = "WARNING"
                if res["temp_c"] and res["temp_c"] >= 65:
                    res["detail"] = f"Suhu tinggi: {res['temp_c']}°C"
                elif pct_used is not None and pct_used >= 90:
                    res["detail"] = f"Sisa umur tipis: {res['wearout_remaining']}%"
                else:
                    res["detail"] = f"Spare blocks menipis: {avail_sp}%"
            else:
                res["health"] = "healthy"
                res["status_label"] = "PASSED"
                res["detail"] = "Normal (NVMe)"
            return res

        # ATA / SCSI / SATA SMART info
        temp_data = raw_json.get("temperature") or {}
        cur_temp = temp_data.get("current")
        if cur_temp and 0 < cur_temp < 150:
            res["temp_c"] = cur_temp

        poh = raw_json.get("power_on_time", {}).get("hours")
        if poh is not None:
            res["power_on_hours"] = poh

        # Parse ATA Attributes Table
        ata_attrs = raw_json.get("ata_smart_attributes", {}).get("table", [])
        reallocated = 0
        pending = 0
        ssd_life_val = None

        for attr in ata_attrs:
            aid = attr.get("id")
            name_attr = attr.get("name", "").lower()
            raw_v = attr.get("raw", {}).get("value", 0)
            val = attr.get("value", 100)

            if aid == 5 or "reallocated" in name_attr:
                reallocated = raw_v
                res["reallocated_sectors"] = reallocated
            elif aid in (197, 198) or "pending" in name_attr or "uncorrectable" in name_attr:
                pending = max(pending, raw_v)
            elif aid in (194, 190) or "temp" in name_attr:
                if not res["temp_c"] and 0 < raw_v < 150:
                    res["temp_c"] = raw_v
            elif aid in (177, 231, 232, 233, 169, 202) or "life" in name_attr or "wear" in name_attr:
                if ssd_life_val is None:
                    ssd_life_val = val

        if ssd_life_val is not None:
            res["wearout_remaining"] = ssd_life_val
            res["wearout_pct"] = max(0, 100 - ssd_life_val)

        smart_status = raw_json.get("smart_status") or {}
        passed = smart_status.get("passed")

        if passed is False:
            res["health"] = "critical"
            res["status_label"] = "CRITICAL"
            res["detail"] = "S.M.A.R.T. Melaporkan Kerusakan Hardware"
        elif (res["temp_c"] and res["temp_c"] >= 65) or reallocated > 10 or pending > 0 or (res["wearout_remaining"] is not None and res["wearout_remaining"] <= 10):
            res["health"] = "warning"
            res["status_label"] = "WARNING"
            reasons = []
            if res["temp_c"] and res["temp_c"] >= 65:
                reasons.append(f"Suhu {res['temp_c']}°C")
            if reallocated > 10:
                reasons.append(f"{reallocated} Sektor Rusak")
            if pending > 0:
                reasons.append(f"{pending} Pending Sektor")
            if res["wearout_remaining"] is not None and res["wearout_remaining"] <= 10:
                reasons.append(f"Sisa Umur {res['wearout_remaining']}%")
            res["detail"] = ", ".join(reasons) or "Degraded"
        elif passed is True:
            res["health"] = "healthy"
            res["status_label"] = "PASSED"
            res["detail"] = "Normal"
        else:
            res["health"] = "healthy"
            res["status_label"] = "PASSED"
            res["detail"] = "Normal"
        return res

    # 4. Fallback jika smartctl tidak tersedia / gagal eksekusi
    # Cek sensor suhu via sysfs /sys/class/hwmon
    try:
        hwmon_path = f"/sys/block/{disk_name}/device/hwmon"
        if os.path.exists(hwmon_path):
            for hdir in os.listdir(hwmon_path):
                tfile = os.path.join(hwmon_path, hdir, "temp1_input")
                if os.path.exists(tfile):
                    with open(tfile, "r") as f:
                        mc = int(f.read().strip())
                        if mc > 0:
                            res["temp_c"] = round(mc / 1000)
                            break
    except Exception:
        pass

    res["health"] = "unknown"
    res["status_label"] = "N/A"
    res["detail"] = "SMART tidak tersedia"
    return res


_hw_specs_cache = {"at": 0.0, "data": {}}

def collect_hardware_specs() -> dict:
    """Kumpulkan spesifikasi mendalam perangkat keras & platform sistem klien."""
    global _hw_specs_cache
    now = time.monotonic()
    if (now - _hw_specs_cache["at"]) < 45.0 and _hw_specs_cache["data"]:
        return _hw_specs_cache["data"]

    specs = {
        "cpu": {
            "model": "Unknown CPU",
            "cores": os.cpu_count() or 1,
            "arch": platform.machine() or "x86_64",
            "mhz": "",
            "cache": "",
        },
        "platform": {
            "virt": "Bare Metal / Physical",
            "vendor": "",
            "product": "",
            "bios_version": "",
            "bios_date": "",
        },
        "memory": {
            "ram_total": 0,
            "swap_total": 0,
        },
        "disks": [],
        "network": {
            "gateway": "",
            "dns": [],
            "interfaces": [],
        },
        "os": {
            "os_name": _os_pretty(),
            "kernel": _kernel_release(),
            "hostname": get_hostname(),
            "boot_time": "",
        }
    }

    # 1. CPU Detail dari /proc/cpuinfo
    try:
        if os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if ":" in line:
                        k, v = [x.strip() for x in line.split(":", 1)]
                        if k in ("model name", "Hardware", "Processor") and specs["cpu"]["model"] == "Unknown CPU":
                            specs["cpu"]["model"] = v
                        elif k == "cpu MHz" and not specs["cpu"]["mhz"]:
                            specs["cpu"]["mhz"] = v
                        elif k == "cache size" and not specs["cpu"]["cache"]:
                            specs["cpu"]["cache"] = v
    except Exception:
        pass

    # 2. Total RAM & Swap dari meminfo
    mem = _read_meminfo()
    specs["memory"]["ram_total"] = mem.get("MemTotal", 0)
    specs["memory"]["swap_total"] = mem.get("SwapTotal", 0)

    # 3. Platform & DMI data
    dmi_map = {
        "vendor": "/sys/class/dmi/id/sys_vendor",
        "product": "/sys/class/dmi/id/product_name",
        "bios_version": "/sys/class/dmi/id/bios_version",
        "bios_date": "/sys/class/dmi/id/bios_date",
    }
    for k, p in dmi_map.items():
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    specs["platform"][k] = f.read().strip()
        except Exception:
            pass

    # Deteksi Hypervisor / Virtualisasi / Kontainer secara komprehensif (Multi-Layer Heuristic)
    detected_virt = ""

    # 1. systemd-detect-virt (coba direct, lalu via sudo bila non-root)
    for cmd in (["systemd-detect-virt"], ["/usr/bin/sudo", "-n", "systemd-detect-virt"]):
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
            if res.returncode == 0:
                out = res.stdout.strip()
                if out and out.lower() != "none":
                    detected_virt = out.upper()
                    break
        except Exception:
            pass

    # 2. File /run/systemd/container (dibuat systemd PID 1 jika booted dalam container)
    if not detected_virt:
        try:
            if os.path.exists("/run/systemd/container"):
                with open("/run/systemd/container", "r", encoding="utf-8", errors="replace") as f:
                    c = f.read().strip()
                    if c and c.lower() != "none":
                        detected_virt = c.upper()
        except Exception:
            pass

    # 3. Mount inspection (/proc/mounts & /proc/self/mountinfo) - Proxmox LXCFS
    if not detected_virt:
        for mpath in ("/proc/mounts", "/proc/self/mountinfo"):
            try:
                if os.path.exists(mpath):
                    with open(mpath, "r", encoding="utf-8", errors="replace") as f:
                        m_content = f.read()
                        if "lxcfs" in m_content or "fuse.lxcfs" in m_content:
                            detected_virt = "LXC"
                            break
            except Exception:
                pass

    # 4. cgroup inspection (/proc/1/cgroup & /proc/self/cgroup - world-readable)
    if not detected_virt:
        for cg_path in ("/proc/1/cgroup", "/proc/self/cgroup"):
            try:
                if os.path.exists(cg_path):
                    with open(cg_path, "r", encoding="utf-8", errors="replace") as f:
                        cg_content = f.read()
                        if any(k in cg_content for k in ("/lxc/", "/lxc.payload", "/lxc.monitor", "machine-lxc", "lxc/")):
                            detected_virt = "LXC"
                            break
                        elif "/docker/" in cg_content or "/docker.service" in cg_content:
                            detected_virt = "DOCKER"
                            break
                        elif "/containerd/" in cg_content:
                            detected_virt = "CONTAINER"
                            break
            except Exception:
                pass

    # 5. AppArmor profile inspection (/proc/self/attr/current)
    if not detected_virt:
        for aa_path in ("/proc/self/attr/current", "/proc/self/attr/apparmor/current"):
            try:
                if os.path.exists(aa_path):
                    with open(aa_path, "r", encoding="utf-8", errors="replace") as f:
                        aa_content = f.read().strip()
                        if "lxc" in aa_content:
                            detected_virt = "LXC"
                            break
                        elif "docker" in aa_content:
                            detected_virt = "DOCKER"
                            break
            except Exception:
                pass

    # 6. /proc/1/environ (bila user root atau world-readable)
    if not detected_virt:
        try:
            if os.path.exists("/proc/1/environ"):
                with open("/proc/1/environ", "rb") as f:
                    env_raw = f.read()
                    if b"container=lxc" in env_raw:
                        detected_virt = "LXC"
                    elif b"container=docker" in env_raw or os.path.exists("/.dockerenv"):
                        detected_virt = "DOCKER"
                    elif b"container=podman" in env_raw:
                        detected_virt = "PODMAN"
        except Exception:
            pass

    # 7. Device markers & flag files
    if not detected_virt:
        if os.path.exists("/dev/lxcfs") or os.path.exists("/dev/.lxc"):
            detected_virt = "LXC"
        elif os.path.exists("/.dockerenv"):
            detected_virt = "DOCKER"

    if detected_virt:
        specs["platform"]["virt"] = detected_virt

    # Klasifikasi Tipe Platform & Label
    virt_upper = specs["platform"]["virt"].upper()
    if virt_upper in ("LXC", "LXC-LIBVIRT", "DOCKER", "PODMAN", "CONTAINER", "WSL", "SYSTEMD-NSPAWN"):
        specs["platform"]["platform_type"] = "lxc"
        specs["platform"]["platform_label"] = "LXC Container" if virt_upper in ("LXC", "LXC-LIBVIRT") else f"Container ({virt_upper})"
    elif virt_upper in ("KVM", "QEMU", "VMWARE", "XEN", "VIRTUALBOX", "ORACLE", "HYPERV", "BOCHS", "BHYVE"):
        specs["platform"]["platform_type"] = "vm"
        specs["platform"]["platform_label"] = f"VM ({virt_upper})"
    elif virt_upper not in ("", "BARE METAL / PHYSICAL", "NONE", "UNKNOWN"):
        specs["platform"]["platform_type"] = "vm"
        specs["platform"]["platform_label"] = f"VM ({virt_upper})"
    else:
        specs["platform"]["virt"] = "Bare Metal / Physical"
        specs["platform"]["platform_type"] = "baremetal"
        specs["platform"]["platform_label"] = "Baremetal"

    # 4. Storage Block Devices
    # Pada kontainer LXC, block devices di host (mis. HPE DL380 sda 7.6T) tidak dimiliki oleh kontainer.
    # Laporkan kuota/alokasi partisi container (rootfs) via statvfs('/'), bukan disk fisik host.
    is_container_ct = specs["platform"].get("platform_type") == "lxc" or virt_upper in ("LXC", "LXC-LIBVIRT", "DOCKER", "PODMAN")
    if is_container_ct:
        try:
            st = os.statvfs("/")
            tot_bytes = st.f_frsize * st.f_blocks
            if tot_bytes > 0:
                gb = tot_bytes / (1024 ** 3)
                sz_str = f"{round(gb / 1024, 1)}T" if gb >= 1024 else f"{round(gb, 1)}G"
                specs["disks"].append({
                    "name": "rootfs",
                    "size": sz_str,
                    "type": "Virtual (LXC)",
                    "model": "Container Allocation",
                    "smart": collect_disk_smart_health("rootfs", "Container Allocation", "lxc"),
                })
        except Exception:
            pass
    else:
        try:
            res = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "NAME,SIZE,TYPE,ROTA,TRAN,MODEL"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 3 and parts[2] == "disk":
                        name = parts[0]
                        size = parts[1]
                        rota = parts[3] if len(parts) > 3 else "1"
                        dtype = "SSD" if rota == "0" else "HDD"
                        model = " ".join(parts[5:]) if len(parts) > 5 else ""
                        specs["disks"].append({
                            "name": name,
                            "size": size,
                            "type": dtype,
                            "model": model,
                            "smart": collect_disk_smart_health(name, model, specs["platform"].get("platform_type", "")),
                        })
        except Exception:
            pass

    # Fallback disk jika specs["disks"] masih kosong
    if not specs["disks"]:
        try:
            st = os.statvfs("/")
            tot_bytes = st.f_frsize * st.f_blocks
            if tot_bytes > 0:
                gb = tot_bytes / (1024 ** 3)
                sz_str = f"{round(gb / 1024, 1)}T" if gb >= 1024 else f"{round(gb, 1)}G"
                specs["disks"].append({
                    "name": "rootfs",
                    "size": sz_str,
                    "type": "Virtual (LXC)" if is_container_ct else "Disk",
                    "model": "Root Partition",
                    "smart": collect_disk_smart_health("rootfs", "Root Partition", specs["platform"].get("platform_type", "")),
                })
        except Exception:
            pass

    # 5. Network (Default Gateway, DNS, & Interfaces)
    try:
        if os.path.exists("/proc/net/route"):
            with open("/proc/net/route", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    fields = line.strip().split()
                    if len(fields) >= 3 and fields[1] == "00000000":
                        specs["network"]["gateway"] = socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
                        break
    except Exception:
        pass

    try:
        if os.path.exists("/etc/resolv.conf"):
            with open("/etc/resolv.conf", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) > 1 and parts[1] not in specs["network"]["dns"]:
                            specs["network"]["dns"].append(parts[1])
    except Exception:
        pass

    try:
        net_dir = "/sys/class/net"
        if os.path.exists(net_dir):
            for iface in sorted(os.listdir(net_dir)):
                if iface == "lo":
                    continue
                mac_path = os.path.join(net_dir, iface, "address")
                speed_path = os.path.join(net_dir, iface, "speed")
                mac = ""
                speed = ""
                try:
                    if os.path.exists(mac_path):
                        with open(mac_path, "r", encoding="utf-8", errors="replace") as f:
                            mac = f.read().strip()
                except Exception:
                    pass
                try:
                    if os.path.exists(speed_path):
                        with open(speed_path, "r", encoding="utf-8", errors="replace") as f:
                            sp = f.read().strip()
                            if sp and int(sp) > 0:
                                speed = f"{sp} Mbps"
                except Exception:
                    pass
                specs["network"]["interfaces"].append({
                    "name": iface,
                    "mac": mac,
                    "speed": speed,
                })
    except Exception:
        pass

    # 6. Waktu Boot (Boot Time)
    try:
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r", encoding="utf-8", errors="replace") as f:
                up_secs = float(f.read().split()[0])
                import datetime as _dt
                btime = _dt.datetime.now() - _dt.timedelta(seconds=up_secs)
                specs["os"]["boot_time"] = btime.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    _hw_specs_cache["at"] = now
    _hw_specs_cache["data"] = specs
    return specs


def collect_disks() -> list[dict]:
    global _disk_prev, _disk_prev_t
    out = []
    now = time.monotonic()
    dt = (now - _disk_prev_t) if _disk_prev_t else 0.0

    # 1. Baca disk I/O delta dari /proc/diskstats
    io_rates: dict[str, dict] = {}
    curr_io: dict[str, dict] = {}
    try:
        with open("/proc/diskstats") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 14:
                    dev = parts[2]
                    if dev.startswith(("loop", "ram", "sr")):
                        continue
                    reads = int(parts[3])
                    sec_read = int(parts[5])
                    writes = int(parts[7])
                    sec_write = int(parts[9])
                    io_active = int(parts[11])
                    io_ms = int(parts[12])

                    curr_io[dev] = {
                        "reads": reads, "sec_read": sec_read,
                        "writes": writes, "sec_write": sec_write,
                        "io_ms": io_ms,
                    }
                    r_kb_s = 0.0
                    w_kb_s = 0.0
                    r_iops = 0.0
                    w_iops = 0.0
                    util_pct = 0.0
                    if dev in _disk_prev and dt > 0:
                        prev = _disk_prev[dev]
                        r_kb_s = max(0.0, ((sec_read - prev["sec_read"]) * 512 / 1024.0) / dt)
                        w_kb_s = max(0.0, ((sec_write - prev["sec_write"]) * 512 / 1024.0) / dt)
                        r_iops = max(0.0, (reads - prev["reads"]) / dt)
                        w_iops = max(0.0, (writes - prev["writes"]) / dt)
                        util_pct = min(100.0, max(0.0, ((io_ms - prev["io_ms"]) / (dt * 1000.0)) * 100.0))

                    io_rates[dev] = {
                        "read_kb_s": round(r_kb_s, 1),
                        "write_kb_s": round(w_kb_s, 1),
                        "read_iops": round(r_iops, 1),
                        "write_iops": round(w_iops, 1),
                        "util_pct": round(util_pct, 1),
                    }
    except OSError:
        pass
    _disk_prev = curr_io
    _disk_prev_t = now

    # 2. Peta mount point ke device block
    mount_dev_map = {}
    try:
        with open("/proc/mounts") as f:
            lines = f.read().splitlines()
    except OSError:
        return out

    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            dev_path, mount_pt, fstype = parts[0], parts[1], parts[2]
            if fstype in DISK_TYPES and dev_path.startswith("/dev/"):
                try:
                    dev_name = os.path.basename(os.path.realpath(dev_path))
                    mount_dev_map[mount_pt] = dev_name
                except Exception:
                    pass

    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        mount, fstype = parts[1], parts[2]
        opts = parts[3].split(",") if len(parts) >= 4 else []
        if fstype not in DISK_TYPES or len(out) >= 20:
            continue
        try:
            st = os.statvfs(mount)
        except OSError:
            continue
        is_ro = ("ro" in opts) or bool(getattr(st, "f_flag", 0) & getattr(os, "ST_RDONLY", 1))
        total = st.f_frsize * st.f_blocks
        used = total - st.f_frsize * st.f_bavail
        pct = round(used * 100.0 / total, 1) if total else 0.0

        # Cari device matching untuk I/O
        dev_name = mount_dev_map.get(mount)
        rates = io_rates.get(dev_name) if dev_name else None
        if not rates and dev_name:
            # Cek jika ada induk partisi (misal sda3 -> sda)
            for k, v in io_rates.items():
                if dev_name.startswith(k) or k.startswith(dev_name):
                    rates = v
                    break

        item = {
            "mount": mount, "type": fstype,
            "total": total, "used": used, "pct": pct,
            "is_ro": is_ro,
        }
        if rates:
            item["read_kb_s"] = rates["read_kb_s"]
            item["write_kb_s"] = rates["write_kb_s"]
            item["read_iops"] = rates["read_iops"]
            item["write_iops"] = rates["write_iops"]
            item["io_util"] = rates["util_pct"]

        out.append(item)
    return out


def collect_net() -> list[dict]:
    global _net_prev, _net_prev_t
    ifaces = []
    try:
        with open("/proc/net/dev") as f:
            lines = f.read().splitlines()[2:]
    except OSError:
        return ifaces

    # Kumpulkan IP per interface dari /proc/net/fib_trie (IPv4)
    _ip_map: dict[str, list[str]] = {}
    try:
        import socket
        import struct
        import fcntl
        SIOCGIFCONF = 0x8912
        SIOCGIFADDR = 0x8915
        with open("/proc/net/fib_trie") as ft:
            cur_iface = None
            for ln in ft:
                ln = ln.strip()
                if ln.startswith("Ifa:"):
                    # Format: Ifa: <iface>
                    cur_iface = ln.split()[-1] if len(ln.split()) > 1 else None
                elif cur_iface and ln.startswith("LOCAL"):
                    ip = ln.split()[-1]
                    try:
                        import ipaddress as _ia
                        a = _ia.ip_address(ip)
                        if not (a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified):
                            _ip_map.setdefault(cur_iface, [])
                            if ip not in _ip_map[cur_iface]:
                                _ip_map[cur_iface].append(ip)
                    except ValueError:
                        pass
    except Exception:
        pass

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
            "ip_addrs": _ip_map.get(name, [])[:4],
        })
        _net_prev[name] = (rx, tx)
    _net_prev_t = now
    return [i for i in ifaces if not i["iface"].startswith("lo")][:16]



def collect_top_processes(limit: int = 100) -> dict:
    """Kumpulkan snapshot proses teratas berdasarkan %CPU dan %MEM beserta status (state)."""
    top_cpu = []
    top_mem = []
    res_cpu = _run_cmd(["ps", "-eo", "pid,user,comm,state,%cpu,%mem", "--sort=-%cpu"], timeout=5)
    if res_cpu and res_cpu.returncode == 0:
        lines = res_cpu.stdout.strip().splitlines()
        for line in lines[1:limit + 1]:
            parts = line.split(None, 5)
            if len(parts) >= 6:
                try:
                    top_cpu.append({
                        "pid": int(parts[0]),
                        "user": parts[1],
                        "comm": parts[2],
                        "state": parts[3],
                        "cpu": float(parts[4]),
                        "mem": float(parts[5]),
                    })
                except (ValueError, IndexError):
                    pass

    res_mem = _run_cmd(["ps", "-eo", "pid,user,comm,state,%cpu,%mem", "--sort=-%mem"], timeout=5)
    if res_mem and res_mem.returncode == 0:
        lines = res_mem.stdout.strip().splitlines()
        for line in lines[1:limit + 1]:
            parts = line.split(None, 5)
            if len(parts) >= 6:
                try:
                    top_mem.append({
                        "pid": int(parts[0]),
                        "user": parts[1],
                        "comm": parts[2],
                        "state": parts[3],
                        "cpu": float(parts[4]),
                        "mem": float(parts[5]),
                    })
                except (ValueError, IndexError):
                    pass

    return {"cpu": top_cpu, "mem": top_mem}


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
        "top_procs": collect_top_processes(100),
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


def _get_locked_users() -> set[str]:
    try:
        cmd = [PANTAU_USER_CMD, "list-locked"] if IS_ROOT else ["/usr/bin/sudo", "-n", PANTAU_USER_CMD, "list-locked"]
        res = _run_cmd(cmd, timeout=3)
        if res and res.returncode == 0:
            return set(res.stdout.split())
    except Exception:
        pass
    return set()


def collect_groups() -> list[dict]:
    """Mengumpulkan inventaris seluruh grup sistem Linux (/etc/group)."""
    groups_list = []
    try:
        gr_entries = list(grp.getgrall())
    except Exception:
        gr_entries = []

    primary_group_mems: dict[int, set[str]] = {}
    try:
        for pw in pwd.getpwall():
            primary_group_mems.setdefault(pw.pw_gid, set()).add(pw.pw_name)
    except Exception:
        pass

    privileged_names = frozenset({
        "root", "sudo", "wheel", "admin", "docker", "adm", "shadow", "disk", "lxd", "kvm"
    })

    for gr in gr_entries:
        p_name = gr.gr_name
        gid = gr.gr_gid
        is_priv = p_name in privileged_names
        is_sys = (gid < 1000 and gid != 0)

        all_members = set(gr.gr_mem)
        if gid in primary_group_mems:
            all_members.update(primary_group_mems[gid])
        sorted_mems = sorted(list(all_members))

        groups_list.append({
            "group": p_name,
            "gid": gid,
            "is_system": is_sys,
            "is_privileged": is_priv,
            "members": sorted_mems[:50],
            "member_count": len(sorted_mems),
        })

    def _group_sort_key(g):
        priv_rank = 0 if g["is_privileged"] else 1
        type_rank = 0 if not g["is_system"] else 1
        return (priv_rank, type_rank, g["gid"])

    groups_list.sort(key=_group_sort_key)
    return groups_list[:250]


def collect_accounts() -> list[dict]:
    """Mengumpulkan inventaris seluruh akun pengguna Linux (/etc/passwd, lastlog, who)."""
    lastlog = _parse_lastlog()
    who = _parse_who()
    locked_set = _get_locked_users()
    sessions_by_user: dict[str, list[dict]] = {}
    for s in who:
        sessions_by_user.setdefault(s["user"], []).append(s)

    gid_to_name: dict[int, str] = {}
    user_to_supp_groups: dict[str, list[str]] = {}
    try:
        for gr in grp.getgrall():
            gid_to_name[gr.gr_gid] = gr.gr_name
            for m in gr.gr_mem:
                user_to_supp_groups.setdefault(m, []).append(gr.gr_name)
    except Exception:
        pass

    protected_set = frozenset({
        "root", "pantau", "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail",
        "news", "uucp", "proxy", "www-data", "backup", "list", "irc", "gnats", "nobody",
        "_apt", "messagebus", "sshd"
    })
    privileged_groups = frozenset({"sudo", "wheel", "root", "admin"})

    accounts = []
    try:
        entries = list(pwd.getpwall())
    except Exception:
        entries = []

    for pw in entries:
        sessions = sessions_by_user.get(pw.pw_name, [])
        primary_grp_name = gid_to_name.get(pw.pw_gid, str(pw.pw_gid))
        supp_groups = sorted(user_to_supp_groups.get(pw.pw_name, []))

        is_system = (pw.pw_uid < 1000 and pw.pw_uid != 0)
        is_sudo = (pw.pw_uid == 0) or (primary_grp_name in privileged_groups) or bool(set(supp_groups) & privileged_groups)
        is_protected = is_system or (pw.pw_name in protected_set)
        is_locked = pw.pw_name in locked_set

        accounts.append({
            "user": pw.pw_name,
            "uid": pw.pw_uid,
            "gid": pw.pw_gid,
            "group": primary_grp_name,
            "groups": supp_groups[:20],
            "home": pw.pw_dir or "",
            "shell": pw.pw_shell or "",
            "last_login": lastlog.get(pw.pw_name, ""),
            "sessions": sessions[:5],
            "is_system": is_system,
            "is_sudo": is_sudo,
            "is_protected": is_protected,
            "is_locked": is_locked,
        })

    def _acc_sort_key(a):
        active_rank = 0 if a["user"] in sessions_by_user else 1
        type_rank = 0 if not a["is_system"] else 1
        return (active_rank, type_rank, a["uid"])

    accounts.sort(key=_acc_sort_key)

    seen_users = {a["user"] for a in accounts}
    for u, u_sessions in sessions_by_user.items():
        if u not in seen_users:
            accounts.append({
                "user": u,
                "uid": 9999,
                "gid": 9999,
                "group": "nogroup",
                "groups": [],
                "home": "",
                "shell": "/bin/sh",
                "last_login": "",
                "sessions": u_sessions[:5],
                "is_system": False,
                "is_sudo": False,
                "is_protected": False,
                "is_locked": False,
            })
    return accounts[:250]


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


def collect_systemd_units(limit: int = 2000) -> list[dict]:
    """Mengumpulkan inventaris seluruh unit service systemd (runtime state + boot enablement + telemetri PID & RAM)."""
    boot_map = {}
    p_files = _run_cmd(
        ["/usr/bin/systemctl", "list-unit-files", "--type=service", "--no-pager", "--no-legend"],
        timeout=10,
    )
    if p_files and p_files.stdout:
        for line in p_files.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                u_name = parts[0].strip()
                boot_state = parts[1].strip().lower()
                boot_map[u_name] = boot_state
                base = u_name[:-8] if u_name.endswith(".service") else u_name
                boot_map[base] = boot_state

    p_units = _run_cmd(
        ["/usr/bin/systemctl", "list-units", "--type=service", "--all", "--no-pager", "--no-legend"],
        timeout=15,
    )
    units = []
    seen = set()
    running_names = []

    if p_units and p_units.stdout:
        for line in p_units.stdout.splitlines()[:limit]:
            line = line.strip().lstrip("●").strip()
            if not line:
                continue
            parts = line.split(None, 4)
            if len(parts) >= 4:
                u_name = parts[0].strip()
                load = parts[1].strip().lower()
                active = parts[2].strip().lower()
                sub = parts[3].strip().lower()
                desc = parts[4].strip() if len(parts) > 4 else ""

                if active == "active" and sub == "running":
                    status = "running"
                    running_names.append(u_name)
                elif active == "active" and sub == "exited":
                    status = "exited"
                elif active == "failed" or sub == "failed":
                    status = "failed"
                elif active == "inactive":
                    status = "inactive"
                else:
                    status = active or "unknown"

                boot = (
                    boot_map.get(u_name)
                    or boot_map.get(u_name[:-8] if u_name.endswith(".service") else u_name)
                    or "unknown"
                )

                units.append({
                    "name": u_name,
                    "load": load,
                    "active": active,
                    "sub": sub,
                    "status": status,
                    "boot": boot,
                    "description": desc,
                    "pid": None,
                    "memory": None,
                    "tasks": None,
                })
                seen.add(u_name)

    # Unit yang ada di disk tapi belum dimuat di runtime
    for u_name, boot_state in boot_map.items():
        if not u_name.endswith(".service"):
            continue
        if u_name not in seen and "@" not in u_name and len(units) < limit:
            units.append({
                "name": u_name,
                "load": "unloaded",
                "active": "inactive",
                "sub": "dead",
                "status": "inactive",
                "boot": boot_state,
                "description": "",
                "pid": None,
                "memory": None,
                "tasks": None,
            })
            seen.add(u_name)

    # Kumpulkan telemetri PID, RAM, & Thread untuk unit yang aktif running
    if running_names:
        p_show = _run_cmd(
            ["/usr/bin/systemctl", "show", "-p", "Id,MainPID,MemoryCurrent,TasksCurrent", *running_names[:200]],
            timeout=10,
        )
        if p_show and p_show.stdout:
            props = {}
            for block in p_show.stdout.strip().split("\n\n"):
                cur = {}
                for line in block.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        cur[k.strip()] = v.strip()
                uid = cur.get("Id")
                if uid:
                    props[uid] = cur

            for u in units:
                pr = props.get(u["name"])
                if pr:
                    pid = pr.get("MainPID")
                    if pid and pid.isdigit() and int(pid) > 0:
                        u["pid"] = int(pid)
                    mem = pr.get("MemoryCurrent")
                    if mem and mem.isdigit() and int(mem) < 18446744073709551615:
                        u["memory"] = int(mem)
                    tasks = pr.get("TasksCurrent")
                    if tasks and tasks.isdigit() and int(tasks) > 0:
                        u["tasks"] = int(tasks)

    return units


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


PANTAU_APT_SCRIPT_BODY = """#!/bin/sh
# pantau-apt — Cangkang sempit utk tombol Update/Upgrade paket OS.
# Dipanggil agen 'pantau' via sudo NOPASSWD (lihat /etc/sudoers.d/pantau-agent).
# Dijalankan lewat pty (script -qfec) supaya output PERSIS seperti terminal SSH:
# baris progress \\r ikut terlihat, dan dpkg bisa BERINTERAKSI lewat stdin.
# Argumen divalidasi di sini; BUKAN shell passthrough. URL/repo tetap apa adanya.
#
# Pemakaian:
#   pantau-apt update            -> sinkron, non-interaktif
#   pantau-apt upgrade           -> upgrade NON-INTERAKTIF (aman, tak menggantung)
#   pantau-apt upgrade-interact  -> upgrade INTERAKTIF: admin mengetik jawaban
#                                   sendiri lewat kotak input di Dashboard
#                                   (dpkg boleh bertanya apa pun)
#
# Kenapa ada dua mode? Non-interaktif cocok untuk update terjadwal/massal.
# Interaktif dipakai admin yang ingin memutuskan sendiri tiap prompt dpkg
# (mis. memakai konfigurasi bawaan paket, bukan miliknya).
set -e

DPKG_KEEP_LOCAL="-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
DPKG_COMMON="-o Dpkg::Use-Pty=0 -o Dpkg::Lock::Timeout=600 -o APT::Get::Always-Include-Phased-Updates=true"

if [ -e /var/lib/dpkg/lock-frontend ] && fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; then
    echo "pantau-apt: proses apt/dpkg lain sedang berjalan (lock /var/lib/dpkg/lock-frontend dipegang)." >&2
    echo "           Tunggu proses itu selesai, lalu ulangi. Tidak ada yang dirusak." >&2
    exit 3
fi

case "${1:-}" in
    update)
        export DEBIAN_FRONTEND=noninteractive
        export NEEDRESTART_MODE=l
        export APT_LISTCHANGES_FRONTEND=none
        exec /usr/bin/script -qfec "/usr/bin/apt-get update -o Dpkg::Lock::Timeout=600" /dev/null
        ;;
    upgrade)
        export DEBIAN_FRONTEND=noninteractive
        export NEEDRESTART_MODE=a
        export APT_LISTCHANGES_FRONTEND=none
        exec /usr/bin/script -qfec "/usr/bin/apt-get --with-new-pkgs -y -o Dpkg::Lock::Timeout=600 $DPKG_KEEP_LOCAL $DPKG_COMMON upgrade" /dev/null
        ;;
    upgrade-interact)
        unset DEBIAN_FRONTEND DEBCONF_NONINTERACTIVE_SEEN
        export NEEDRESTART_MODE=a
        export APT_LISTCHANGES_FRONTEND=none
        exec /usr/bin/script -qfec "/usr/bin/apt-get --with-new-pkgs -y -o Dpkg::Lock::Timeout=600 -o Dpkg::Use-Pty=1 -o APT::Get::Always-Include-Phased-Updates=true upgrade" /dev/null
        ;;
    dist-upgrade)
        unset DEBIAN_FRONTEND DEBCONF_NONINTERACTIVE_SEEN
        export NEEDRESTART_MODE=a
        export APT_LISTCHANGES_FRONTEND=none
        exec /usr/bin/script -qfec "/usr/bin/apt-get -y -o Dpkg::Lock::Timeout=600 -o Dpkg::Use-Pty=1 -o APT::Get::Always-Include-Phased-Updates=true dist-upgrade" /dev/null
        ;;
    fix)
        unset DEBIAN_FRONTEND DEBCONF_NONINTERACTIVE_SEEN
        export NEEDRESTART_MODE=a
        export APT_LISTCHANGES_FRONTEND=none
        /usr/bin/script -qfec "/usr/bin/dpkg --configure -a" /dev/null || true
        exec /usr/bin/script -qfec "/usr/bin/apt-get -y -f -o Dpkg::Lock::Timeout=600 -o Dpkg::Use-Pty=1 -o APT::Get::Always-Include-Phased-Updates=true install" /dev/null
        ;;
    clean)
        exec /usr/bin/apt-get clean
        ;;
    upgrade-pkg)
        pkg="${2:-}"
        if [ -z "$pkg" ]; then
            echo "pantau-apt: nama paket target tidak boleh kosong" >&2
            exit 2
        fi
        case "$pkg" in
            *[!a-z0-9+.-]* | "" | -* | .* | +* )
                echo "pantau-apt: nama paket tidak valid: '$pkg'" >&2
                exit 2
                ;;
        esac
        export DEBIAN_FRONTEND=noninteractive
        export NEEDRESTART_MODE=a
        export APT_LISTCHANGES_FRONTEND=none
        exec /usr/bin/script -qfec "/usr/bin/apt-get --only-upgrade -y -o Dpkg::Lock::Timeout=600 $DPKG_KEEP_LOCAL $DPKG_COMMON install '$pkg'" /dev/null
        ;;
    *)
        echo "pantau-apt: argumen tidak dikenal: '${1:-}'" >&2
        echo "            (hanya: update | upgrade | upgrade-interact | dist-upgrade | fix | clean | upgrade-pkg)" >&2
        exit 2
        ;;
esac
"""


def ensure_pantau_apt_updated() -> bool:
    """Memastikan wrapper /usr/local/sbin/pantau-apt mendukung upgrade-pkg, clean, dan Always-Include-Phased-Updates.
    Jika masih versi lama, otomatis perbarui via root langsung atau sudo pantau-file.
    """
    try:
        # Konfigurasi APT tingkat sistem agar semua operasi apt mengikutsertakan Phased Updates
        apt_conf_dir = "/etc/apt/apt.conf.d"
        apt_conf_file = os.path.join(apt_conf_dir, "99pantau-phased-updates")
        if os.path.isdir(apt_conf_dir) and not os.path.isfile(apt_conf_file):
            phased_content = 'APT::Get::Always-Include-Phased-Updates "true";\n'
            if IS_ROOT:
                try:
                    with open(apt_conf_file, "w", encoding="utf-8") as f:
                        f.write(phased_content)
                except Exception:
                    pass
            else:
                pantau_file = "/usr/local/sbin/pantau-file"
                if os.path.isfile(pantau_file):
                    try:
                        payload = json.dumps({
                            "action": "write",
                            "params": {"path": apt_conf_file, "content": phased_content, "make_backup": False}
                        })
                        subprocess.run(["/usr/bin/sudo", "-n", pantau_file], input=payload, text=True, capture_output=True, timeout=5)
                    except Exception:
                        pass

        cur_content = ""
        if os.path.isfile(PANTAU_APT_CMD):
            try:
                with open(PANTAU_APT_CMD, "r", encoding="utf-8", errors="replace") as f:
                    cur_content = f.read()
            except Exception:
                pass
        if "Always-Include-Phased-Updates" in cur_content and "upgrade-pkg" in cur_content and "clean" in cur_content and "-qfec" in cur_content:
            return True

        if IS_ROOT:
            with open(PANTAU_APT_CMD, "w", encoding="utf-8") as f:
                f.write(PANTAU_APT_SCRIPT_BODY)
            os.chmod(PANTAU_APT_CMD, 0o755)
            print("[APT] Wrapper /usr/local/sbin/pantau-apt berhasil diperbarui (root)")
            return True

        # Jika user 'pantau', gunakan sudo pantau-file jika tersedia
        pantau_file = "/usr/local/sbin/pantau-file"
        if os.path.isfile(pantau_file):
            payload_write = json.dumps({
                "action": "write",
                "params": {"path": PANTAU_APT_CMD, "content": PANTAU_APT_SCRIPT_BODY, "make_backup": False}
            })
            pw = subprocess.run(["/usr/bin/sudo", "-n", pantau_file], input=payload_write, text=True, capture_output=True, timeout=10)
            try:
                out_data = json.loads(pw.stdout or "{}")
            except Exception:
                out_data = {}
            if pw.returncode == 0 and out_data.get("ok"):
                payload_chmod = json.dumps({
                    "action": "chmod",
                    "params": {"path": PANTAU_APT_CMD, "mode": "0755"}
                })
                subprocess.run(["/usr/bin/sudo", "-n", pantau_file], input=payload_chmod, text=True, capture_output=True, timeout=10)
                print("[APT] Wrapper /usr/local/sbin/pantau-apt berhasil diperbarui via pantau-file")
                return True
    except Exception as e:
        print(f"[APT WARN] Gagal memperbarui {PANTAU_APT_CMD}: {e}")
    return False


def _apt_cmd(kind: str, detail: str = ""):
    """Command apt (lewat wrapper sempit) + timeout per jenis aksi."""
    ensure_pantau_apt_updated()
    prefix = [] if IS_ROOT else ["/usr/bin/sudo", "-n"]
    if kind == "APT_UPDATE":
        return prefix + [PANTAU_APT_CMD, "update"], 300
    if kind == "APT_UPGRADE":
        return prefix + [PANTAU_APT_CMD, "upgrade"], 900
    if kind == "APT_UPGRADE_INTERACT":
        # Interaktif menunggu admin mengetik; timeout lebih longgar, dan HANYA
        # diakhiri bila proses benar-benar tidak bergerak (mis. admin lupa).
        return prefix + [PANTAU_APT_CMD, "upgrade-interact"], 3600
    if kind == "APT_DIST_UPGRADE":
        return prefix + [PANTAU_APT_CMD, "dist-upgrade"], 3600
    if kind == "APT_FIX":
        # Reparasi dpkg & pemulihan paket rusak
        return prefix + [PANTAU_APT_CMD, "fix"], 1800
    if kind == "PKG_UPGRADE":
        pkg = (detail or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", pkg):
            raise ValueError(f"nama paket tidak valid untuk upgrade: '{pkg}'")
        return prefix + [PANTAU_APT_CMD, "upgrade-pkg", pkg], 600
    if kind == "PKG_CLEAN":
        return prefix + [PANTAU_APT_CMD, "clean"], 120
    raise ValueError(f"unit apt tidak dikenal: {kind}")


def collect_installed_packages(limit: int = 5000) -> list[dict]:
    """Mengumpulkan inventaris seluruh paket OS yang terpasang via dpkg-query,
    beserta deteksi paket pengguna vs sistem (apt-mark showmanual) dan
    status layanan aktif runtime systemd (running, exited, inactive, installed).
    """
    pkgs = []
    if not os.path.exists("/usr/bin/dpkg-query"):
        return pkgs

    # 1. Ambil daftar paket manual/pengguna via apt-mark showmanual
    manual_set = set()
    res_manual = _run_cmd(["/usr/bin/apt-mark", "showmanual"], timeout=8)
    if res_manual and res_manual.stdout:
        for line in res_manual.stdout.splitlines():
            line = line.strip()
            if line:
                manual_set.add(line)
                if ":" in line:
                    manual_set.add(line.split(":")[0])

    # 2. Ambil status layanan systemd terkini
    svc_map = {}
    res_svc = _run_cmd([
        "/usr/bin/systemctl", "list-units", "--type=service", "--all", "--no-pager", "--no-legend"
    ], timeout=8)
    if res_svc and res_svc.stdout:
        for line in res_svc.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) >= 4:
                unit = parts[0].strip()
                active = parts[2].strip()
                sub = parts[3].strip()
                base_name = unit.replace(".service", "")
                if active == "active" and sub == "running":
                    st = "running"
                elif active == "active" and sub == "exited":
                    st = "exited (active)"
                elif active == "failed" or sub == "failed":
                    st = "failed"
                elif active == "inactive":
                    st = "inactive"
                else:
                    st = "inactive"
                svc_map[base_name] = st

    # Alias / pemetaan umum nama paket ke nama unit systemd
    alias_map = {
        "openssh-server": "ssh",
        "mariadb-server": "mariadb",
        "mysql-server": "mysql",
        "apache2": "apache2",
        "nginx": "nginx",
        "cron": "cron",
        "systemd": "systemd-journald",
        "ufw": "ufw",
        "bind9": "named",
        "docker.io": "docker",
        "docker-ce": "docker",
        "redis-server": "redis",
    }

    # 3. Kueri dpkg-query untuk paket
    res = _run_cmd([
        "/usr/bin/dpkg-query", "-W", "-f",
        "${binary:Package}\t${Version}\t${Architecture}\t${Installed-Size}\t${Priority}\t${Section}\t${binary:Summary}\n"
    ], timeout=15)
    if not res or not res.stdout or "\t" not in res.stdout:
        res = _run_cmd([
            "/usr/bin/dpkg-query", "-W",
            "-f=${binary:Package}\t${Version}\t${Architecture}\t${Installed-Size}\t${Priority}\t${Section}\t${binary:Summary}\n"
        ], timeout=15)

    if res and res.stdout:
        for line in res.stdout.splitlines()[:limit]:
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[0].strip()
                ver = parts[1].strip()
                arch = parts[2].strip() if len(parts) > 2 else ""
                size_kb = 0
                if len(parts) > 3:
                    try:
                        size_kb = int(parts[3].strip())
                    except ValueError:
                        size_kb = 0
                prio = parts[4].strip().lower() if len(parts) > 4 else ""
                sec = parts[5].strip().lower() if len(parts) > 5 else ""
                summary = parts[6].strip() if len(parts) > 6 else ""

                base_name = name.split(":")[0]

                # Klasifikasi Paket Pengguna vs Sistem
                is_user = False
                if (name in manual_set or base_name in manual_set) and prio not in ("required", "important"):
                    is_user = True

                # Klasifikasi Runtime Status dari unit systemd
                unit_candidate = alias_map.get(base_name) or alias_map.get(name) or base_name
                status = svc_map.get(unit_candidate)
                if not status:
                    stripped = base_name.replace("-server", "").replace("server-", "")
                    status = svc_map.get(stripped)
                if not status:
                    status = "installed"

                pkgs.append({
                    "name": name,
                    "version": ver,
                    "arch": arch,
                    "size_kb": size_kb,
                    "summary": summary,
                    "is_user": is_user,
                    "status": status,
                })
    return pkgs


def clear_package_cache(pkg: str = "") -> str:
    """Membersihkan cache berkas .deb unduhan untuk paket tertentu atau seluruh apt cache."""
    cleaned = 0
    bytes_freed = 0
    pkg = (pkg or "").strip()
    if pkg and re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", pkg):
        cache_dir = "/var/cache/apt/archives"
        if os.path.isdir(cache_dir):
            for fname in os.listdir(cache_dir):
                if fname.startswith(f"{pkg}_") and fname.endswith(".deb"):
                    fpath = os.path.join(cache_dir, fname)
                    try:
                        sz = os.path.getsize(fpath)
                        os.unlink(fpath)
                        cleaned += 1
                        bytes_freed += sz
                    except OSError:
                        pass
        mb_freed = bytes_freed / (1024 * 1024)
        return f"Cache untuk paket '{pkg}' berhasil dibersihkan: {cleaned} berkas deb ({mb_freed:.2f} MB)."
    prefix = [] if IS_ROOT else ["/usr/bin/sudo", "-n"]
    res = _run_cmd(prefix + [PANTAU_APT_CMD, "clean"], timeout=30)
    if res and res.returncode == 0:
        return "Seluruh cache paket sistem operasi (/var/cache/apt/archives) berhasil dibersihkan."
    return "Cache paket sistem dibersihkan."


def get_package_logs(pkg: str, lines: int = 100) -> str:
    """Membaca riwayat aktivitas dpkg untuk paket spesifik dari /var/log/dpkg.log."""
    pkg = (pkg or "").strip()
    if not pkg or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", pkg):
        return "Nama paket tidak valid."
    matched_lines = []
    for path in ("/var/log/dpkg.log.1", "/var/log/dpkg.log"):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if f" {pkg}:" in line or f" {pkg} " in line:
                        matched_lines.append(line.strip())
        except OSError as e:
            matched_lines.append(f"[Gagal membaca {path}: {e}]")
    if not matched_lines:
        return f"Belum ada riwayat aktivitas log untuk paket '{pkg}' pada berkas /var/log/dpkg.log."
    return "\n".join(matched_lines[-lines:])


def _apt_sudo_denied_hint(err: str) -> str:
    """Pesan bantuan bila wrapper/sudoers belum tersedia di host klien."""
    low_err = (err or "").lower()
    if "no new privileges" in low_err:
        return (
            "[apt tidak dapat dijalankan] Konfigurasi systemd agen pada host/container ini "
            "mengaktifkan flag 'NoNewPrivileges' atau isolasi namespace (PrivateTmp/Protect*), "
            "sehingga kernel menolak eskalasi sudo.\n"
            "Perbaiki (sebagai root di host ini):\n"
            "  sudo sed -i 's/^PrivateTmp=yes/PrivateTmp=no/' /etc/systemd/system/agent_pantau.service\n"
            "  sudo sed -i 's/^ProtectKernelTunables=yes/ProtectKernelTunables=no/' /etc/systemd/system/agent_pantau.service\n"
            "  sudo sed -i 's/^ProtectControlGroups=yes/ProtectControlGroups=no/' /etc/systemd/system/agent_pantau.service\n"
            "  sudo sed -i 's/^ProtectClock=yes/ProtectClock=no/' /etc/systemd/system/agent_pantau.service\n"
            "  echo 'NoNewPrivileges=no' | sudo tee -a /etc/systemd/system/agent_pantau.service\n"
            "  sudo systemctl daemon-reload && sudo systemctl restart agent_pantau.service\n"
            "Rincian teknis:\n" + (err or "")
        )
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
_TERM_KEEP_RE = re.compile(r"\x1b\[(?:[0-9;]*m|2J|3J|H|1;1H|[0-2]?K|[0-9]*P|[0-9]*[A-D])")


def _keep_sgr(text: str) -> str:
    """Buang semua escape sequence KECUALI SGR & clear screen, sisakan \\r \\b \\t \\n \\x0c.

    Untuk stream apt & shell: dashboard merender ulang kodenya sendiri supaya output
    di kotak terminal terlihat sama seperti di SSH (warna + gerak kursor + clear screen).
    """
    if not text:
        return ""

    def _repl(m: re.Match) -> str:
        return m.group(0) if _TERM_KEEP_RE.fullmatch(m.group(0)) else ""

    cleaned = _ANSI_RE.sub(_repl, text).replace("\x00", "")
    kept: list[str] = []

    def _stash(m: re.Match) -> str:
        kept.append(m.group(0))
        return f"\ue000{len(kept) - 1}\ue001"

    cleaned = _TERM_KEEP_RE.sub(_stash, cleaned)
    cleaned = "".join(c for c in cleaned
                      if c >= " " or c in "\n\r\b\t\x0c\ue000\ue001")
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


def _render_cells(cells: list[tuple[str, str]], upto: int, strip_trailing: bool = True) -> str:
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
    res = "".join(parts)
    return res.rstrip("\t ") if strip_trailing else res


def termify(raw: str) -> str:
    """Emulasi layar terminal utk output yang memakai \\r, \\b, erase line, dan clear screen.

    Di terminal SSH, `\\r` memindahkan kursor ke awal baris, `\\b` memundurkan
    kursor, `\\x1b[K` menghapus ke kanan, dan `\\x1b[2J` membersihkan layar.
    Fungsi ini mereplikasi sel kursor dan buffer layar sehingga hasil yang
    tampil di dashboard persis sama dengan layar SSH yang sesungguhnya.
    """
    if "Session terminated" in raw:
        raw = re.sub(r"\n?Session terminated, killing shell\.\.\..*$", "", raw, flags=re.MULTILINE)
    out: list[str] = []
    cells: list[tuple[str, str]] = []
    style = ""
    p = 0
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "\x1b":
            # 1. Warna / SGR
            m = _SGR_RE.match(raw, i)
            if m:
                style = _sgr_on(style, m.group(1))
                i = m.end()
                continue
            # 2. Clear Screen: \x1b[2J, \x1b[3J, \x1b[H\x1b[2J
            m_clear = re.match(r"\x1b\[(?:2J|3J|H\x1b\[2J)", raw[i:])
            if m_clear:
                out = []
                cells = []
                p = 0
                i += m_clear.end()
                continue
            # 3. Cursor Home: \x1b[H, \x1b[1;1H
            m_h = re.match(r"\x1b\[(?:H|1;1H)", raw[i:])
            if m_h:
                p = 0
                i += m_h.end()
                continue
            # 4. Erase in Line: \x1b[K, \x1b[0K, \x1b[1K, \x1b[2K
            m_k = re.match(r"\x1b\[([0-2]?)K", raw[i:])
            if m_k:
                k_mode = m_k.group(1) or "0"
                if k_mode in ("0", ""):
                    cells = cells[:p]
                elif k_mode == "2":
                    cells = []
                    p = 0
                elif k_mode == "1":
                    for idx in range(min(p, len(cells))):
                        cells[idx] = (style, " ")
                i += m_k.end()
                continue
            # 5. Delete Character: \x1b[P, \x1b[1P, dll
            m_p = re.match(r"\x1b\[(\d*)P", raw[i:])
            if m_p:
                cnt = int(m_p.group(1)) if m_p.group(1) else 1
                del cells[p:p+cnt]
                i += m_p.end()
                continue
            # 6. Cursor Movement: \x1b[C (forward), \x1b[D (backward)
            m_cd = re.match(r"\x1b\[(\d*)([CD])", raw[i:])
            if m_cd:
                cnt = int(m_cd.group(1)) if m_cd.group(1) else 1
                if m_cd.group(2) == "C":
                    p = min(p + cnt, len(cells))
                else:
                    p = max(p - cnt, 0)
                i += m_cd.end()
                continue
            i += 1  # escape lain: abaikan
            continue
        if c == "\x0c":  # Form Feed / Ctrl+L
            out = []
            cells = []
            p = 0
            i += 1
            continue
        if c == "\r":
            p = 0
            i += 1
            continue
        if c == "\n":
            out.append(_render_cells(cells, len(cells), strip_trailing=True) + "\n")
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
    return "".join(out) + _render_cells(cells, len(cells), strip_trailing=False)


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


def _run_apt_in_thread(cfg: dict, rid: int, kind: str, detail: str = ""):
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
        _run_apt_inner(cfg, rid, kind, detail)
    finally:
        with _APT_RUN_LOCK:
            _APT_RUNNING = False


def _run_apt_inner(cfg: dict, rid: int, kind: str, detail: str = ""):
    """Jalankan apt update/upgrade DENGAN STREAMING live ke Dashboard.

    Proses dijalankan lewat wrapper pantau-apt -> script (pty), jadi outputnya
    PERSIS seperti terminal SSH (termasuk frame progress \r). Output dibaca
    dalam potongan biner, dibersihkan, lalu dikirim ke /progress tiap ~1,2
    detik agar admin melihat proses berjalan. Hasil final TIDAK dipotong
    (kuota APT_AGENT_OUTPUT_MAX = 4MB, praktis selengkap SSH).
    """
    try:
        cmd, timeout = _apt_cmd(kind, detail)
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

    global last_apt, _last_pkg_signature
    try:
        apt = collect_apt()
        last_apt = apt
        _last_pkg_signature = _get_pkg_state_signature()
    except Exception:
        apt = None

    partial = termify(_tail_parts(output_parts, 40000)).strip("\n")
    low_full = (full or "").lower()
    has_fetch_err = False
    fetch_err_reason = ""
    if kind == "APT_UPDATE":
        if "w: some index files failed to download" in low_full or "w: failed to fetch" in low_full or "failed to fetch" in low_full:
            has_fetch_err = True
            if "temporary failure resolving" in low_full or "could not resolve" in low_full or "no servers could be reached" in low_full:
                fetch_err_reason = "Gagal mengunduh indeks repositori: resolusi DNS bermasalah."
            elif "connection refused" in low_full or "could not connect" in low_full:
                fetch_err_reason = "Gagal mengunduh indeks repositori: koneksi jaringan ditolak / terputus."
            else:
                fetch_err_reason = "Sebagian atau seluruh indeks repositori gagal diunduh (periksa URL repositori/koneksi)."

    if failed:
        result_ok = False
        err_desc = errmsg or "Eksekusi proses apt gagal"
        msg = json.dumps({
            "type": kind,
            "output": (full or partial)[-APT_AGENT_OUTPUT_MAX:],
            "apt": apt,
            "error": err_desc,
            "rc": 1,
        })
    elif proc is not None and proc.returncode != 0:
        # Jika apt update selesai membaca daftar paket meski ada repositori yang gagal diunduh (rc=100)
        if kind == "APT_UPDATE" and ("reading package lists" in low_full or has_fetch_err):
            result_ok = True
            msg = json.dumps({
                "type": kind,
                "output": full[-APT_AGENT_OUTPUT_MAX:],
                "apt": apt,
                "has_fetch_err": True,
                "fetch_err_reason": fetch_err_reason or "Sebagian indeks repositori gagal diunduh.",
                "warning": fetch_err_reason or "Sebagian indeks repositori gagal diunduh.",
                "rc": proc.returncode,
            })
        else:
            result_ok = False
            if "no new privileges" in low_full or "permission denied" in low_full or "a password is required" in low_full or proc.returncode in (126, 127):
                err_desc = _apt_sudo_denied_hint(full or f"rc={proc.returncode}")
            else:
                err_desc = f"Proses apt selesai dengan kode kegagalan (rc={proc.returncode})"
            msg = json.dumps({
                "type": kind,
                "output": full[-APT_AGENT_OUTPUT_MAX:],
                "apt": apt,
                "error": err_desc,
                "rc": proc.returncode,
            })
    else:
        result_ok = True
        msg = json.dumps({
            "type": kind,
            "output": full[-APT_AGENT_OUTPUT_MAX:],
            "apt": apt,
            "has_fetch_err": has_fetch_err,
            "fetch_err_reason": fetch_err_reason,
            "warning": fetch_err_reason if has_fetch_err else None,
            "rc": proc.returncode if proc else 0,
        })

    result = {"status": "success" if result_ok else "failed", "result": msg}
    print(f"[APT] {kind} (rid={rid}) -> {result['status']} (result {len(msg)} byte)")
    http_json_request(cfg, f"/api/logs/{rid}/result", "POST", result)


# ---------------------------------------------------------------------------
# Terminal Bawaan: shell root interaktif (unit "SHELL")
# ---------------------------------------------------------------------------
_SHELL_LOCK = threading.Lock()
_SHELL_RIDS: set[int] = set()


def _shell_sudo_denied_hint(err: str) -> str:
    """Petunjuk bila wrapper pantau-shell belum terpasang/berhak di host klien."""
    low_err = (err or "").lower()
    if "no new privileges" in low_err:
        return (
            "[terminal tidak dapat dibuka] Konfigurasi systemd agen pada host/container ini "
            "mengaktifkan flag 'NoNewPrivileges' atau isolasi namespace, sehingga kernel menolak eskalasi sudo.\n"
            "Perbaiki (sebagai root di host ini):\n"
            "  sudo sed -i 's/^PrivateTmp=yes/PrivateTmp=no/' /etc/systemd/system/agent_pantau.service\n"
            "  sudo sed -i 's/^ProtectKernelTunables=yes/ProtectKernelTunables=no/' /etc/systemd/system/agent_pantau.service\n"
            "  sudo sed -i 's/^ProtectControlGroups=yes/ProtectControlGroups=no/' /etc/systemd/system/agent_pantau.service\n"
            "  sudo sed -i 's/^ProtectClock=yes/ProtectClock=no/' /etc/systemd/system/agent_pantau.service\n"
            "  echo 'NoNewPrivileges=no' | sudo tee -a /etc/systemd/system/agent_pantau.service\n"
            "  sudo systemctl daemon-reload && sudo systemctl restart agent_pantau.service\n"
            "Rincian teknis:\n" + (err or "")
        )
    return (
        "[terminal tidak dapat dibuka] hak sudo agen 'pantau' untuk wrapper "
        "pantau-shell belum tersedia di host ini.\n"
        "Perbaiki (sebagai root di host ini):\n"
        "  cd <folder-paket-pantau>/package && sudo bash install.sh\n"
        "(memasang ulang sudoers + wrapper pantau-shell; aman/idempotent.)\n"
        "Rincian teknis:\n" + (err or "")
    )


def _stdin_writer_thread_polled(cfg: dict, rid: int, proc, poll_secs: float) -> None:
    """Terus ambil ketikan admin dari dashboard lalu tulis ke stdin proses.

    Berhenti saat proses selesai. Semua error ditelan supaya tidak mematikan
    shell; admin cukup mengetik ulang bila gagal terkirim.
    """
    while True:
        time.sleep(poll_secs)
        if proc.poll() is not None:
            return
        try:
            code, data = http_json_request(cfg, f"/api/logs/{rid}/input", "GET", timeout=10)
        except Exception:  # noqa: BLE001 - loop diagnostik, jangan matikan apa pun
            continue
        if code != 200 or not data.get("data"):
            continue
        text = data["data"]
        try:
            #bash di pty sudah menggema karakter yang diketik, jadi kita TIDAK
            # menulis baris tambahan ke output - persis seperti terminal SSH.
            proc.stdin.write(text.encode("utf-8", errors="replace"))
            proc.stdin.flush()
        except (OSError, ValueError):
            return


def _run_shell_inner(cfg: dict, rid: int) -> None:
    """Jalankan shell root interaktif dengan streaming live ke Dashboard.

    Berbeda dari alur apt, ini bukan proses sekali jalan: shell hidup sampai
    admin mengetik "exit", dashboard menutup jendelanya, atau timeout 8 jam.
    Semua ketikan admin diteruskan apa adanya ke stdin shell lewat pty.
    """
    cmd = [PANTAU_SHELL_CMD] if IS_ROOT else ["/usr/bin/sudo", "-n", PANTAU_SHELL_CMD]
    output_parts: list[str] = []
    raw_len = 0
    truncated = False
    last_post = 0.0
    started = time.monotonic()
    last_activity = started
    closed = False

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.PIPE, start_new_session=True)
    except OSError as e:
        http_json_request(cfg, f"/api/logs/{rid}/result", "POST",
                          {"status": "failed",
                           "result": f"[gagal membuka shell: {e}]"})
        return

    # Admin yang mengetik; agen tidak pernah menyuntik perintah ke shell.
    threading.Thread(target=_stdin_writer_thread_polled,
                     args=(cfg, rid, proc, SHELL_IDLE_POLL_SECS),
                     name=f"shell-input-{rid}", daemon=True).start()

    try:
        while True:
            now = time.monotonic()
            if now - started > SHELL_TIMEOUT_SECS:
                closed = True
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except (OSError, ProcessLookupError, PermissionError):
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except (OSError, ProcessLookupError, PermissionError):
                        pass
                break
            try:
                rdy = select.select([proc.stdout], [], [], 1.0)[0]
            except (OSError, ValueError):
                break
            if rdy:
                raw = proc.stdout.read1(8192)
                if raw:
                    # KEEP \r + warna SGR: pty shell menghasilkan keduanya, dan
                    # dashboard harus bisa merender terminal sungguhan.
                    text = _keep_sgr(raw.decode("utf-8", errors="replace"))
                    if text:
                        if "\x0c" in text or "\x1b[2J" in text or "\x1b[3J" in text:
                            output_parts = [text]
                            raw_len = len(text)
                        else:
                            output_parts.append(text)
                            raw_len += len(text)
                        last_activity = time.monotonic()
                elif proc.poll() is not None:
                    break
            # Kirim output segera setelah berubah supaya ketikan admin terasa
            # responsif (shell interaktif, bukan laporan berkala).
            if raw_len and (now - last_post) >= SHELL_POST_MIN_SECS:
                live = termify(_tail_parts(output_parts, SHELL_PROGRESS_TAIL_CHARS))
                if live:
                    http_json_request(cfg, f"/api/logs/{rid}/progress", "POST",
                                      {"chunk": live, "replace": True})
                    last_post = now
            if raw_len > SHELL_OUTPUT_MAX:
                excess = raw_len - SHELL_OUTPUT_MAX
                while excess > 0 and output_parts:
                    part = output_parts[0]
                    if len(part) <= excess:
                        excess -= len(part)
                        output_parts.pop(0)
                    else:
                        output_parts[0] = part[excess:]
                        excess = 0
                raw_len = SHELL_OUTPUT_MAX
                truncated = True
        if proc.returncode is None:
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
    finally:
        with _SHELL_LOCK:
            _SHELL_RIDS.discard(rid)

    full = termify("".join(output_parts))
    if truncated and full:
        full = ("[catatan: output awal dibuang agen karena melebihi kuota]\n\n"
                + full.strip("\n") + "\n")
    elif full:
        full = full.strip("\n")

    live = termify(_tail_parts(output_parts, SHELL_PROGRESS_TAIL_CHARS))
    if live:
        http_json_request(cfg, f"/api/logs/{rid}/progress", "POST",
                          {"chunk": live, "replace": True})

    is_ok = True
    if closed:
        msg = (full + "\n\n[catatan: sesi shell ditutup otomatis karena "
                      "melewati batas waktu 8 jam]").strip("\n")
    elif proc.returncode not in (0, None):
        is_ok = False
        msg = _shell_sudo_denied_hint(full or f"shell berhenti rc={proc.returncode}")
    else:
        msg = full or "[shell ditutup tanpa output]"

    print(f"[SHELL] rid={rid} selesai rc={proc.returncode} ({len(msg)} byte)")
    http_json_request(cfg, f"/api/logs/{rid}/result", "POST",
                      {"status": "success" if is_ok else "failed", "result": msg})


def _run_shell_in_thread(cfg: dict, rid: int) -> None:
    """Pemicu thread shell; menolak dua sesi shell pada satu server."""
    with _SHELL_LOCK:
        if _SHELL_RIDS:
            http_json_request(cfg, f"/api/logs/{rid}/result", "POST",
                              {"status": "failed",
                               "result": "Sesi shell lain masih terbuka di server ini."})
            return
        _SHELL_RIDS.add(rid)
    try:
        _run_shell_inner(cfg, rid)
    finally:
        with _SHELL_LOCK:
            _SHELL_RIDS.discard(rid)


def fetch_log_lines(unit: str, lines: int) -> str:
    """Ambil log layanan: unit journal, atau file SYSLOG/AUTH (dengan fallback journalctl)."""
    if unit == "SYSLOG":
        if os.path.isfile(SYSLOG_FILE):
            return _tail_file(SYSLOG_FILE, lines)
        res = _run_cmd(["journalctl", "-n", str(lines), "--no-pager"], timeout=30)
        return (res.stdout.rstrip() if res else "") or f"[file {SYSLOG_FILE} tidak ditemukan]"
    if unit == "AUTH":
        for cand in (AUTH_FILE, "/var/log/secure"):
            if os.path.isfile(cand):
                return _tail_file(cand, lines)
        res = _run_cmd(
            ["journalctl", "-u", "ssh", "-u", "sshd", "-u", "sudo", "-u", "systemd-logind",
             "-n", str(lines), "--no-pager"],
            timeout=30,
        )
        return (res.stdout.rstrip() if res else "") or "[log autentikasi tidak ditemukan]"
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
    """Aktivitas login user dari wtmp (last), utmp (who), dan auth log / journalctl.

    Mendukung penuh distribusi Linux modern tanpa rsyslog (Ubuntu 24.04 LTS Noble,
    Debian 12, RHEL 9) maupun sistem tradisional berbasis /var/log/auth.log atau secure.
    """
    events: list[dict] = []
    seen_keys: set[str] = set()

    # 1. Prioritas Sesi Aktif Real-Time (who)
    try:
        active_sessions = _parse_who()
        for s in active_sessions:
            u = s.get("user", "")
            if not u or u == "pantau":
                continue
            src = s.get("from") or "(lokal)"
            tty = s.get("tty", "ssh")
            t = s.get("time", "")
            ev = {
                "ts": t,
                "user": u,
                "type": "sukses",
                "from": src,
                "method": f"{tty} (aktif)",
            }
            k = f"{u}:{t}:{src}:{tty}"
            if k not in seen_keys:
                seen_keys.add(k)
                events.append(ev)
    except Exception:
        pass

    # 2. Riwayat Sesi dari Database Akuntansi Login Linux (last -F)
    try:
        res_last = _run_cmd(["last", "-n", "80", "-F"], timeout=5)
        if res_last and res_last.stdout:
            for line in res_last.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 8 and parts[0] not in ("reboot", "wtmp"):
                    u = parts[0]
                    if u == "pantau":
                        continue
                    tty = parts[1]
                    src = parts[2]
                    raw_time = " ".join(parts[3:8])
                    status = " ".join(parts[8:])
                    try:
                        dt = datetime.strptime(raw_time, "%a %b %d %H:%M:%S %Y")
                        ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        ts_str = raw_time
                    is_active = "still logged in" in status
                    method_desc = f"{tty} (aktif)" if is_active else f"{tty} (selesai)"
                    from_clean = src if (src and src != ":0" and not src.startswith(":")) else "(lokal)"
                    k = f"{u}:{ts_str}:{from_clean}:{tty}"
                    if k not in seen_keys:
                        seen_keys.add(k)
                        events.append({
                            "ts": ts_str,
                            "user": u,
                            "type": "sukses",
                            "from": from_clean,
                            "method": method_desc,
                        })
    except Exception:
        pass

    # 3. Log Otentikasi Terperinci (auth.log, secure, atau systemd journalctl)
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

    data = ""
    for auth_path in (AUTH_FILE, "/var/log/secure"):
        if os.path.isfile(auth_path):
            try:
                with open(auth_path, "rb") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    chunk = min(size, 8 * 1024 * 1024)
                    f.seek(size - chunk)
                    data = f.read().decode("utf-8", errors="replace")
                if data:
                    break
            except OSError:
                pass

    if not data:
        # Fallback journalctl untuk host tanpa file auth fisik
        res_j = _run_cmd(
            ["journalctl", "-u", "ssh", "-u", "sshd", "-u", "sudo", "-u", "systemd-logind",
             "-n", "600", "--no-pager"],
            timeout=10,
        )
        if res_j and res_j.stdout:
            data = res_j.stdout

    if data:
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
                k = f"{user}:{ts}:{src}:{kind}:{method[:40]}"
                if k not in seen_keys:
                    seen_keys.add(k)
                    events.append({"ts": ts, "user": user, "type": kind, "from": src, "method": method})
                break

    events.sort(key=lambda e: str(e.get("ts", "")), reverse=True)
    return events[: max(0, max_events)]


_security_cache: dict = {"at": 0.0, "data": None}


def collect_security() -> dict:
    """Ringkasan keamanan dari auth log / journalctl (window ±4 MB terakhir).

    Dipakai indikator 'status masalah' pada Dashboard (serangan/brute force).
    Dihitung maksimal sekali per 60 detik karena auth.log sering ditulis.

    Kembalikan: {"failed", "invalid_users", "source_ips": {ip: n}, "window": [start,end]}
    """
    now = time.monotonic()
    if _security_cache["data"] is not None and now - _security_cache["at"] < 60:
        return _security_cache["data"]

    out: dict = {"failed": 0, "invalid_users": 0, "source_ips": {}, "window": []}
    data = ""
    for cand in (AUTH_FILE, "/var/log/secure"):
        if os.path.isfile(cand):
            try:
                with open(cand, "rb") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    chunk = min(size, 4 * 1024 * 1024)
                    f.seek(size - chunk)
                    data = f.read().decode("utf-8", errors="replace")
                if data:
                    break
            except OSError:
                pass

    if not data:
        # Fallback journalctl untuk host tanpa file auth fisik
        res_j = _run_cmd(
            ["journalctl", "-u", "ssh", "-u", "sshd", "-n", "300", "--no-pager"],
            timeout=8,
        )
        if res_j and res_j.stdout:
            data = res_j.stdout

    lines = data.splitlines() if data else []
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


_cron_cache: dict = {"at": 0.0, "data": None}


def collect_cron_jobs() -> dict:
    """Kumpulkan daftar tugas terjadwal dari crontab sistem, user, dan systemd timers."""
    now = time.monotonic()
    if _cron_cache["data"] is not None and now - _cron_cache["at"] < 30:
        return _cron_cache["data"]

    items: list[dict] = []
    
    # 1. Parse /etc/crontab (system-wide)
    if os.path.isfile("/etc/crontab"):
        try:
            with open("/etc/crontab", "r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f, 1):
                    raw = line.strip()
                    if not raw or raw.startswith("#"):
                        continue
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", raw):
                        continue
                    parts = re.split(r"\s+", raw)
                    if len(parts) >= 7:
                        sched = " ".join(parts[0:5])
                        user = parts[5]
                        cmd = " ".join(parts[6:])
                        items.append({
                            "type": "cron",
                            "source": "/etc/crontab",
                            "line": idx,
                            "schedule": sched,
                            "user": user,
                            "command": cmd,
                            "is_managed": False,
                            "ident": "",
                            "is_enabled": True,
                        })
        except OSError:
            pass

    # 2. Parse /etc/cron.d/*
    for path in sorted(glob.glob("/etc/cron.d/*")):
        if os.path.basename(path).startswith("."):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f, 1):
                    raw = line.strip()
                    is_enabled = True
                    if raw.startswith("# DISABLED_BY_PANTAU"):
                        is_enabled = False
                        raw = raw[len("# DISABLED_BY_PANTAU"):].strip()
                    elif not raw or raw.startswith("#"):
                        continue
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", raw):
                        continue
                    parts = re.split(r"\s+", raw)
                    if len(parts) >= 7:
                        sched = " ".join(parts[0:5])
                        user = parts[5]
                        cmd = " ".join(parts[6:])
                        bname = os.path.basename(path)
                        is_managed = bname.startswith("pantau-")
                        ident = bname[len("pantau-"):] if is_managed else ""
                        items.append({
                            "type": "cron",
                            "source": path,
                            "line": idx,
                            "schedule": sched,
                            "user": user,
                            "command": cmd,
                            "is_managed": is_managed,
                            "ident": ident,
                            "is_enabled": is_enabled,
                        })
        except OSError:
            pass

    # 3. Systemd Timers (Modern Linux schedulers)
    timers: list[dict] = []
    try:
        res = _run_cmd(["systemctl", "list-timers", "--all", "--no-pager"], timeout=5)
        if res and res.returncode == 0:
            lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
            for l in lines[1:]:
                if "ACTIVATES" in l or "timers listed" in l:
                    continue
                parts = l.split()
                timer_unit = [p for p in parts if p.endswith(".timer")]
                svc_unit = [p for p in parts if p.endswith(".service") or p.endswith(".target")]
                if timer_unit and svc_unit:
                    timers.append({
                        "timer": timer_unit[0],
                        "activates": svc_unit[0],
                        "raw": l,
                    })
    except Exception:
        pass

    out = {"jobs": items[:100], "timers": timers[:50]}
    _cron_cache["data"] = out
    _cron_cache["at"] = now
    return out


_fw_cache: dict = {"at": 0.0, "data": None}


def collect_firewall() -> dict:
    """Inspeksi status firewall (UFW dan/atau iptables) dan daftar IP terblokir."""
    now = time.monotonic()
    if _fw_cache["data"] is not None and now - _fw_cache["at"] < 20:
        return _fw_cache["data"]

    fw: dict = {
        "backend": "unknown",
        "status": "inactive",
        "rules": [],
        "blocked_ips": [],
    }

    # 1. Panggil pantau-firewall status jika non-root
    raw_output = ""
    if not IS_ROOT:
        res = _run_cmd(["/usr/bin/sudo", "-n", PANTAU_FIREWALL, "status"], timeout=6)
        if res and res.returncode == 0:
            raw_output = res.stdout
    else:
        # Root langsung
        try:
            r_ufw = _run_cmd(["ufw", "status", "verbose"], timeout=5)
            r_ipt = _run_cmd(["iptables", "-L", "INPUT", "-n", "-v", "--line-numbers"], timeout=5)
            raw_output = (r_ufw.stdout if r_ufw else "") + "\n" + (r_ipt.stdout if r_ipt else "")
        except Exception:
            pass

    if raw_output:
        lines = [l.strip() for l in raw_output.splitlines() if l.strip()]
        has_ufw = any("ufw status" in l.lower() or "status: " in l.lower() for l in lines)
        if has_ufw:
            fw["backend"] = "ufw"
            for l in lines:
                if l.lower().startswith("status:"):
                    fw["status"] = "active" if "active" in l.lower() and "inactive" not in l.lower() else "inactive"
                    break
        else:
            fw["backend"] = "iptables"
            fw["status"] = "active"

        in_rules = False
        in_iptables = False
        for l in lines:
            if l.startswith("--- IPTABLES"):
                in_iptables = True
                in_rules = False
                continue
            if not in_iptables:
                if l.startswith("--"):
                    in_rules = True
                    continue
                if in_rules:
                    fw["rules"].append(l[:120])
            else:
                parts = l.split()
                if len(parts) >= 9 and parts[3] == "DROP":
                    fw["blocked_ips"].append({
                        "num": parts[0],
                        "pkts": parts[1],
                        "bytes": parts[2],
                        "source": parts[8],
                    })

    fw["rules"] = fw["rules"][:100]
    fw["blocked_ips"] = fw["blocked_ips"][:100]
    _fw_cache["data"] = fw
    _fw_cache["at"] = now
    return fw


_ports_cache: dict = {"at": 0.0, "data": None}


def collect_listening_ports() -> list[dict]:
    """Audit listening ports & socket via ss -tulpn (dengan hak sudo ss agar nama proses terbaca)."""
    now = time.monotonic()
    if _ports_cache["data"] is not None and now - _ports_cache["at"] < 15:
        return _ports_cache["data"]

    ports: list[dict] = []
    cmd = [SS_BIN, "-tulpn"] if IS_ROOT else ["/usr/bin/sudo", "-n", SS_BIN, "-tulpn"]
    res = _run_cmd(cmd, timeout=5)

    if res and res.returncode == 0:
        for line in res.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                proto = parts[0].lower()
                local = parts[4]
                if ":" in local:
                    ip, port_str = local.rsplit(":", 1)
                else:
                    continue
                try:
                    port = int(port_str)
                except ValueError:
                    continue
                proc = ""
                pid = None
                pname = ""
                tail = " ".join(parts[5:])
                m = re.search(r'"([^"]+)",pid=(\d+)', tail)
                if m:
                    pname = m.group(1)
                    pid = int(m.group(2))
                    proc = f"{pname} (PID {pid})"
                elif len(parts) >= 7:
                    proc = parts[6]
                is_loopback = ip in ("127.0.0.1", "::1", "127.0.0.53", "127.0.0.54") or ip.startswith("127.0.0.") or ip.endswith("%lo")
                ports.append({
                    "proto": proto,
                    "ip": ip,
                    "port": port,
                    "proc": proc,
                    "pid": pid,
                    "pname": pname,
                    "is_loopback": is_loopback,
                    "is_public": not is_loopback,
                })

    ports = ports[:60]
    _ports_cache["data"] = ports
    _ports_cache["at"] = now
    return ports


_ssl_cache: dict = {"at": 0.0, "data": None}


def _parse_agent_cert_date(date_str: str) -> datetime | None:
    """Parsing tanggal sertifikat SSL dengan dukungan berbagai format dan zona waktu."""
    if not date_str:
        return None
    s = re.sub(r"\s+", " ", date_str.strip())
    for fmt in (
        "%b %d %H:%M:%S %Y %Z",
        "%b %d %H:%M:%S %Y GMT",
        "%b %d %H:%M:%S %Y UTC",
        "%b %d %H:%M:%S %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y%m%d%H%M%SZ",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def collect_ssl_certs() -> list[dict]:
    """Inspeksi berkas sertifikat SSL/TLS untuk mendeteksi masa kedaluwarsa."""
    now = time.monotonic()
    if _ssl_cache["data"] is not None and now - _ssl_cache["at"] < 300:
        return _ssl_cache["data"]

    certs: list[dict] = []
    patterns = [
        "/etc/letsencrypt/live/*/cert.pem",
        "/etc/letsencrypt/live/*/fullchain.pem",
        "/etc/ssl/certs/*.crt",
        "/etc/nginx/ssl/*.crt",
        "/etc/apache2/ssl/*.crt",
    ]
    seen_files = set()
    found_paths = []
    custom_reals = set()

    # Sertifikat kustom yang didaftarkan lewat Pantau
    custom_conf = "/etc/pantau/custom_ssl.conf"
    if os.path.isfile(custom_conf):
        try:
            with open(custom_conf, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    cpath = line.strip()
                    if cpath and not cpath.startswith("#") and os.path.isfile(cpath):
                        try:
                            r = os.path.realpath(cpath)
                            custom_reals.add(r)
                            if r not in seen_files:
                                seen_files.add(r)
                                found_paths.append(cpath)
                        except OSError:
                            continue
        except OSError:
            pass

    for pat in patterns:
        for p in sorted(glob.glob(pat)):
            try:
                real = os.path.realpath(p)
                if real not in seen_files:
                    seen_files.add(real)
                    found_paths.append(p)
            except OSError:
                continue

    utc_now = datetime.now(timezone.utc)
    for p in found_paths[:50]:
        try:
            subject = ""
            issuer = ""
            sans = []
            cn = ""
            not_after = None

            # 1. Pustaka standar internal: ssl._ssl._test_decode_cert
            try:
                decoded = ssl._ssl._test_decode_cert(p)
                if decoded:
                    if "subject" in decoded:
                        subject = ", ".join(f"{k}={v}" for rdn in decoded["subject"] for k, v in rdn)
                        cn = next((v for rdn in decoded["subject"] for k, v in rdn if k == "commonName"), "")
                    if "issuer" in decoded:
                        issuer = ", ".join(f"{k}={v}" for rdn in decoded["issuer"] for k, v in rdn)
                    if "subjectAltName" in decoded:
                        sans = [str(v) for k, v in decoded["subjectAltName"] if k == "DNS"]
                    if "notAfter" in decoded:
                        not_after = _parse_agent_cert_date(decoded["notAfter"])
            except Exception:
                decoded = None

            # 2. Fallback: CLI openssl x509 bawaan sistem
            if not not_after:
                try:
                    res = subprocess.run(
                        ["openssl", "x509", "-in", p, "-noout", "-subject", "-issuer", "-enddate", "-ext", "subjectAltName"],
                        capture_output=True,
                        text=True,
                        timeout=5.0,
                    )
                    if res.returncode == 0:
                        for line in res.stdout.splitlines():
                            line_s = line.strip()
                            if line_s.startswith("subject=") and not subject:
                                subject = line_s.split("subject=", 1)[1].strip()
                                cn_m = re.search(r"(?:^|,\s*)CN\s*=\s*([^,]+)", subject, re.IGNORECASE)
                                if cn_m:
                                    cn = cn_m.group(1).strip()
                            elif line_s.startswith("issuer=") and not issuer:
                                issuer = line_s.split("issuer=", 1)[1].strip()
                            elif line_s.startswith("notAfter="):
                                date_str = line_s.split("notAfter=", 1)[1].strip()
                                not_after = _parse_agent_cert_date(date_str)
                            elif "DNS:" in line_s and not sans:
                                sans = [item.strip()[4:] for item in line_s.split(",") if item.strip().startswith("DNS:")]
                except Exception:
                    pass

            if not not_after:
                continue

            days_left = (not_after - utc_now).days

            is_custom = False
            try:
                is_custom = os.path.realpath(p) in custom_reals
            except OSError:
                pass

            domains = sans if sans else ([cn] if cn else ([subject] if subject else []))

            certs.append({
                "path": p,
                "subject": subject,
                "domains": domains,
                "issuer": issuer,
                "not_after": not_after.isoformat(),
                "days_left": days_left,
                "is_expired": days_left < 0,
                "is_critical": 0 <= days_left <= 14,
                "is_warning": 14 < days_left <= 30,
                "is_custom": is_custom,
            })
        except Exception:
            continue

    _ssl_cache["data"] = certs
    _ssl_cache["at"] = now
    return certs


_syslog_cache: dict = {"at": 0.0, "data": []}


def collect_system_logs(lines: int = 25) -> list[dict]:
    """Kumpulkan log galat sistem kritis (journalctl priority err, crit, alert, emerg)."""
    now = time.monotonic()
    if _syslog_cache["data"] and now - _syslog_cache["at"] < 30:
        return _syslog_cache["data"]

    events: list[dict] = []
    # Jalankan journalctl -p 3 -r (0=emerg, 1=alert, 2=crit, 3=err, -r = terbaru di atas)
    res = _run_cmd(
        ["journalctl", "-p", "3", "-n", str(lines), "-r", "--no-pager", "-o", "json"],
        timeout=5,
    )
    if res and res.returncode == 0:
        for ln in res.stdout.splitlines():
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
                ts = d.get("__REALTIME_TIMESTAMP")
                time_str = ""
                if ts:
                    try:
                        dt = datetime.fromtimestamp(int(ts) / 1000000.0, timezone.utc)
                        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        time_str = str(ts)
                unit = d.get("_SYSTEMD_UNIT") or d.get("SYSLOG_IDENTIFIER") or "-"
                msg = (d.get("MESSAGE") or "").strip()[:400]
                try:
                    prio = int(d.get("PRIORITY", 3))
                except Exception:
                    prio = 3
                events.append({
                    "time": time_str,
                    "unit": unit,
                    "message": msg,
                    "priority": prio,
                })
            except Exception:
                continue

    _syslog_cache["data"] = events
    _syslog_cache["at"] = now
    return events


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
    cmd = [PANTAU_HISTORY_CMD, str(user)] if IS_ROOT else ["/usr/bin/sudo", "-n", PANTAU_HISTORY_CMD, str(user)]
    res = _run_cmd(cmd, timeout=15)
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
        elif unit in ("APT_UPDATE", "APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE", "APT_FIX", "PKG_UPGRADE", "PKG_CLEAN"):
            detail_val = str(req.get("detail", "") or "")
            threading.Thread(
                target=_run_apt_in_thread, args=(cfg, rid, unit, detail_val), daemon=True
            ).start()
            continue
        elif unit == "PKG_LIST":
            try:
                pkgs = collect_installed_packages()
                result = {"status": "success", "result": json.dumps(pkgs)}
            except Exception as e:
                result = {"status": "failed", "result": f"Gagal membaca daftar paket: {e}"}
        elif unit == "SYSTEMD_LIST":
            try:
                units = collect_systemd_units()
                result = {"status": "success", "result": json.dumps(units)}
            except Exception as e:
                result = {"status": "failed", "result": f"Gagal membaca unit systemd: {e}"}
        elif unit == "PKG_CLEAR_CACHE":
            try:
                pkg_name = str(req.get("detail", "") or "").strip()
                res_msg = clear_package_cache(pkg_name)
                result = {"status": "success", "result": res_msg}
            except Exception as e:
                result = {"status": "failed", "result": f"Gagal membersihkan cache paket: {e}"}
        elif unit == "PKG_LOGS":
            try:
                pkg_name = str(req.get("detail", "") or "").strip()
                log_out = get_package_logs(pkg_name, lines)
                result = {"status": "success", "result": log_out}
            except Exception as e:
                result = {"status": "failed", "result": f"Gagal membaca log paket: {e}"}
        elif unit == "SHELL":
            # Terminal Bawaan: shell root interaktif milik admin dashboard.
            threading.Thread(
                target=_run_shell_in_thread, args=(cfg, rid), daemon=True
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
# File Manager operations (Berkas)
# ---------------------------------------------------------------------------
def run_file_op(action: str, params: dict) -> dict:
    """Jalankan operasi file melalui wrapper /usr/local/sbin/pantau-file (sudo root)."""
    payload = json.dumps({"action": action, "params": params}).encode("utf-8")
    if os.path.exists(PANTAU_FILE_CMD):
        try:
            cmd = [PANTAU_FILE_CMD] if IS_ROOT else ["/usr/bin/sudo", "-n", PANTAU_FILE_CMD]
            proc = subprocess.run(
                cmd,
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
            )
            if proc.stdout:
                try:
                    return json.loads(proc.stdout.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    pass
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            if err:
                return {"ok": False, "error": f"[pantau-file error] {err}"}
        except Exception as e:
            return {"ok": False, "error": f"Eksekusi pantau-file gagal: {e}"}

    # Fallback jika wrapper sudo belum terpasang atau jalan native
    try:
        proc = subprocess.run(
            [sys.executable, PANTAU_FILE_CMD],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
        )
        if proc.stdout:
            return json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"ok": False, "error": f"Fallback pantau-file gagal: {e}"}
    return {"ok": False, "error": "pantau-file tidak dapat dieksekusi"}


def _file_worker_loop(cfg: dict) -> None:
    """Worker background untuk merespons permintaan file manager secara instan (long-poll)."""
    while True:
        try:
            code, data = http_json_request(cfg, "/api/agent/file-requests", method="GET", timeout=25)
            if code == 200 and data and isinstance(data.get("requests"), list):
                for req in data["requests"]:
                    req_id = req.get("id")
                    action = req.get("action")
                    params = req.get("params", {})
                    if not req_id or not action:
                        continue
                    res = run_file_op(action, params)
                    http_json_request(
                        cfg,
                        f"/api/agent/file-requests/{req_id}/result",
                        method="POST",
                        data=res,
                        timeout=20,
                    )
            elif code in (401, 403):
                # API key salah / server belum siap
                time.sleep(10.0)
            elif code == 0:
                time.sleep(2.0)
        except Exception:
            time.sleep(2.0)


# ---------------------------------------------------------------------------
# Realtime Terminal (PTY + WebSocket Stream Bridge)
# ---------------------------------------------------------------------------
def _set_terminal_winsize(fd: int, rows: int, cols: int) -> None:
    try:
        winsize = struct.pack("HHHH", int(rows), int(cols), 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except Exception:
        pass


# Pola escape sequence probe/query terminal dan respon internal xterm.js
DA_QUERY_PATTERN = re.compile(
    r"\x1b\[c|\x1b\[0c|\x1b\[>c|\x1b\[>0c|\x1b\[>q|\x1b\]1[01];\?(?:\x07|\x1b\\)"
)
DA_RESP_PATTERN = re.compile(
    r"\x1b\[[?>!][0-9;]*c|\x1b\[\??[0-9]+;[0-9]+R|\x1b\[[0-9]+n|\x1b\](?:10|11);[^\x07\x1b]*(?:\x07|\x1b\\)"
)


def _run_terminal_session(cfg: dict, session_id: str) -> None:
    """Jalankan proses shell interaktif di pseudo-terminal (PTY) realtime.

    Terkoneksi langsung ke sesi WebSocket browser via bridge dashboard Pantau.
    """
    master_fd, slave_fd = pty.openpty()
    _set_terminal_winsize(master_fd, 24, 80)

    if os.path.exists(PANTAU_SHELL_CMD):
        cmd = [PANTAU_SHELL_CMD] if IS_ROOT else ["/usr/bin/sudo", "-n", PANTAU_SHELL_CMD]
    else:
        cmd = ["/bin/bash", "-i"]

    def _preexec():
        os.setsid()
        try:
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=_preexec,
            close_fds=True,
        )
    except Exception as e:
        try:
            os.close(slave_fd)
            os.close(master_fd)
        except Exception:
            pass
        http_json_request(
            cfg,
            f"/api/agent/terminal/{session_id}/stdout",
            method="POST",
            data={"chunk": f"\r\n[Gagal membuka terminal: {e}]\r\n"},
            timeout=5,
        )
        http_json_request(cfg, f"/api/agent/terminal/{session_id}/close", method="POST", timeout=5)
        return

    # Tutup slave_fd di proses induk agar master_fd menerima EOF saat anak selesai
    try:
        os.close(slave_fd)
    except Exception:
        pass

    stop_event = threading.Event()

    bash_pgrp = proc.pid
    try:
        bash_pgrp = os.getpgid(proc.pid)
    except Exception:
        pass

    def check_terminal_busy() -> bool:
        # 1. POSIX PTY foreground group check (untuk bash langsung tanpa tmux)
        try:
            curr_pgrp = os.tcgetpgrp(master_fd)
            if curr_pgrp > 0 and curr_pgrp != bash_pgrp:
                return True
        except Exception:
            pass

        # 2. Kernel proc stat check untuk bash di bawah tmux / sudo wrapper
        try:
            for pid_str in os.listdir("/proc"):
                if not pid_str.isdigit():
                    continue
                try:
                    with open(f"/proc/{pid_str}/comm", "r") as cf:
                        if cf.read().strip() != "bash":
                            continue
                    with open(f"/proc/{pid_str}/cmdline", "rb") as cf:
                        cmd = cf.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
                    if "--rcfile" in cmd and "pantau-shellrc" in cmd:
                        with open(f"/proc/{pid_str}/stat", "r") as sf:
                            c = sf.read()
                            idx = c.rfind(")")
                            if idx != -1:
                                fields = c[idx + 2:].split()
                                if len(fields) >= 6:
                                    pgrp = int(fields[2])
                                    tpgid = int(fields[5])
                                    if tpgid > 0 and pgrp != tpgid:
                                        return True
                except Exception:
                    continue
        except Exception:
            pass

        return False

    def pty_reader():
        pending_out = []
        last_busy_state = False
        last_busy_check = 0.0

        try:
            while not stop_event.is_set():
                now = time.time()
                r, _, _ = select.select([master_fd], [], [], 0.05)
                if not r:
                    if proc.poll() is not None:
                        break
                    # Cek berkala saat terminal idle untuk mendeteksi selesainya proses tanpa stdout baru
                    if now - last_busy_check >= 0.25:
                        last_busy_check = now
                        curr_busy = check_terminal_busy()
                        if curr_busy != last_busy_state:
                            last_busy_state = curr_busy
                            http_json_request(
                                cfg,
                                f"/api/agent/terminal/{session_id}/stdout",
                                method="POST",
                                data={"chunk": "", "busy": curr_busy},
                                timeout=5,
                            )
                    continue

                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break
                if not data:
                    break

                chunks = [data]
                while True:
                    r, _, _ = select.select([master_fd], [], [], 0.005)
                    if not r:
                        break
                    try:
                        more = os.read(master_fd, 4096)
                        if not more:
                            break
                        chunks.append(more)
                    except OSError:
                        break

                chunk = b"".join(chunks).decode("utf-8", errors="replace")
                chunk = DA_QUERY_PATTERN.sub("", chunk)
                if not chunk and not pending_out:
                    continue
                if pending_out:
                    chunk = "".join(pending_out) + chunk
                    pending_out.clear()

                last_busy_check = time.time()
                curr_busy = check_terminal_busy()
                last_busy_state = curr_busy

                code, _ = http_json_request(
                    cfg,
                    f"/api/agent/terminal/{session_id}/stdout",
                    method="POST",
                    data={"chunk": chunk, "busy": curr_busy},
                    timeout=10,
                )
                if code == 410:
                    break
                elif code == 0:
                    pending_out.append(chunk)
                    if len(pending_out) > 50:
                        pending_out.pop(0)
                    time.sleep(0.5)
        except Exception:
            pass
        finally:
            stop_event.set()

    def stdin_poller():
        try:
            while not stop_event.is_set():
                if proc.poll() is not None:
                    break
                code, data = http_json_request(
                    cfg,
                    f"/api/agent/terminal/{session_id}/stdin",
                    method="GET",
                    timeout=20,
                )
                if code in (404, 410):
                    break
                if code != 200 or not data:
                    time.sleep(1.0)
                    continue

                mtype = data.get("type")
                if mtype == "input":
                    text = data.get("data", "")
                    if text:
                        cleaned = DA_RESP_PATTERN.sub("", text)
                        if cleaned:
                            os.write(master_fd, cleaned.encode("utf-8", errors="replace"))
                elif mtype == "resize":
                    cols = data.get("cols", 80)
                    rows = data.get("rows", 24)
                    _set_terminal_winsize(master_fd, rows, cols)
        except Exception:
            pass
        finally:
            stop_event.set()

    t_reader = threading.Thread(target=pty_reader, daemon=True)
    t_poller = threading.Thread(target=stdin_poller, daemon=True)
    t_reader.start()
    t_poller.start()

    stop_event.wait()

    # Bersihkan proses shell dan proses group (misal htop/vim)
    try:
        if proc.poll() is None:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.2)
            if proc.poll() is None:
                os.killpg(pgid, signal.SIGKILL)
    except Exception:
        pass

    try:
        os.close(master_fd)
    except Exception:
        pass

    # Beri tahu server bahwa sesi terminal selesai
    try:
        http_json_request(cfg, f"/api/agent/terminal/{session_id}/close", method="POST", timeout=5)
    except Exception:
        pass


def _terminal_worker_loop(cfg: dict) -> None:
    """Worker background untuk mem-poll permintaan pembukaan sesi terminal realtime."""
    while True:
        try:
            code, data = http_json_request(cfg, "/api/agent/terminal-requests", method="GET", timeout=25)
            if code == 200 and data and data.get("session_id"):
                sess_id = data["session_id"]
                threading.Thread(
                    target=_run_terminal_session,
                    args=(cfg, sess_id),
                    daemon=True,
                ).start()
            elif code in (401, 403):
                time.sleep(10.0)
            elif code == 0:
                time.sleep(2.0)
        except Exception:
            time.sleep(2.0)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
prev_services: dict[int, str] = {}
last_apt: dict | None = None
_tick = 0
_last_pkg_signature: tuple | None = None


def _get_pkg_state_signature() -> tuple:
    """Mengambil signature timestamp status dpkg dan apt lists untuk deteksi reaktif instan.
    Jika operator menjalankan apt install/upgrade/remove via SSH, mtime dpkg status akan berubah.
    """
    m_dpkg = 0.0
    m_lists = 0.0
    try:
        if os.path.exists("/var/lib/dpkg/status"):
            m_dpkg = os.path.getmtime("/var/lib/dpkg/status")
    except Exception:
        pass
    try:
        if os.path.exists("/var/lib/apt/lists"):
            m_lists = os.path.getmtime("/var/lib/apt/lists")
    except Exception:
        pass
    return (m_dpkg, m_lists)


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
    ensure_pantau_apt_updated()
    ensure_pantau_user_updated()
    print()

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        print(f"\n[INFO] Signal {sig} diterima, menghentikan agen...")
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Jalankan worker file manager, terminal & command executor di background thread
    threading.Thread(target=_file_worker_loop, args=(cfg,), daemon=True).start()
    threading.Thread(target=_terminal_worker_loop, args=(cfg,), daemon=True).start()
    threading.Thread(target=_command_worker_loop, args=(cfg,), daemon=True).start()

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
    global prev_services, last_apt, _tick, _last_pkg_signature
    _tick += 1

    # Eksekusi command yang mungkin pending sebelum pemindaian services
    try:
        poll_and_execute_commands(cfg)
    except Exception as e:
        print(f"[WARN] Polling command error: {e}")

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

    # Sesi pengguna, akun (SSH login/logout), dan unit layanan dilaporkan di setiap siklus
    accounts = collect_accounts()
    units = collect_units()

    # Deteksi reaktif perubahan paket di server klien (misal operator menjalankan apt di SSH)
    current_pkg_sig = _get_pkg_state_signature()
    pkg_changed = False
    if _last_pkg_signature is not None and _last_pkg_signature != current_pkg_sig:
        pkg_changed = True

    if last_apt is None or pkg_changed or (_tick % 6 == 2):
        last_apt = collect_apt()
        _last_pkg_signature = current_pkg_sig

    apt = last_apt

    if send_report(cfg, services, system, accounts, units, apt, pkg_changed):
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
    if any(arg in sys.argv for arg in ("--test-runtime", "--check-syntax-only")):
        # Inisialisasi modul dan validasi interpreter Python berhasil.
        # Periksa integritas konstanta dan fungsi penting sebelum keluar 0 tanpa efek samping.
        if not (isinstance(AGENT_VERSION, str) and AGENT_VERSION):
            print("ERROR: Konstanta AGENT_VERSION tidak terdefinisi atau kosong", file=sys.stderr)
            sys.exit(1)
        if not callable(main):
            print("ERROR: Fungsi main() tidak terdefinisi", file=sys.stderr)
            sys.exit(1)
        if not callable(_exec_update_agent):
            print("ERROR: Fungsi _exec_update_agent() tidak terdefinisi", file=sys.stderr)
            sys.exit(1)
        print(f"Pantau Agent v{AGENT_VERSION} runtime pre-flight check OK")
        sys.exit(0)
    if any(arg in sys.argv for arg in ("-v", "--version")):
        print(f"AgentPantau v{AGENT_VERSION}")
        sys.exit(0)
    if any(arg in sys.argv for arg in ("-h", "--help")):
        print(f"Pantau Monitoring Agent v{AGENT_VERSION}")
        print("Penggunaan: agent_pantau.py [OPSI]")
        print("Opsi:")
        print("  --test-runtime, --check-syntax-only  Uji integritas sintaks & inisialisasi modul tanpa menjalankan loop")
        print("  -v, --version                        Tampilkan versi agen")
        print("  -h, --help                           Tampilkan bantuan ini")
        sys.exit(0)
    main()