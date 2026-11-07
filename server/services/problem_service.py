"""Incident and Problem Lifecycle Management Service."""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Any

from sqlalchemy import desc, func, text, or_
from sqlalchemy.orm import Session

try:
    from config import settings
    from models import (
        AuditLog, Command, LogRequest, LoginAttempt, MaintenanceWindow,
        Metric, ProbeLog, ProbeTarget, Server, ServerExtras, ServerProblem,
        Service, SysSnapshotHour, SystemSetting, SystemSnapshot, User,
    )
    from core.database import SessionLocal
    from core.security import _prune_expired_sessions, _agent_ip_tracker, _agent_tracker_lock
    from core.utils import _fmt_short_dt, _is_agent_outdated
    from services.maintenance_service import _evaluate_maintenance_windows
    from services.server_service import _server_stale, _latest_metrics, _server_status
except ImportError:
    from server.config import settings
    from server.models import (
        AuditLog, Command, LogRequest, LoginAttempt, MaintenanceWindow,
        Metric, ProbeLog, ProbeTarget, Server, ServerExtras, ServerProblem,
        Service, SysSnapshotHour, SystemSetting, SystemSnapshot, User,
    )
    from server.core.database import SessionLocal
    from server.core.security import _prune_expired_sessions, _agent_ip_tracker, _agent_tracker_lock
    from server.core.utils import _fmt_short_dt, _is_agent_outdated
    from server.services.maintenance_service import _evaluate_maintenance_windows
    from server.services.server_service import _server_stale, _latest_metrics, _server_status

logger = logging.getLogger('pantau.problems')

# Ambang batas masalah default (Bawaan Pabrik)
DEFAULT_THRESHOLDS = {
    "cpu_warn": 85.0,
    "cpu_danger": 95.0,
    "ram_warn": 85.0,
    "ram_danger": 95.0,
    "disk_warn": 90.0,
    "disk_danger": 95.0,
    "swap_warn": 80.0,
    "swap_danger": 92.0,
    "ssh_fail_warn": 5,
    "ssh_fail_danger": 12,
}

# Alias kompatibilitas
SECURITY_DANGER_FAILED = 12
SECURITY_DANGER_INVALID = 4
SECURITY_WARNING_FAILED = 5
PROBLEM_RANK = {"ok": 0, "info": 1, "warning": 2, "average": 3, "danger": 4}
FRESH_SNAP_SECS = 90
RAM_DANGER_PCT = 95.0
RAM_WARNING_PCT = 85.0
SWAP_DANGER_PCT = 92.0
SWAP_WARNING_PCT = 80.0
CPU_DANGER_PCT = 95.0
CPU_WARNING_PCT = 85.0
DISK_DANGER_PCT = 95.0
DISK_WARNING_PCT = 90.0


def get_global_thresholds(db: Session | None = None) -> dict:
    """Ambil ambang batas global dari tabel system_settings (fallback ke DEFAULT_THRESHOLDS)."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
        if row and row.value:
            data = json.loads(row.value)
            res = dict(DEFAULT_THRESHOLDS)
            for k in res:
                if k in data and data[k] is not None and str(data[k]).strip() != "":
                    try:
                        res[k] = int(data[k]) if "fail" in k else float(data[k])
                    except (ValueError, TypeError):
                        pass
            return res
    except Exception as e:
        if not close_db:
            try:
                db.rollback()
            except Exception:
                pass
        logger.warning("[thresholds] Gagal membaca global thresholds: %s", e)
    finally:
        if close_db:
            db.close()
    return dict(DEFAULT_THRESHOLDS)


def get_server_thresholds(srv, db: Session | None = None) -> dict:
    """Ambil ambang batas efektif untuk server tertentu (per-server override -> global -> default)."""
    global_th = get_global_thresholds(db)
    if not srv or not getattr(srv, "custom_thresholds", None):
        return global_th
    try:
        raw = srv.custom_thresholds
        custom = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(custom, dict):
            res = dict(global_th)
            for k in res:
                if k in custom and custom[k] is not None and str(custom[k]).strip() != "":
                    try:
                        res[k] = int(custom[k]) if "fail" in k else float(custom[k])
                    except (ValueError, TypeError):
                        pass
            return res
    except Exception:
        pass
    return global_th

RAM_TIP = ("Cek proses pemakan memori: sudo ps aux --sort=-%mem | head | Hentikan/mulai ulang proses: "
           "sudo systemctl restart <unit> | Tambah alokasi RAM. Server bisa crash/OOM bila dibiarkan.")
CPU_TIP = ("Cek proses pemakan CPU: sudo ps aux --sort=-%cpu | head -20 | restart unit bermasalah; "
           "pertimbangkan menaikkan kuota CPU bila rutin melonjak.")
DISK_TIP = ("Bersihkan: sudo du -xh --max-depth=2 / | sort -rh | head -20 | hapus log lama: "
            "sudo journalctl --vacuum-size=200M. Disk penuh bisa mematikan database & aplikasi.")
SWAP_TIP = ("Penggunaan swap meningkat karena alokasi RAM tinggi — dapat menurunkan performa. Periksa konsumsi RAM dan proses sistem.")

# Jendela tenang: masalah danger ditutup otomatis bila tidak ada deteksi/kejadian
# baru selama rentang ini (mencegah banner macet karena sisa data auth.log).
SECURITY_QUIET_SECS = 600      # keamanan: 10 menit tanpa percobaan baru
RESOURCE_QUIET_SECS = 45       # resource: 45 detik dalam kondisi normal sebelum dinyatakan pulih
BG_PROBLEM_EVAL_SECS = 15      # interval evaluator background


def _quiet_secs_for(key: str) -> int:
    if key in ("security_danger", "failed_logins"):
        return SECURITY_QUIET_SECS
    if key.startswith("oom_kill:"):
        return 900   # 15 menit tanpa kejadian OOM baru
    if key.startswith("disk_io_error:"):
        return 1200  # 20 menit tanpa error I/O baru
    if key.startswith("segfault:"):
        return 600   # 10 menit tanpa segfault baru
    if key in ("kernel_panic", "hardware_error_mce"):
        return 1800  # 30 menit
    if key.startswith(("ram_", "swap_", "cpu_", "disk_")):
        return RESOURCE_QUIET_SECS
    if key.startswith("service_down:"):
        return 0   # Pemulihan layanan langsung seketika tanpa jeda penahanan
    if key == "agent_conflict":
        return 120  # Pertahankan peringatan konflik setidaknya 2 menit setelah stabil
    if key.startswith("ssh_active_session:"):
        return 0   # Sesi SSH remote ditutup seketika saat user logout
    return 0


def _build_problem_context(key: str, srv, **kwargs) -> str | None:
    """Susun payload JSON diagnostik terstruktur dwibahasa (ID & EN) untuk ServerProblem.context."""
    try:
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Konflik Agen (Split-Brain Multi-IP)
        if key == "agent_conflict":
            ips = kwargs.get("ips") or []
            return json.dumps({
                "diagnosa": "Konflik API Key Agen (Split-Brain Telemetri)",
                "diagnosa_en": "Agent API Key Conflict (Split-Brain Telemetry)",
                "penyebab": f"Server {srv.hostname} menerima telemetri aktif dari {len(ips)} alamat IP berbeda ({', '.join(ips)}) secara bersamaan dalam waktu kurang dari 2 menit. Mesin kemungkinan telah dikloning atau API key dipasang pada lebih dari satu host.",
                "penyebab_en": f"Server {srv.hostname} receives active telemetry from {len(ips)} distinct IP addresses ({', '.join(ips)}) simultaneously within 2 minutes. Likely caused by a cloned VM or duplicate agent installation with the same API key.",
                "dampak": "Metrik status layanan dan performa sistem berfluktuasi/flapping tidak menentu karena host melaporkan status yang berbeda.",
                "dampak_en": "Service status and system performance metrics flap erratically because different hosts report conflicting states.",
                "data_teknis": {
                    "conflicting_ips": ips,
                    "server_id": srv.id,
                    "server_hostname": srv.hostname,
                    "waktu_deteksi": now_str,
                },
                "rekomendasi": [
                    f"Periksa host di jaringan dengan alamat IP: {', '.join(ips)}.",
                    "Jika salah satu host merupakan hasil klon VM / template pengujian, matikan agen: sudo systemctl stop agent_pantau && sudo systemctl disable agent_pantau.",
                    "Jika kedua host harus dipantau terpisah, daftarkan server baru di Pantau Server untuk memperoleh API Key yang terpisah."
                ],
                "rekomendasi_en": [
                    f"Inspect hosts in your network with IP addresses: {', '.join(ips)}.",
                    "If one host is a cloned VM or staging template, stop the agent: sudo systemctl stop agent_pantau && sudo systemctl disable agent_pantau.",
                    "If both hosts must be monitored independently, add a new server in Pantau Server to generate a dedicated API Key."
                ],
                "perintah_diagnosa": [
                    f"ssh <user>@{ips[0]} 'sudo systemctl status agent_pantau'" if ips else "",
                    f"ssh <user>@{ips[-1]} 'sudo systemctl status agent_pantau'" if len(ips) > 1 else "",
                ]
            }, ensure_ascii=False)

        # 2. Layanan Mati (Service Down)
        if key.startswith("service_down:"):
            svc_name = kwargs.get("service_name") or key.split(":", 1)[1]
            port = kwargs.get("port")
            proc = kwargs.get("proc")
            health_msg = kwargs.get("health_msg")
            conflict_ips = kwargs.get("conflict_ips")
            is_op_stop = kwargs.get("is_op_stop", False)
            op_by = kwargs.get("op_by") or "OPERATOR"
            op_deps = kwargs.get("operator_stopped_dependencies") or []

            if is_op_stop:
                diagnosa = f"Layanan {svc_name} Dihentikan oleh Operator ({op_by})"
                diagnosa_en = f"Service {svc_name} Stopped by Operator ({op_by})"
                penyebab = f"Layanan {svc_name} sengaja dihentikan melalui panel kontrol oleh operator ({op_by}) untuk keperluan pemeliharaan atau operasional. Sistem mengenali tindakan ini sebagai pemeliharaan terencana dan menekan alarm darurat."
                penyebab_en = f"Service {svc_name} was intentionally stopped via the control panel by operator ({op_by}) for maintenance or operations. Emergency alarms are suppressed."
                dampak = f"Layanan {svc_name} sedang nonaktif sementara atas inisiatif operator. Layanan lain yang bergantung pada {svc_name} mungkin terpengaruh."
                dampak_en = f"Service {svc_name} is temporarily offline per operator action. Dependent services may be affected."
                rekomendasi = [
                    f"Nyalakan kembali layanan saat pekerjaan pemeliharaan selesai: sudo systemctl start {svc_name}",
                    f"Atau gunakan tombol Start pada antarmuka Pantau Server.",
                    f"Periksa apakah ada layanan lain di server ini yang terpengaruh akibat penghentian {svc_name}."
                ]
                rekomendasi_en = [
                    f"Start the service when maintenance is completed: sudo systemctl start {svc_name}",
                    f"Or click the Start button on the Pantau Server interface.",
                    f"Check if other services on this server are impacted by the stoppage of {svc_name}."
                ]
            else:
                diagnosa = f"Layanan {svc_name} Tidak Aktif (DOWN)"
                diagnosa_en = f"Service {svc_name} Inactive (DOWN)"
                penyebab = f"Layanan {svc_name} tidak mendengarkan (listening) pada port {port or 'terkait'} atau proses tidak ditemukan."
                penyebab_en = f"Service {svc_name} is not listening on port {port or 'associated'} or process was not found running."
                if conflict_ips and len(conflict_ips) > 1:
                    penyebab += f" Terdeteksi juga konflik multi-IP ({', '.join(conflict_ips)}) yang menyebabkan status layanan berfluktuasi."
                    penyebab_en += f" Multi-IP agent conflict ({', '.join(conflict_ips)}) detected, causing service status to flap."
                elif health_msg:
                    penyebab += f" Rincian pesan: {health_msg}"
                    penyebab_en += f" Detail: {health_msg}"
                dampak = f"Aplikasi atau pengguna tidak dapat mengakses layanan {svc_name}" + (f" pada port {port}." if port else ".")
                dampak_en = f"Clients or dependent systems cannot access service {svc_name}" + (f" on port {port}." if port else ".")
                rekomendasi = [
                    f"Periksa status layanan: sudo systemctl status {svc_name}",
                    f"Lihat riwayat log galat layanan: sudo journalctl -u {svc_name} -n 50 --no-pager",
                    f"Pastikan port listening: ss -tulpn | grep :{port}" if port else f"Periksa proses: pgrep -fa {proc or svc_name}",
                    f"Coba mulai ulang layanan: sudo systemctl restart {svc_name}"
                ]
                rekomendasi_en = [
                    f"Check service status: sudo systemctl status {svc_name}",
                    f"Inspect service error logs: sudo journalctl -u {svc_name} -n 50 --no-pager",
                    f"Verify listening port: ss -tulpn | grep :{port}" if port else f"Check process: pgrep -fa {proc or svc_name}",
                    f"Restart service: sudo systemctl restart {svc_name}"
                ]

            return json.dumps({
                "diagnosa": diagnosa,
                "diagnosa_en": diagnosa_en,
                "penyebab": penyebab,
                "penyebab_en": penyebab_en,
                "dampak": dampak,
                "dampak_en": dampak_en,
                "data_teknis": {
                    "service_name": svc_name,
                    "port": port,
                    "process_name": proc,
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "health_message": health_msg,
                    "conflicting_ips": conflict_ips,
                    "is_operator_stopped": is_op_stop,
                    "operator_stopped_by": op_by if is_op_stop else None,
                    "operator_stopped_dependencies": op_deps if op_deps else None,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": rekomendasi,
                "rekomendasi_en": rekomendasi_en,
                "perintah_diagnosa": [
                    f"sudo systemctl status {svc_name}",
                    f"sudo journalctl -u {svc_name} -n 50 --no-pager",
                    f"ss -tulpn | grep :{port}" if port else f"pgrep -fa {proc or svc_name}",
                    f"sudo systemctl restart {svc_name}"
                ]
            }, ensure_ascii=False)

        # 3. Layanan Belum Ada Data (Service Unknown / No Data)
        if key.startswith("svc_no_data:"):
            svc_name = kwargs.get("service_name") or key.split(":", 1)[1]
            port = kwargs.get("port")
            return json.dumps({
                "diagnosa": f"Layanan {svc_name} Belum Memiliki Data",
                "diagnosa_en": f"Service {svc_name} Has No Reported Data",
                "penyebab": f"Agen di server belum mendeteksi status atau metrik untuk layanan {svc_name}. Port atau proses mungkin belum aktif saat siklus pemindaian.",
                "penyebab_en": f"Agent on the server has not captured status or metrics for service {svc_name}. The port or process might not have been open during scan.",
                "dampak": "Metrik ketersediaan layanan belum dapat dihitung secara akurat.",
                "dampak_en": "Service availability metrics cannot be accurately computed.",
                "data_teknis": {
                    "service_name": svc_name,
                    "port": port,
                    "server_hostname": srv.hostname,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    f"Pastikan layanan berjalan: sudo systemctl status {svc_name}",
                    f"Pastikan port listening: ss -tlnp | grep :{port}" if port else f"Cek proses: pgrep -fa {svc_name}",
                    "Tunggu siklus pemindaian agen berikutnya (berjalan tiap beberapa detik)."
                ],
                "rekomendasi_en": [
                    f"Ensure service is running: sudo systemctl status {svc_name}",
                    f"Ensure port is listening: ss -tlnp | grep :{port}" if port else f"Check process: pgrep -fa {svc_name}",
                    "Wait for the next agent reporting cycle (runs every few seconds)."
                ],
                "perintah_diagnosa": [
                    f"sudo systemctl status {svc_name}",
                    f"ss -tulpn | grep :{port}" if port else f"pgrep -fa {svc_name}",
                ]
            }, ensure_ascii=False)

        # 4. RAM Kritis / Tinggi
        if key in ("ram_usage", "ram_critical", "ram_high"):
            pct = kwargs.get("pct", 0)
            used = kwargs.get("used", 0)
            total = kwargs.get("total", 0)
            is_crit = ("critical" in key) or (kwargs.get("severity") == "danger") or (pct >= kwargs.get("threshold", 95))
            return json.dumps({
                "diagnosa": f"Konsumsi Memori RAM Kritis ({pct:.1f}%)" if is_crit else f"Konsumsi Memori RAM Tinggi ({pct:.1f}%)",
                "diagnosa_en": f"Critical RAM Memory Consumption ({pct:.1f}%)" if is_crit else f"High RAM Memory Consumption ({pct:.1f}%)",
                "penyebab": f"Pemakaian memori RAM mencapai {pct:.1f}% ({_fmt_size(used)} dari {_fmt_size(total)}). Sistem berisiko memicu kernel Out-Of-Memory (OOM Killer).",
                "penyebab_en": f"RAM memory usage reached {pct:.1f}% ({_fmt_size(used)} of {_fmt_size(total)}). The host is at risk of invoking the Linux OOM Killer.",
                "dampak": "Sistem melambat drastis, thrashing swap meningkat, dan service penting dapat dimatikan mendadak oleh kernel OOM Killer.",
                "dampak_en": "Extreme system slowdown, severe swap thrashing, and critical services risk being terminated abruptly by the OOM Killer.",
                "data_teknis": {
                    "mem_used": used,
                    "mem_total": total,
                    "mem_percent": round(pct, 1),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Buka tab Proses untuk memeriksa proses pemakan memori teratas.",
                    "Jalankan di server: sudo ps aux --sort=-%mem | head -15",
                    "Mulai ulang aplikasi atau daemon yang memicu kebocoran memori (memory leak).",
                    "Pertimbangkan menambah alokasi RAM fisik atau swap bila beban kerja normal."
                ],
                "rekomendasi_en": [
                    "Open the Processes tab to inspect top memory-consuming processes.",
                    "Run on host: sudo ps aux --sort=-%mem | head -15",
                    "Restart daemon or application causing memory leaks.",
                    "Consider scaling up RAM capacity or swap space if standard workload demands it."
                ],
                "perintah_diagnosa": [
                    "free -h",
                    "ps aux --sort=-%mem | head -15",
                    "sudo journalctl -k -g 'oom' -n 20 --no-pager"
                ]
            }, ensure_ascii=False)

        # 5. Swap Kritis / Tinggi
        if key in ("swap_usage", "swap_critical", "swap_high"):
            pct = kwargs.get("pct", 0)
            used = kwargs.get("used", 0)
            total = kwargs.get("total", 0)
            is_crit = ("critical" in key) or (kwargs.get("severity") == "danger") or (pct >= kwargs.get("threshold", 92))
            return json.dumps({
                "diagnosa": f"Kapasitas Swap Hampir Penuh ({pct:.1f}%)" if is_crit else f"Pemakaian Swap Tinggi ({pct:.1f}%)",
                "diagnosa_en": f"Swap Space Nearly Full ({pct:.1f}%)" if is_crit else f"High Swap Space Usage ({pct:.1f}%)",
                "penyebab": f"Pemakaian swap mencapai {pct:.1f}% ({_fmt_size(used)} dari {_fmt_size(total)}). Memori RAM fisik menipis sehingga kernel memindahkan halaman memori ke disk.",
                "penyebab_en": f"Swap usage reached {pct:.1f}% ({_fmt_size(used)} of {_fmt_size(total)}). Physical RAM is exhausted, forcing kernel paging onto disk.",
                "dampak": "Kinerja I/O disk melonjak, latency sistem dan aplikasi meningkat tajam karena kecepatan swap jauh lebih lambat dari RAM.",
                "dampak_en": "Severe disk I/O bottleneck; system response latency spikes sharply due to disk-based memory paging.",
                "data_teknis": {
                    "swap_used": used,
                    "swap_total": total,
                    "swap_percent": round(pct, 1),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Periksa proses yang menggunakan banyak memori: sudo ps aux --sort=-%mem | head -15",
                    "Bebaskan memori dengan me-restart proses yang boros RAM.",
                    "Bersihkan cache jika aman: sudo sync && sudo sysctl -w vm.drop_caches=3",
                    "Tingkatkan alokasi RAM server."
                ],
                "rekomendasi_en": [
                    "Inspect high memory processes: sudo ps aux --sort=-%mem | head -15",
                    "Release memory by restarting excessive memory consumer services.",
                    "Drop safe filesystem caches if needed: sudo sync && sudo sysctl -w vm.drop_caches=3",
                    "Upgrade physical RAM allocation."
                ],
                "perintah_diagnosa": [
                    "free -h",
                    "swapon --show",
                    "vmstat 1 5"
                ]
            }, ensure_ascii=False)

        # 6. CPU Jenuh / Tinggi
        if key in ("cpu_usage", "cpu_saturated", "cpu_high"):
            cpu_avg = kwargs.get("cpu_avg", 0)
            cpu_max = kwargs.get("cpu_max", 0)
            is_crit = ("saturated" in key) or (kwargs.get("severity") == "danger") or (cpu_avg >= kwargs.get("threshold", 95))
            return json.dumps({
                "diagnosa": "Saturasi Beban Prosesor (CPU Saturated)" if is_crit else "Beban Prosesor Tinggi (CPU High)",
                "diagnosa_en": "Processor Saturation (CPU Saturated)" if is_crit else "High Processor Load (CPU High)",
                "penyebab": f"Beban CPU rata-rata mencapai {cpu_avg:.1f}% (puncak {cpu_max:.1f}%) dalam rentang observasi terakhir.",
                "penyebab_en": f"Average CPU utilization reached {cpu_avg:.1f}% (peak {cpu_max:.1f}%) during recent observation window.",
                "dampak": "Antrean thread sistem melambat, response time layanan meningkat, potensi request timeout.",
                "dampak_en": "System thread queues stall, response latency deteriorates, elevated risk of connection timeouts.",
                "data_teknis": {
                    "cpu_avg": round(cpu_avg, 1),
                    "cpu_max": round(cpu_max, 1),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Buka tab Proses untuk melihat proses dengan pemakaian CPU tertinggi.",
                    "Identifikasi proses intensif: top -b -n 1 | head -20",
                    "Periksa apakah ada loop eksekusi tak berujung (infinite loop) atau thread worker yang menggantung."
                ],
                "rekomendasi_en": [
                    "Open Processes tab to identify top CPU consumers.",
                    "Inspect active processes: top -b -n 1 | head -20",
                    "Investigate stuck worker threads or infinite execution loops."
                ],
                "perintah_diagnosa": [
                    "top -b -n 1 | head -20",
                    "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -15"
                ]
            }, ensure_ascii=False)

        # 7. Partisi Disk Kritis / Tinggi
        if key.startswith("disk_usage:") or key.startswith("disk_critical:") or key.startswith("disk_high:"):
            mount = kwargs.get("mount") or key.split(":", 1)[1]
            used = kwargs.get("used", 0)
            total = kwargs.get("total", 0)
            pct = kwargs.get("pct", 0)
            is_crit = ("critical" in key) or (kwargs.get("severity") == "danger") or (pct >= kwargs.get("threshold", 95))
            return json.dumps({
                "diagnosa": f"Penyimpanan Partisi {mount} Hampir Penuh ({pct:.0f}%)" if is_crit else f"Penyimpanan Partisi {mount} Terisi Tinggi ({pct:.0f}%)",
                "diagnosa_en": f"Disk Partition {mount} Nearly Full ({pct:.0f}%)" if is_crit else f"Disk Partition {mount} High Usage ({pct:.0f}%)",
                "penyebab": f"Penggunaan partisi {mount} mencapai {pct:.0f}% ({_fmt_size(used)} terpakai dari kapasitas {_fmt_size(total)}).",
                "penyebab_en": f"Partition {mount} utilization reached {pct:.0f}% ({_fmt_size(used)} used out of {_fmt_size(total)}).",
                "dampak": "Aplikasi tidak dapat membuat file baru, database dapat read-only atau crash, sistem logging terhenti.",
                "dampak_en": "Applications cannot write new files, databases risk read-only state or crash, system logging halts.",
                "data_teknis": {
                    "mount_point": mount,
                    "disk_used": used,
                    "disk_total": total,
                    "disk_percent": round(pct, 1),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    f"Periksa penggunaan direktori terbesar: sudo du -xh --max-depth=2 {mount} | sort -rh | head -20",
                    "Bersihkan berkas log systemd lama: sudo journalctl --vacuum-size=200M",
                    "Bersihkan cache paket: sudo apt clean",
                    "Hapus berkas temporary lama di /tmp dan /var/tmp."
                ],
                "rekomendasi_en": [
                    f"Find largest directories: sudo du -xh --max-depth=2 {mount} | sort -rh | head -20",
                    "Vacuum journal logs: sudo journalctl --vacuum-size=200M",
                    "Clean APT package cache: sudo apt clean",
                    "Purge stale temporary files in /tmp and /var/tmp."
                ],
                "perintah_diagnosa": [
                    f"df -h {mount}",
                    f"sudo du -xh --max-depth=2 {mount} | sort -rh | head -15",
                    "sudo journalctl --disk-usage"
                ]
            }, ensure_ascii=False)

        # 8. Serangan SSH / Login Gagal
        if key in ("security_danger", "failed_logins"):
            failed = kwargs.get("failed", 0)
            invalid = kwargs.get("invalid", 0)
            source_ips = kwargs.get("source_ips") or {}
            top_ips = sorted(source_ips.items(), key=lambda x: x[1] if isinstance(x[1], int) else 0, reverse=True)[:10]
            ip_list = [f"{ip} ({cnt}x)" for ip, cnt in top_ips]
            is_crit = (key == "security_danger") or (kwargs.get("severity") == "danger") or (failed >= kwargs.get("threshold", 12)) or (invalid >= 4)
            return json.dumps({
                "diagnosa": "Indikasi Aktivitas SSH Brute-Force" if is_crit else "Percobaan Login SSH Gagal Berulang",
                "diagnosa_en": "Suspected SSH Brute-Force Activity" if is_crit else "Repetitive Failed SSH Login Attempts",
                "penyebab": f"Terdeteksi {failed} percobaan login SSH gagal dan {invalid} percobaan user tidak valid dari {len(source_ips)} alamat IP sumber.",
                "penyebab_en": f"Detected {failed} failed SSH logins and {invalid} invalid username attempts originating from {len(source_ips)} source IPs.",
                "dampak": "Potensi pembobolan kredensial akun server bila password lemah, serta beban koneksi SSH yang tinggi.",
                "dampak_en": "Security risk of unauthorized account breach if weak passwords exist, alongside network socket overhead on sshd.",
                "data_teknis": {
                    "total_failed": failed,
                    "invalid_users": invalid,
                    "total_source_ips": len(source_ips),
                    "top_attacker_ips": ip_list,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Gunakan tombol 'Blokir IP' pada kolom tindakan untuk memblokir alamat IP sumber via iptables.",
                    "Pasang dan aktifkan fail2ban: sudo apt install fail2ban && sudo systemctl enable --now fail2ban",
                    "Perketat konfigurasi SSH (/etc/ssh/sshd_config): PasswordAuthentication no, gunakan SSH Key.",
                    "Ganti port default SSH dari port 22 ke port khusus non-standar."
                ],
                "rekomendasi_en": [
                    "Use the 'Block IP' button in the action column to drop source IPs via iptables.",
                    "Install and enable fail2ban: sudo apt install fail2ban && sudo systemctl enable --now fail2ban",
                    "Harden SSH daemon (/etc/ssh/sshd_config): set PasswordAuthentication no, enforce SSH Keys.",
                    "Change default SSH listening port from 22 to a custom high port."
                ],
                "perintah_diagnosa": [
                    "sudo journalctl -u ssh -n 50 --no-pager",
                    "sudo iptables -L INPUT -v -n --line-numbers",
                    "sudo fail2ban-client status sshd"
                ]
            }, ensure_ascii=False)

        # 9. Agen Stale (Offline / Agen Tidak Melapor)
        if key == "agent_stale":
            return json.dumps({
                "diagnosa": "Agen Tidak Melapor",
                "diagnosa_en": "Agent Not Reporting",
                "penyebab": f"Agen Pantau pada server {srv.hostname} tidak mengirimkan telemetri ke server pusat. Kemungkinan penyebab mencakup server offline, shutdown, koneksi jaringan terputus, service agent_pantau terhenti, atau pemblokiran firewall.",
                "penyebab_en": f"Monitoring agent on server {srv.hostname} stopped transmitting telemetry to central server. Causes include offline host, shutdown, network disconnection, halted agent service, or firewall blocking.",
                "dampak": "Metrik kinerja hardware (CPU, RAM, Disk), status layanan, dan telemetri keamanan server tidak dapat diperbarui secara live di dashboard.",
                "dampak_en": "Hardware performance metrics (CPU, RAM, Disk), service states, and security telemetry are no longer live on the dashboard.",
                "data_teknis": {
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "terakhir_melapor": srv.last_seen.strftime("%Y-%m-%d %H:%M:%S UTC") if srv.last_seen else "Belum pernah",
                    "durasi_tidak_melapor_detik": kwargs.get("sec_silent"),
                    "level_eskalasi": (kwargs.get("escalation_level") or "").upper(),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Verifikasi status daya fisik atau virtual mesin: pastikan server dalam kondisi aktif (Power ON).",
                    "Uji konektivitas jaringan: lakukan ping atau uji jangkauan SSH ke alamat host server.",
                    "Lakukan inspeksi keamanan & firewall: pastikan port telemetri atau akses keluar server tidak diblokir.",
                    "Bila server aktif dan dapat diakses, periksa status service agen: sudo systemctl status agent_pantau",
                    "Periksa log sistem dan agen untuk diagnosa mendalam: sudo journalctl -u agent_pantau -n 30 --no-pager"
                ],
                "rekomendasi_en": [
                    "Check host machine power status: ensure server is powered ON.",
                    "Check network connectivity: ping host or test console / SSH reachability.",
                    "Inspect security & firewall rules: verify agent outbound connection or SSH port is not blocked.",
                    "If machine is running, inspect agent daemon: sudo systemctl status agent_pantau",
                    "Inspect agent logs for detailed diagnosis: sudo journalctl -u agent_pantau -n 30 --no-pager"
                ],
                "perintah_diagnosa": [
                    "ping -c 3 " + (srv.ip_address or "127.0.0.1"),
                    "ssh -o ConnectTimeout=5 " + (srv.ip_address or srv.hostname),
                    "sudo systemctl status agent_pantau",
                    "sudo journalctl -u agent_pantau -n 30 --no-pager"
                ]
            }, ensure_ascii=False)

        # 10. Paket OS Butuh Pembaruan (APT Updates)
        if key == "apt_updates":
            upg_count = kwargs.get("upgradable", 0)
            return json.dumps({
                "diagnosa": f"{upg_count} Paket Pembaruan OS Tersedia",
                "diagnosa_en": f"{upg_count} OS Package Updates Available",
                "penyebab": f"Repositori sistem melaporkan terdapat {upg_count} paket software/kernel yang siap di-upgrade, termasuk potensi patch keamanan.",
                "penyebab_en": f"System package repositories report {upg_count} upgradable software/kernel packages, potentially including critical security patches.",
                "dampak": "Sistem berisiko terhadap kerentanan keamanan yang telah ditambal pada versi terbaru.",
                "dampak_en": "Host remains vulnerable to publicly known CVEs and software defects resolved in upstream updates.",
                "data_teknis": {
                    "paket_upgradable": upg_count,
                    "server_hostname": srv.hostname,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Gunakan tombol 'Update OS' pada antarmuka Pantau Server untuk menjalankan pembaruan otomatis.",
                    "Atau jalankan secara manual di server: sudo apt update && sudo apt upgrade -y",
                    "Periksa apakah diperlukan reboot setelah kernel diperbarui."
                ],
                "rekomendasi_en": [
                    "Use the 'Update OS' button in the dashboard to execute automated package updates.",
                    "Alternatively run manually on host: sudo apt update && sudo apt upgrade -y",
                    "Check if host reboot is required after kernel packages update."
                ],
                "perintah_diagnosa": [
                    "apt list --upgradable",
                    "sudo apt update && sudo apt upgrade -s"
                ]
            }, ensure_ascii=False)

        # 11. Agen Perlu Pembaruan (Agent Outdated)
        if key == "agent_outdated":
            agent_ver = kwargs.get("agent_version") or getattr(srv, "_agent_version", None) or "lama"
            app_ver = kwargs.get("app_version") or settings.APP_VERSION
            return json.dumps({
                "diagnosa": f"Versi Agen Pantau Usang (v{agent_ver})",
                "diagnosa_en": f"Outdated Pantau Agent Version (v{agent_ver})",
                "penyebab": f"Agen pemantau di host {srv.hostname} berjalan pada versi v{agent_ver}, sedangkan dashboard pusat berada pada versi v{app_ver}. Fitur telemetri terbaru, stabilitas proses snapshot, dan perbaikan agen belum aktif pada host ini.",
                "penyebab_en": f"Monitoring agent on host {srv.hostname} is running version v{agent_ver}, while central dashboard is running v{app_ver}. Latest telemetry capabilities, snapshot stability, and agent patches are not active on this host.",
                "dampak": "Metrik kinerja snapshot mungkin tidak lengkap dan berisiko mengalami anomali kompatibilitas.",
                "dampak_en": "System metrics telemetry may be incomplete and risks protocol discrepancies with the central server.",
                "data_teknis": {
                    "versi_agen_klien": f"v{agent_ver}",
                    "versi_dashboard_pusat": f"v{app_ver}",
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Jalankan perintah pembaruan agen otomatis di terminal server klien.",
                    "Pastikan daemon agent_pantau kembali aktif setelah pembaruan: sudo systemctl status agent_pantau",
                    "Muat ulang dashboard setelah agen berhasil mengirimkan telemetri versi baru."
                ],
                "rekomendasi_en": [
                    "Execute the automated agent update command on the client server terminal.",
                    "Verify agent_pantau service is active following update: sudo systemctl status agent_pantau",
                    "Reload dashboard once the agent transmits updated telemetry."
                ],
                "perintah_diagnosa": [
                    "sudo curl -fsSL -o /opt/pantau/agent/agent_pantau.py https://raw.githubusercontent.com/azhuka/pantau-server/master/package/opt/pantau/agent/agent_pantau.py && sudo systemctl restart agent_pantau.service",
                    "sudo systemctl status agent_pantau",
                    "python3 /opt/pantau/agent/agent_pantau.py --version"
                ]
            }, ensure_ascii=False)

        # 12. Sesi Remote SSH Aktif (INFO)
        if key.startswith("ssh_active_session"):
            user = kwargs.get("user") or "unknown"
            from_ip = kwargs.get("from_ip") or kwargs.get("source") or "unknown"
            tty = kwargs.get("tty") or "-"
            login_time = kwargs.get("login_time") or "-"
            penyebab = f"Pengguna '{user}' sedang aktif terhubung ke server {srv.hostname} via remote SSH dari IP {from_ip} pada terminal {tty}"
            penyebab_en = f"User '{user}' is actively connected to server {srv.hostname} via remote SSH from IP {from_ip} on terminal {tty}"
            if login_time and login_time != "-":
                penyebab += f" sejak {login_time}."
                penyebab_en += f" since {login_time}."
            else:
                penyebab += "."
                penyebab_en += "."

            clean_tty_sub = tty.replace("pts/", "").replace("/dev/", "") if tty and tty != "-" else ""
            return json.dumps({
                "diagnosa": f"Sesi Remote SSH Aktif ({user}@{from_ip})",
                "diagnosa_en": f"Active Remote SSH Session ({user}@{from_ip})",
                "penyebab": penyebab,
                "penyebab_en": penyebab_en,
                "dampak": "Informasi keamanan dan telemetri aktivitas remote server. Tidak ada gangguan layanan jika akses ini sah.",
                "dampak_en": "Security telemetry and remote access tracking. No service disruption if access is authorized.",
                "data_teknis": {
                    "user": user,
                    "client_ip": from_ip,
                    "tty": tty,
                    "login_time": login_time,
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "waktu_deteksi": now_str,
                },
                "rekomendasi": [
                    f"Pastikan login remote oleh pengguna '{user}' dari {from_ip} merupakan aktivitas administratif sah.",
                    "Periksa aktivitas proses sesi melalui perintah: who atau w",
                    f"Bila sesi mencurigakan atau tidak diizinkan, putuskan segera: sudo pkill -u {user}" + (f" atau sudo pkill -t {clean_tty_sub}" if clean_tty_sub else ""),
                    "Periksa riwayat log login SSH di tab Logs atau via: sudo journalctl -u ssh -n 50 --no-pager"
                ],
                "rekomendasi_en": [
                    f"Ensure remote login by user '{user}' from {from_ip} is an authorized administrative activity.",
                    "Inspect active processes of this session using: who or w",
                    f"If the session is unauthorized, terminate it immediately: sudo pkill -u {user}" + (f" or sudo pkill -t {clean_tty_sub}" if clean_tty_sub else ""),
                    "Inspect SSH authentication log in the Logs tab or via: sudo journalctl -u ssh -n 50 --no-pager"
                ],
                "perintah_diagnosa": [
                    "who",
                    f"w {user}",
                    "sudo journalctl -u ssh -n 30 --no-pager",
                    f"sudo pkill -t {clean_tty_sub}" if clean_tty_sub else f"sudo pkill -u {user}"
                ]
            }, ensure_ascii=False)

        # 11. S.M.A.R.T. / NVMe Kerusakan Kritis (Drive Failing)
        if key.startswith("disk_smart_failing"):
            disk = kwargs.get("disk") or (key.split(":", 1)[1] if ":" in key else "drive")
            smart = kwargs.get("smart") or {}
            detail = smart.get("detail") or "Kerusakan integritas hardware"
            return json.dumps({
                "diagnosa": f"Kerusakan Kritis S.M.A.R.T. Drive {disk}",
                "diagnosa_en": f"Critical S.M.A.R.T. Failure on Drive {disk}",
                "penyebab": f"Drive {disk} melaporkan status kegagalan (FAILING/CRITICAL): {detail}. Kerusakan fisik atau sektor bad sektoral melampaui toleransi batas pabrikan.",
                "penyebab_en": f"Drive {disk} reports failing/critical health status: {detail}. Physical damage or bad sector count exceeds manufacturer threshold.",
                "dampak": "Risiko kehilangan data permanen (data loss), silent corruption, dan kernel I/O crash.",
                "dampak_en": "High risk of catastrophic data loss, silent corruption, and kernel I/O panic.",
                "data_teknis": {
                    "disk": disk,
                    "smart_health": smart.get("health"),
                    "smart_detail": detail,
                    "serial": smart.get("serial"),
                    "temp_c": smart.get("temp_c"),
                    "reallocated_sectors": smart.get("reallocated_sectors"),
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    f"Segera lakukan pencadangan data (backup) dari drive {disk} ke penyimpanan eksternal/remote.",
                    f"Jalankan uji diagnostik: sudo smartctl -H -A /dev/{disk}",
                    f"Cek riwayat galat drive: sudo smartctl -l error /dev/{disk}",
                    f"Segera ganti fisik drive {disk} dengan unit baru."
                ],
                "rekomendasi_en": [
                    f"Immediately back up all data from drive {disk} to an external or remote target.",
                    f"Run diagnostic test: sudo smartctl -H -A /dev/{disk}",
                    f"Inspect drive error log: sudo smartctl -l error /dev/{disk}",
                    f"Replace physical drive {disk} immediately."
                ],
                "perintah_diagnosa": [
                    f"sudo smartctl -H -A /dev/{disk}",
                    f"sudo smartctl -l error /dev/{disk}",
                    f"sudo dmesg -T | grep -E 'I/O error|ata[0-9]|nvme[0-9]|sd[a-z]'"
                ]
            }, ensure_ascii=False)

        # 12. S.M.A.R.T. / NVMe Suhu Terlalu Panas (Drive Overheating)
        if key.startswith("disk_smart_temp"):
            disk = kwargs.get("disk") or (key.split(":", 1)[1] if ":" in key else "drive")
            temp_c = kwargs.get("temp_c")
            return json.dumps({
                "diagnosa": f"Suhu Drive {disk} Terlalu Tinggi ({temp_c}°C)",
                "diagnosa_en": f"Overheating Temperature on Drive {disk} ({temp_c}°C)",
                "penyebab": f"Sensor suhu drive {disk} mendeteksi panas {temp_c}°C, melampaui batas aman operasional (< 60°C).",
                "penyebab_en": f"Drive {disk} temperature sensor measured {temp_c}°C, exceeding standard operational limits (< 60°C).",
                "dampak": "Thermal throttling memperlambat kecepatan baca/tulis dan mempercepat keausan memori flash atau motor cakram magnetik.",
                "dampak_en": "Thermal throttling degrades read/write throughput and accelerates permanent component wear.",
                "data_teknis": {
                    "disk": disk,
                    "temp_c": temp_c,
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Periksa sirkulasi udara (airflow) dan kebersihan pendingin chassis server.",
                    "Pastikan kipas pendingin casing dan server berjalan pada RPM normal.",
                    f"Periksa sensor temperatur sistem: sensors atau sudo smartctl -A /dev/{disk}"
                ],
                "rekomendasi_en": [
                    "Check chassis airflow, fan dust filters, and heat sinks.",
                    "Verify server cooling fans are spinning at nominal RPM.",
                    f"Check temperature sensors: sensors or sudo smartctl -A /dev/{disk}"
                ],
                "perintah_diagnosa": [
                    f"sudo smartctl -A /dev/{disk} | grep -i temp",
                    "sensors",
                    "sudo ipmitool sdr type Temperature 2>/dev/null || true"
                ]
            }, ensure_ascii=False)

        # 13. S.M.A.R.T. / NVMe Sisa Umur Flash Menipis (Drive Wearout)
        if key.startswith("disk_smart_wear"):
            disk = kwargs.get("disk") or (key.split(":", 1)[1] if ":" in key else "drive")
            rem = kwargs.get("remaining", 0)
            return json.dumps({
                "diagnosa": f"Sisa Umur Drive SSD/NVMe {disk} Menipis ({rem}%)",
                "diagnosa_en": f"Low Wearout Endurance Life on Drive {disk} ({rem}% Remaining)",
                "penyebab": f"Ketahanan sel flash NAND pada drive {disk} hampir habis (sisa umur {rem}%). Beban penulisan TBW telah mendekati kapasitas desain pabrikan.",
                "penyebab_en": f"NAND flash endurance on drive {disk} is nearly exhausted ({rem}% remaining). Write endurance has approached manufacturer TBW rating.",
                "dampak": "Saat sisa umur mencapai 0%, SSD akan mengunci ke mode read-only atau mengalami kegagalan penulisan permanen.",
                "dampak_en": "Once endurance hits 0%, SSD may lock into read-only mode or suffer write block exhaustion.",
                "data_teknis": {
                    "disk": disk,
                    "remaining_pct": rem,
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    f"Jadwalkan penggantian drive {disk} dengan unit SSD/NVMe baru.",
                    "Pastikan backup berkala berjalan dengan baik.",
                    f"Cek total byte penulisan: sudo nvme smart-log /dev/{disk} 2>/dev/null || sudo smartctl -A /dev/{disk}"
                ],
                "rekomendasi_en": [
                    f"Schedule proactive replacement of drive {disk} with a new SSD/NVMe unit.",
                    "Verify regular backup routines are operational.",
                    f"Inspect total bytes written: sudo nvme smart-log /dev/{disk} 2>/dev/null || sudo smartctl -A /dev/{disk}"
                ],
                "perintah_diagnosa": [
                    f"sudo nvme smart-log /dev/{disk} -o json 2>/dev/null || sudo smartctl -A /dev/{disk}",
                ]
            }, ensure_ascii=False)

        # 14. S.M.A.R.T. Sektor Rusak (Reallocated Sectors)
        if key.startswith("disk_smart_sectors"):
            disk = kwargs.get("disk") or (key.split(":", 1)[1] if ":" in key else "drive")
            realloc = kwargs.get("reallocated", 0)
            return json.dumps({
                "diagnosa": f"Drive {disk} Mendeteksi Sektor Rusak ({realloc} Sektor)",
                "diagnosa_en": f"Drive {disk} Detected Bad Sectors ({realloc} Reallocated)",
                "penyebab": f"Drive {disk} telah memetakan ulang {realloc} sektor fisik yang rusak ke blok cadangan (Reallocated Sector Count).",
                "penyebab_en": f"Drive {disk} reallocated {realloc} corrupted physical sectors to spare blocks.",
                "dampak": "Bila jumlah sektor rusak terus bertambah, drive berada di ambang kegagalan mekanik/permukaan piringan atau blok memori.",
                "dampak_en": "If reallocated sectors continue to increment, the drive is nearing complete mechanical or media failure.",
                "data_teknis": {
                    "disk": disk,
                    "reallocated_sectors": realloc,
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    f"Amati apakah nilai sektor rusak bertambah setiap hari.",
                    f"Siapkan unit pengganti drive {disk} sebelum terjadi kegagalan total.",
                    f"Periksa status SMART: sudo smartctl -A /dev/{disk}"
                ],
                "rekomendasi_en": [
                    "Observe whether bad sector count continues to grow day-by-day.",
                    f"Prepare a replacement drive {disk} before catastrophic failure.",
                    f"Check SMART status: sudo smartctl -A /dev/{disk}"
                ],
                "perintah_diagnosa": [
                    f"sudo smartctl -A /dev/{disk} | grep -E 'Reallocated|Pending|Uncorrectable'",
                ]
            }, ensure_ascii=False)

        # 15. Konflik Konfigurasi Platform (Platform Mismatch Conflict)
        if key == "platform_conflict":
            ovr_label = kwargs.get("override_label") or "Fisik / Baremetal"
            det_label = kwargs.get("detected_label") or "Mesin Virtual / Kontainer"
            virt_name = kwargs.get("virt") or "Virtual"
            return json.dumps({
                "diagnosa": "Konfigurasi Platform Server Tidak Sesuai",
                "diagnosa_en": "Server Platform Configuration Mismatch",
                "penyebab": f"Server {srv.hostname} disetel manual sebagai '{ovr_label}' pada konfigurasi dashboard, namun agen mendeteksi sistem operasi berjalan di atas '{det_label}' ({virt_name}).",
                "penyebab_en": f"Server {srv.hostname} is manually configured as '{ovr_label}', but the agent detects the operating system running on '{det_label}' ({virt_name}).",
                "dampak": "Kalkulasi alokasi kapasitas penyimpanan, sensor kesehatan hardware fisik (S.M.A.R.T.), dan proteksi Proxmox HA dapat tidak bekerja secara optimal atau menampilkan data yang membingungkan operator.",
                "dampak_en": "Storage capacity calculations, physical hardware health sensors (S.M.A.R.T.), and Proxmox HA protections may not operate optimally or may present confusing data to operators.",
                "data_teknis": {
                    "server_id": srv.id,
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "platform_override": kwargs.get("override"),
                    "platform_override_label": ovr_label,
                    "detected_type": kwargs.get("detected_type"),
                    "detected_label": det_label,
                    "hypervisor_virt": virt_name,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Buka formulir Edit Server melalui menu Rincian Server -> Edit atau klik tombol sinkronkan platform.",
                    "Ubah opsi 'Tipe Platform Lingkungan' menjadi 'Auto Deteksi (Laporan Agen)' agar sistem menyelaraskan arsitektur lingkungan secara otomatis.",
                    "Simpan perubahan konfigurasi server."
                ],
                "rekomendasi_en": [
                    "Open the Edit Server form via Server Details -> Edit or click the sync platform button.",
                    "Change 'Platform Environment Type' to 'Auto Deteksi (Laporan Agen)' so the system aligns metrics accurately.",
                    "Save server configuration changes."
                ],
                "perintah_diagnosa": [
                    "systemd-detect-virt",
                    "cat /sys/class/dmi/id/product_name",
                    "cat /sys/class/dmi/id/sys_vendor"
                ]
            }, ensure_ascii=False)


    except Exception as e:
        logger.warning("[CONTEXT] Gagal menyusun konteks masalah %s: %s", key, e)
    return None



def _parse_extras_security(extras) -> dict:
    if not extras or not extras.security:
        return {}
    try:
        d = json.loads(extras.security)
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def _rollup_sys_hours(db, server_id):
    """Materialisasikan rollup per jam dari sys_snapshots (idempotent).

    Dipanggil tiap laporan agent; hanya memperbaiki "jam yang sudah lewat"
    (di bawah jam berjalan) yang belum ada di sys_snapshots_hourly, lalu
    memangkas metric service > 7 hari (prune mahal -> dibatasi tiap 24 jam).
    """
    global _last_metrics_prune
    now = datetime.utcnow()
    this_hour = now.replace(minute=0, second=0, microsecond=0)

    with _prune_lock:
        if now - _last_metrics_prune > timedelta(hours=24):
            mcut = now - timedelta(days=7)
            db.query(Metric).filter(Metric.timestamp < mcut).delete(synchronize_session=False)
            _last_metrics_prune = now

    latest = (
        db.query(func.max(SysSnapshotHour.bucket))
        .filter(SysSnapshotHour.server_id == server_id)
        .scalar()
    )
    bucket = latest + timedelta(hours=1) if latest else this_hour - timedelta(hours=24)
    while bucket < this_hour:
        nxt = bucket + timedelta(hours=1)
        agg = db.query(
            func.count(SystemSnapshot.id),
            func.avg(SystemSnapshot.cpu),
            func.max(SystemSnapshot.cpu),
            func.avg(SystemSnapshot.load1),
            func.avg(SystemSnapshot.load5),
            func.avg(SystemSnapshot.load15),
            func.max(SystemSnapshot.mem_total),
            func.avg(SystemSnapshot.mem_used),
            func.avg(SystemSnapshot.mem_avail),
            func.max(SystemSnapshot.swap_total),
            func.avg(SystemSnapshot.swap_used),
            func.avg(SystemSnapshot.procs),
        ).filter(
            SystemSnapshot.server_id == server_id,
            SystemSnapshot.timestamp >= bucket,
            SystemSnapshot.timestamp < nxt,
        ).one()
        if agg[0]:
            last_snap = (
                db.query(SystemSnapshot.disks)
                .filter(
                    SystemSnapshot.server_id == server_id,
                    SystemSnapshot.timestamp >= bucket,
                    SystemSnapshot.timestamp < nxt,
                )
                .order_by(desc(SystemSnapshot.timestamp))
                .first()
            )
            disk_max_pct = None
            if last_snap and last_snap.disks:
                try:
                    disks = json.loads(last_snap.disks)
                    disk_max_pct = max(
                        (d.get("pct") or 0) for d in disks if isinstance(d, dict)
                    ) or None
                except (TypeError, ValueError):
                    disk_max_pct = None
            db.add(SysSnapshotHour(
                server_id=server_id, bucket=bucket, samples=agg[0],
                cpu_avg=agg[1] or 0.0, cpu_max=agg[2] or 0.0,
                load1_avg=agg[3], load5_avg=agg[4], load15_avg=agg[5],
                mem_total=agg[6] or 0, mem_used_avg=agg[7] or 0,
                mem_avail_avg=agg[8] or 0, swap_total=agg[9] or 0,
                swap_used_avg=agg[10] or 0,
                procs_avg=int(agg[11]) if agg[11] is not None else None,
                disk_max_pct=disk_max_pct,
            ))
        bucket = nxt

    prune_h = now - timedelta(days=90)
    db.query(SysSnapshotHour).filter(
        SysSnapshotHour.server_id == server_id,
        SysSnapshotHour.bucket < prune_h,
    ).delete(synchronize_session=False)


SECURITY_TIPS = {
    "danger": ("Indikasi brute-force SSH — blokir alamat IP sumber "
               "(sudo iptables -A INPUT -s <ip> -j DROP), pasang fail2ban "
               "(sudo apt install fail2ban), ganti password akun, perketat sshd "
               "(PasswordAuthentication no + PubkeyAuthentication yes)."),
    "warning": "Login SSH gagal dalam jumlah mencurigakan — cek IP sumber & akun; blokir bila repetitif; pasang fail2ban.",
    "info": "Ada login SSH gagal — bisa typo password; tetap pantau aktivitas di halaman Aktivitas User.",
}
APT_TIP = ("Buka Rincian server lalu pilih Update OS atau Upgrade. "
           "Di server bisa juga manual: sudo apt update && sudo apt upgrade")
SVC_DOWN_TIP = ("Cek status: sudo systemctl status {name} | Mulai ulang: "
                "sudo systemctl restart {name} | Log: journalctl -u {name} -n 50")
SVC_NODATA_TIP = "Pastikan service benar-benar ada & port terbuka (ss -tlnp); agen memindai ulang tiap siklus."
AGENT_STALE_TIP = ("Agen tidak melapor — mulai ulang: sudo systemctl restart agent_pantau | "
                   "Log: journalctl -u agent_pantau -n 30")
AGENT_OUTDATED_TIP = (
    "Versi agen di server ini lebih lama dari dashboard. Update via terminal server klien: "
    "sudo curl -fsSL -o /opt/pantau/agent/agent_pantau.py "
    "https://raw.githubusercontent.com/azhuka/pantau-server/master/package/opt/pantau/agent/agent_pantau.py "
    "&& sudo systemctl restart agent_pantau.service"
)


def _fmt_size(n: int | float | None) -> str:
    n = n or 0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _resource_problem_instances(db, srv) -> list:
    """Masalah hardware/performa: RAM/swap penuh, CPU jenuh, disk penuh.

    Data diambil dari snapshot real-time terbaru agen; diabaikan bila basi
    (agen sudah dianggap offline oleh indikator agent_stale).
    """
    inst: list = []
    now = datetime.utcnow()
    snaps = (
        db.query(SystemSnapshot)
        .filter(
            SystemSnapshot.server_id == srv.id,
            SystemSnapshot.timestamp >= now - timedelta(minutes=10),
        )
        .order_by(desc(SystemSnapshot.timestamp))
        .limit(12)
        .all()
    )
    if not snaps:
        return inst
    latest = snaps[0]
    if latest.timestamp < now - timedelta(seconds=FRESH_SNAP_SECS):
        return inst

    th = get_server_thresholds(srv, db)
    tier = getattr(srv, "tier", 2) or 2
    is_prod = (tier == 1)

    # Kunci masalah yang saat ini aktif terbuka untuk server ini
    open_keys = {
        r[0] for r in db.query(ServerProblem.key).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).all()
    }

    # 1. Evaluasi Memori RAM (Unified Key: ram_usage)
    recent_mems = [
        (s.mem_used / s.mem_total * 100)
        for s in snaps[:3]
        if (s.mem_total or 0) > 0 and s.mem_used is not None
    ]
    if recent_mems:
        cur_ram = recent_mems[0]
        mem_total, mem_used = latest.mem_total or 0, latest.mem_used or 0
        is_ram_open = "ram_usage" in open_keys
        should_emit_ram = False
        ram_sev = "warning"

        if is_ram_open:
            if cur_ram >= th["ram_danger"]:
                should_emit_ram = True
                ram_sev = "danger" if is_prod else "warning"
            elif is_prod and cur_ram >= 90.0:
                should_emit_ram = True
                ram_sev = "average"
            elif cur_ram >= th["ram_warn"]:
                should_emit_ram = True
                ram_sev = "warning"
        else:
            if len(recent_mems) >= 3 and all(m >= th["ram_warn"] for m in recent_mems):
                should_emit_ram = True
                ram_avg = sum(recent_mems) / len(recent_mems)
                if cur_ram >= th["ram_danger"] and ram_avg >= th["ram_danger"]:
                    ram_sev = "danger" if is_prod else "warning"
                elif is_prod and (cur_ram >= 90.0 or ram_avg >= 90.0):
                    ram_sev = "average"
                else:
                    ram_sev = "warning"

        if should_emit_ram:
            active_th = th["ram_danger"] if ram_sev == "danger" else (90.0 if ram_sev == "average" else th["ram_warn"])
            label_text = f"RAM HAMPIR PENUH: {cur_ram:.0f}% (ambang {active_th:.0f}%)" if ram_sev == "danger" else (f"RAM sangat tinggi: {cur_ram:.0f}% (ambang {active_th:.0f}%)" if ram_sev == "average" else f"RAM tinggi: {cur_ram:.0f}% (ambang {active_th:.0f}%)")
            inst.append({
                "key": "ram_usage",
                "severity": ram_sev,
                "message": f"{label_text} ({_fmt_size(mem_used)} / {_fmt_size(mem_total)})",
                "tip": RAM_TIP,
                "event_at": snaps[min(len(snaps) - 1, 2)].timestamp if not is_ram_open else None,
                "context": _build_problem_context("ram_usage", srv, pct=cur_ram, used=mem_used, total=mem_total, threshold=active_th, severity=ram_sev),
            })

    # 2. Evaluasi Swap Disk (Unified Key: swap_usage)
    recent_swaps = [
        (s.swap_used / s.swap_total * 100)
        for s in snaps[:3]
        if (s.swap_total or 0) > 0 and s.swap_used is not None
    ]
    if recent_swaps:
        cur_swap = recent_swaps[0]
        swap_total, swap_used = latest.swap_total or 0, latest.swap_used or 0
        is_swap_open = "swap_usage" in open_keys
        should_emit_swap = False
        swap_sev = "warning"

        if is_swap_open:
            if cur_swap >= th["swap_danger"]:
                should_emit_swap = True
                swap_sev = "danger" if is_prod else "warning"
            elif is_prod and cur_swap >= 90.0:
                should_emit_swap = True
                swap_sev = "average"
            elif cur_swap >= th["swap_warn"]:
                should_emit_swap = True
                swap_sev = "warning"
        else:
            if len(recent_swaps) >= 3 and all(s >= th["swap_warn"] for s in recent_swaps):
                should_emit_swap = True
                swap_avg = sum(recent_swaps) / len(recent_swaps)
                if cur_swap >= th["swap_danger"] and swap_avg >= th["swap_danger"]:
                    swap_sev = "danger" if is_prod else "warning"
                elif is_prod and (cur_swap >= 90.0 or swap_avg >= 90.0):
                    swap_sev = "average"
                else:
                    swap_sev = "warning"

        if should_emit_swap:
            active_th = th["swap_danger"] if swap_sev == "danger" else (90.0 if swap_sev == "average" else th["swap_warn"])
            label_text = f"Swap hampir penuh: {cur_swap:.0f}% (ambang {active_th:.0f}%) — RAM menipis" if swap_sev == "danger" else (f"Swap sangat tinggi: {cur_swap:.0f}% (ambang {active_th:.0f}%)" if swap_sev == "average" else f"Swap terpakai tinggi: {cur_swap:.0f}% (ambang {active_th:.0f}%)")
            inst.append({
                "key": "swap_usage",
                "severity": swap_sev,
                "message": label_text,
                "tip": SWAP_TIP,
                "event_at": snaps[min(len(snaps) - 1, 2)].timestamp if not is_swap_open else None,
                "context": _build_problem_context("swap_usage", srv, pct=cur_swap, used=swap_used, total=swap_total, threshold=active_th, severity=swap_sev),
            })

    # 3. Evaluasi Prosesor CPU (Unified Key: cpu_usage)
    recent_cpus = [s.cpu for s in snaps[:3] if s.cpu is not None]
    if recent_cpus:
        cur_cpu = recent_cpus[0]
        recent_avg = sum(recent_cpus) / len(recent_cpus)
        is_cpu_open = "cpu_usage" in open_keys
        should_emit_cpu = False
        cpu_sev = "warning"

        if is_cpu_open:
            if cur_cpu >= th["cpu_danger"] or recent_avg >= th["cpu_danger"]:
                should_emit_cpu = True
                cpu_sev = "danger" if is_prod else "warning"
            elif is_prod and (cur_cpu >= 90.0 or recent_avg >= 90.0):
                should_emit_cpu = True
                cpu_sev = "average"
            elif cur_cpu >= th["cpu_warn"] or recent_avg >= th["cpu_warn"]:
                should_emit_cpu = True
                cpu_sev = "warning"
        else:
            if len(recent_cpus) >= 3 and (all(c >= th["cpu_warn"] for c in recent_cpus) or recent_avg >= th["cpu_warn"]):
                should_emit_cpu = True
                if recent_avg >= th["cpu_danger"] and cur_cpu >= th["cpu_danger"]:
                    cpu_sev = "danger" if is_prod else "warning"
                elif is_prod and (recent_avg >= 90.0 or cur_cpu >= 90.0):
                    cpu_sev = "average"
                else:
                    cpu_sev = "warning"

        if should_emit_cpu:
            active_th = th["cpu_danger"] if cpu_sev == "danger" else (90.0 if cpu_sev == "average" else th["cpu_warn"])
            label_text = f"CPU jenuh/saturasi: {cur_cpu:.0f}% (ambang {active_th:.0f}%) (rata-rata {recent_avg:.0f}%)" if cpu_sev == "danger" else (f"CPU sangat tinggi: {cur_cpu:.0f}% (ambang {active_th:.0f}%) (rata-rata {recent_avg:.0f}%)" if cpu_sev == "average" else f"CPU tinggi: {cur_cpu:.0f}% (ambang {active_th:.0f}%) (rata-rata {recent_avg:.0f}%)")
            inst.append({
                "key": "cpu_usage",
                "severity": cpu_sev,
                "message": label_text,
                "tip": CPU_TIP,
                "event_at": snaps[min(len(snaps) - 1, 2)].timestamp if not is_cpu_open else None,
                "context": _build_problem_context("cpu_usage", srv, cpu_avg=recent_avg, cpu_max=cur_cpu, threshold=active_th, severity=cpu_sev),
            })

    disks = None
    if latest.disks:
        try:
            disks = json.loads(latest.disks)
        except (TypeError, ValueError):
            disks = None
    for d in disks or []:
        mount = d.get("mount", "?")
        if d.get("is_ro"):
            ro_sev = "danger" if is_prod else "warning"
            inst.append({
                "key": f"disk_ro:{mount}", "severity": ro_sev,
                "message": f"Partisi disk {mount} READ-ONLY (sistem berkas terkunci — operasi tulis ditolak!)",
                "tip": f"Filesystem beralih ke mode read-only akibat proteksi kernel/error I/O. Cek kernel: 'dmesg -T | grep -i ext4'. Lakukan remount: 'sudo mount -o remount,rw {mount}'.",
                "context": _build_problem_context(f"disk_ro:{mount}", srv, mount=mount),
            })
        total, used = d.get("total") or 0, d.get("used") or 0
        if total <= 0:
            continue
        dpct = used / total * 100 if total else 0
        if dpct >= th["disk_danger"]:
            disk_sev = "danger" if is_prod else "warning"
            inst.append({
                "key": f"disk_usage:{mount}", "severity": disk_sev,
                "message": f"Disk {mount} HAMPIR PENUH: {dpct:.0f}% (ambang {th['disk_danger']:.0f}%) ({_fmt_size(used)} / {_fmt_size(total)})",
                "tip": DISK_TIP,
                "context": _build_problem_context(f"disk_usage:{mount}", srv, mount=mount, used=used, total=total, pct=dpct, threshold=th["disk_danger"], severity=disk_sev),
            })
        elif is_prod and dpct >= 90.0:
            inst.append({
                "key": f"disk_usage:{mount}", "severity": "average",
                "message": f"Disk {mount} terisi sangat tinggi: {dpct:.0f}% ({_fmt_size(used)} / {_fmt_size(total)})",
                "tip": DISK_TIP,
                "context": _build_problem_context(f"disk_usage:{mount}", srv, mount=mount, used=used, total=total, pct=dpct, threshold=90.0, severity="average"),
            })
        elif dpct >= th["disk_warn"]:
            inst.append({
                "key": f"disk_usage:{mount}", "severity": "warning",
                "message": f"Disk {mount} terisi tinggi: {dpct:.0f}% (ambang {th['disk_warn']:.0f}%)",
                "tip": DISK_TIP,
                "context": _build_problem_context(f"disk_usage:{mount}", srv, mount=mount, used=used, total=total, pct=dpct, threshold=th["disk_warn"], severity="warning"),
            })
    return inst


def _is_admin_service(name: str, port: int | None = None, proc: str | None = None) -> bool:
    """Mendeteksi apakah suatu service adalah layanan administratif/remote/pelengkap
    (seperti sshd, ntp, agent, syslog) yang jika down tidak melumpuhkan operasional aplikasi web/bisnis klien."""
    n = (name or "").lower().strip()
    p = (proc or "").lower().strip()
    admin_keywords = (
        "ssh", "sshd", "chrony", "chronyd", "ntp", "ntpd", "timesyncd",
        "rsyslog", "syslog", "journald", "fail2ban", "pantau-agent",
        "snmp", "snmpd", "zabbix", "node_exporter", "promtail", "vector", "filebeat",
        "cron", "crond", "anacron"
    )
    if any(n == kw or n.startswith(kw + "-") or n.startswith(kw + "_") or n.endswith("-" + kw) or n.endswith("_" + kw) for kw in admin_keywords):
        return True
    if any(p == kw or p.startswith(kw + "-") or p.startswith(kw + "_") for kw in admin_keywords):
        return True
    try:
        if port is not None and int(port) == 22:
            return True
    except (ValueError, TypeError):
        pass
    return False


def _problem_instances(srv, extras, svc_data, db=None) -> list:
    """Masalah yang sedang terjadi -> [{key,severity,message,tip,context}] (Zabbix-like)."""
    inst: list = []

    # 1. Deteksi Konflik IP Agen (Multi-Agent / Klon VM Split-Brain)
    with _agent_tracker_lock:
        s_ips = dict(_agent_ip_tracker.get(srv.id, {}))
    now_ep = time.time()
    active_ips = [ip for ip, ts in s_ips.items() if (now_ep - ts) <= 120]
    tier = getattr(srv, "tier", 2) or 2
    is_prod = (tier == 1)
    if len(active_ips) > 1:
        active_ips_sorted = sorted(active_ips)
        inst.append({
            "key": "agent_conflict",
            "severity": "danger" if is_prod else "warning",
            "message": f"Konflik Agen Terdeteksi: API key aktif di beberapa host ({', '.join(active_ips_sorted)})",
            "tip": "Dua mesin berbeda melapor dengan API key yang sama (kemungkinan VM dikloning atau duplikat instalasi agen). "
                   "Hentikan agent_pantau di mesin kloningan atau daftarkan sebagai server baru.",
            "context": _build_problem_context("agent_conflict", srv, ips=active_ips_sorted),
        })

    if srv.last_seen is None:
        return inst

    # 2. Deteksi Host Terputus / Agen Tidak Melapor dengan Eskalasi Keparahan Dinamis
    ls = srv.last_seen
    if ls.tzinfo is None:
        ls = ls.replace(tzinfo=timezone.utc)
    sec_silent = (datetime.now(timezone.utc) - ls).total_seconds()

    if _server_stale(srv):
        # Periksa apakah server dimatikan atau direboot secara sadar oleh operator (poweroff_host / reboot_host)
        is_op_poweroff = False
        is_op_reboot = False
        op_by = "OPERATOR"
        if db is not None:
            try:
                host_cmd_cutoff = datetime.utcnow() - timedelta(minutes=30)
                last_cmd = (
                    db.query(Command)
                    .filter(
                        Command.server_id == srv.id,
                        Command.action.in_(["poweroff_host", "reboot_host"]),
                        Command.created_at >= host_cmd_cutoff,
                    )
                    .order_by(desc(Command.created_at))
                    .first()
                )
                if last_cmd:
                    cmd_time = last_cmd.created_at
                    ls_time = srv.last_seen
                    if ls_time and ls_time.tzinfo:
                        ls_time = ls_time.replace(tzinfo=None)
                    if cmd_time and (ls_time is None or cmd_time >= ls_time - timedelta(seconds=60)):
                        op_by = (last_cmd.issued_by or "OPERATOR").upper()
                        if last_cmd.action == "reboot_host":
                            is_op_reboot = True
                        else:
                            is_op_poweroff = True
            except Exception:
                pass

        if is_op_poweroff:
            stale_sev = "warning"
            stale_msg = f"Host dimatikan oleh operator ({op_by})"
            stale_tip = f"Server sengaja dimatikan melalui perintah poweroff oleh operator ({op_by})."
        elif is_op_reboot:
            stale_sev = "warning"
            stale_msg = f"Server sedang di-reboot oleh operator ({op_by})"
            stale_tip = f"Server sedang dalam proses mulai ulang (reboot) yang diinisiasi oleh operator ({op_by})."
        elif is_prod:
            # Server Produksi (Layanan Vital 24/7):
            # - Detik awal (> 15s) s/d 1 menit (< 60s): Average (GAWAT)
            # - >= 60s (1 menit): Danger (KRITIS — Memicu sirene darurat, badge & banner merah)
            dur_txt = f"{int(sec_silent // 60)} mnt" if sec_silent >= 60 else f"{int(sec_silent)} dtk"
            if sec_silent >= 60:
                stale_sev = "danger"
                stale_msg = f"Agen tidak melapor (> {dur_txt}) — SERVER OFFLINE"
                stale_tip = "SEGERA lakukan inspeksi fisik atau virtual mesin server Produksi, periksa suplai daya, dan verifikasi konektivitas jaringan."
            else:
                stale_sev = "average"
                stale_msg = f"Agen tidak melapor (> {int(sec_silent)} dtk)"
                stale_tip = "Periksa suplai daya server, koneksi jaringan, atau status service agent_pantau."
        else:
            # Server Non-Produksi (Lab / Pengujian / Uji Coba / Kloning / Dev):
            # - Selalu masuk Warning (Peringatan). Tenang tanpa sirene darurat / banner merah.
            dur_txt = f"{int(sec_silent // 60)} mnt" if sec_silent >= 60 else f"{int(sec_silent)} dtk"
            stale_sev = "warning"
            stale_msg = f"Agen tidak melapor (> {dur_txt})"
            stale_tip = "Server non-produksi (lab/pengujian) sedang tidak aktif atau agent_pantau belum berjalan."

        inst.append({
            "key": "agent_stale",
            "severity": stale_sev,
            "message": stale_msg,
            "tip": stale_tip,
            "event_at": srv.last_seen.replace(tzinfo=None) if srv.last_seen else None,
            "context": _build_problem_context(
                "agent_stale", srv,
                sec_silent=int(sec_silent),
                escalation_level=stale_sev,
                last_seen_str=ls.strftime("%d %b %Y %H:%M:%S UTC")
            )
        })
        # PENTING: Karena server mati/offline, HENTIKAN penambahan masalah layanan (service_down:*)
        # dan metrik resource hardware (CPU/RAM/Disk). Seluruh status layanan tersupresi oleh status server mati.
        return inst

    if db is not None:
        inst += _resource_problem_instances(db, srv)
    if extras is not None:
        th = get_server_thresholds(srv, db)
        if extras.agent_version and _is_agent_outdated(extras.agent_version, settings.APP_VERSION):
            inst.append({
                "key": "agent_outdated",
                "severity": "warning",
                "message": f"Versi Agen Pantau di {srv.hostname} (v{extras.agent_version}) lebih lama dari dashboard (v{settings.APP_VERSION}) — perlu update",
                "tip": AGENT_OUTDATED_TIP,
                "context": _build_problem_context("agent_outdated", srv, agent_version=extras.agent_version, app_version=settings.APP_VERSION),
            })
        if (extras.apt_upgradable or 0) > 0 and getattr(srv, "is_isolated_net", 0) != 1:
            inst.append({"key": "apt_updates", "severity": "info",
                         "message": f"{extras.apt_upgradable} paket menunggu upgrade",
                         "tip": APT_TIP,
                         "context": _build_problem_context("apt_updates", srv, upgradable=extras.apt_upgradable)})

        # Evaluasi Konflik Konfigurasi Platform (Platform Mismatch Conflict Triage)
        plat_ovr = getattr(srv, "platform_override", None)
        if plat_ovr in ("baremetal", "vm", "lxc") and getattr(extras, "hardware_specs", None):
            try:
                hw = json.loads(extras.hardware_specs) if isinstance(extras.hardware_specs, str) else extras.hardware_specs
                plat_dict = hw.get("platform", {}) if isinstance(hw, dict) else {}
                detected_info = _classify_platform(plat_dict, override=None)
                detected_type = detected_info.get("type")
                if detected_type and detected_type != plat_ovr:
                    ovr_names = {
                        "baremetal": "Fisik / Baremetal",
                        "vm": "Mesin Virtual (VM)",
                        "lxc": "Kontainer (LXC)"
                    }
                    inst.append({
                        "key": "platform_conflict",
                        "severity": "warning",
                        "message": "Konfigurasi Platform Server Tidak Sesuai",
                        "tip": f"Server disetel manual sebagai '{ovr_names.get(plat_ovr, plat_ovr)}', namun agen mendeteksi sistem berjalan pada platform '{detected_info.get('label')}'. Disarankan mengubah konfigurasi ke 'Auto Deteksi'.",
                        "context": _build_problem_context(
                            "platform_conflict",
                            srv,
                            override=plat_ovr,
                            override_label=ovr_names.get(plat_ovr, plat_ovr),
                            detected_type=detected_type,
                            detected_label=detected_info.get("label"),
                            virt=detected_info.get("virt")
                        )
                    })
            except Exception as e:
                logger.debug("Gagal evaluasi platform_conflict untuk server %s: %s", srv.id, e)

        # Evaluasi Kesehatan Drive S.M.A.R.T. / NVMe
        if getattr(extras, "hardware_specs", None):
            try:
                hw = json.loads(extras.hardware_specs) if isinstance(extras.hardware_specs, str) else extras.hardware_specs
                for disk in (hw.get("disks") or []):
                    if not isinstance(disk, dict):
                        continue
                    dname = str(disk.get("name") or "").strip()
                    if not dname or disk.get("is_virtual"):
                        continue
                    smart = disk.get("smart")
                    if not smart or not isinstance(smart, dict) or smart.get("is_virtual"):
                        continue

                    health = smart.get("health")
                    temp_c = smart.get("temp_c")
                    wear_pct = smart.get("wearout_pct")
                    wear_rem = smart.get("wearout_remaining")
                    realloc = smart.get("reallocated_sectors") or 0

                    # 1. Drive Failing / Kerusakan S.M.A.R.T.
                    if health == "critical" or smart.get("status_label") == "CRITICAL":
                        crit_sev = "danger" if is_prod else "warning"
                        inst.append({
                            "key": f"disk_smart_failing:{dname}",
                            "severity": crit_sev,
                            "message": f"Kesehatan Drive {dname} KRITIS: {smart.get('detail') or 'S.M.A.R.T. Melaporkan Kerusakan Hardware'}",
                            "tip": f"Segera amankan/cadangkan data server dan siapkan unit pengganti untuk drive {dname}. S.M.A.R.T. mendeteksi kegagalan fatal integritas drive.",
                            "context": _build_problem_context("disk_smart_failing", srv, disk=dname, smart=smart, severity=crit_sev),
                        })

                    # 2. Overheating Drive (Suhu Tinggi >= 65°C)
                    elif temp_c and temp_c >= 65:
                        temp_sev = "danger" if (is_prod and temp_c >= 75) else "warning"
                        inst.append({
                            "key": f"disk_smart_temp:{dname}",
                            "severity": temp_sev,
                            "message": f"Suhu Drive {dname} Terlalu Tinggi: {temp_c}°C (Batas Aman < 60°C)",
                            "tip": f"Periksa aliran ventilasi udara dan kinerja kipas pendingin chassis server klien. Suhu berlebih mempercepat degradasi drive {dname}.",
                            "context": _build_problem_context("disk_smart_temp", srv, disk=dname, temp_c=temp_c, smart=smart, severity=temp_sev),
                        })

                    # 3. Sisa Umur SSD / NVMe Menipis (Wearout >= 90% atau Sisa Umur <= 10%)
                    elif (wear_pct is not None and wear_pct >= 90) or (wear_rem is not None and wear_rem <= 10):
                        rem_val = wear_rem if wear_rem is not None else (100 - wear_pct)
                        wear_sev = "danger" if (is_prod and rem_val <= 3) else "warning"
                        inst.append({
                            "key": f"disk_smart_wear:{dname}",
                            "severity": wear_sev,
                            "message": f"Sisa Umur Drive SSD/NVMe {dname} Menipis: {rem_val}% tersisa",
                            "tip": f"Memori flash drive {dname} mendekati batas total daya tahan tulis TBW (Terabytes Written). Jadwalkan penggantian drive.",
                            "context": _build_problem_context("disk_smart_wear", srv, disk=dname, remaining=rem_val, smart=smart, severity=wear_sev),
                        })

                    # 4. Sektor Rusak / Reallocated Sectors Tinggi (> 50 sektor)
                    elif realloc > 50:
                        inst.append({
                            "key": f"disk_smart_sectors:{dname}",
                            "severity": "warning",
                            "message": f"Drive {dname} Mendeteksi {realloc} Sektor Rusak (Reallocated Sectors)",
                            "tip": f"Terdapat sektor fisik yang rusak dan telah dialihkan ke blok cadangan pada drive {dname}. Pantau stabilitas I/O disk.",
                            "context": _build_problem_context("disk_smart_sectors", srv, disk=dname, reallocated=realloc, smart=smart, severity="warning"),
                        })
            except Exception as e:
                logger.debug("Gagal evaluasi disk SMART untuk server %s: %s", srv.id, e)

        # Deteksi sesi remote SSH aktif dari telemetri akun/who (INFO)
        if getattr(extras, "accounts", None):
            try:
                acc_list = json.loads(extras.accounts) if isinstance(extras.accounts, str) else extras.accounts
                if isinstance(acc_list, list):
                    for acc in acc_list:
                        u_name = str(acc.get("user") or "unknown").strip()
                        for s in (acc.get("sessions") or []):
                            if not isinstance(s, dict):
                                continue
                            raw_from = str(s.get("from") or "").strip()
                            r_from = raw_from.strip("()")
                            r_tty = str(s.get("tty") or "").strip()
                            r_time = str(s.get("time") or "").strip()

                            # Deteksi koneksi remote SSH:
                            # Sesi remote memiliki IP klien atau hostname remote di bagian 'from'.
                            # Filter sesi lokal: string kosong, ":0", ":1" (display X11 lokal), atau "local"
                            if r_from and not r_from.startswith(":") and not r_from.lower().startswith("local"):
                                clean_tty_key = r_tty.replace("/", "_") if r_tty else "ssh"
                                clean_from_key = re.sub(r"[^a-zA-Z0-9_\.:-]", "_", r_from)
                                sess_key = f"ssh_active_session:{u_name}:{clean_tty_key}:{clean_from_key}"[:150]

                                tty_disp = f" ({r_tty})" if r_tty else ""
                                time_disp = f" sejak {r_time}" if r_time else ""
                                inst.append({
                                    "key": sess_key,
                                    "severity": "info",
                                    "message": f"Sesi remote SSH aktif: user '{u_name}' dari {r_from}{tty_disp}",
                                    "tip": f"Pengguna '{u_name}' sedang aktif terhubung ke server klien via remote SSH dari {r_from}{tty_disp}{time_disp}. Periksa aktivitas sesi melalui tab Akun atau log autentikasi.",
                                    "context": _build_problem_context(
                                        "ssh_active_session",
                                        srv,
                                        user=u_name,
                                        from_ip=r_from,
                                        tty=r_tty,
                                        login_time=r_time,
                                    ),
                                })
            except Exception as e:
                logger.debug("Gagal evaluasi ssh_active_session untuk server %s: %s", srv.id, e)
        sec = _parse_extras_security(extras)
        if sec:
            failed = int(sec.get("failed") or 0)
            invalid = int(sec.get("invalid_users") or 0)
            nips = len(sec.get("source_ips") or {})
            event_at = None
            if sec.get("last_seen"):
                try:
                    _dt = datetime.fromisoformat(str(sec["last_seen"]))
                    if _dt.tzinfo is not None:
                        _dt = _dt.astimezone(timezone.utc).replace(tzinfo=None)
                    event_at = _dt
                except (TypeError, ValueError):
                    event_at = None
            if event_at is None and extras is not None and extras.updated_at is not None:
                event_at = extras.updated_at  # fallback bila agen tak mengirim last_seen
            if invalid >= SECURITY_DANGER_INVALID or failed >= th["ssh_fail_danger"]:
                ssh_sev = "danger" if is_prod else "warning"
                inst.append({"key": "failed_logins", "severity": ssh_sev,
                             "message": f"Indikasi brute-force SSH: {failed} login gagal (ambang batas >={th['ssh_fail_danger']}), "
                                         f"{invalid} user invalid, dari {nips} IP"
                                         + (f" · terakhir {_rel_dt(event_at)}" if event_at else ""),
                             "tip": SECURITY_TIPS.get(ssh_sev, SECURITY_TIPS["warning"]), "event_at": event_at,
                             "context": _build_problem_context("failed_logins", srv, failed=failed, invalid=invalid, source_ips=sec.get("source_ips") or {}, threshold=th["ssh_fail_danger"], severity=ssh_sev)})
            elif failed >= th["ssh_fail_warn"]:
                inst.append({"key": "failed_logins", "severity": "warning",
                             "message": f"{failed} login SSH gagal dari {nips} IP (ambang >={th['ssh_fail_warn']})"
                                         + (f" · terakhir {_rel_dt(event_at)}" if event_at else "")
                                         + " — waspada brute force",
                             "tip": SECURITY_TIPS["warning"], "event_at": event_at,
                             "context": _build_problem_context("failed_logins", srv, failed=failed, invalid=invalid, source_ips=sec.get("source_ips") or {}, threshold=th["ssh_fail_warn"], severity="warning")})
            elif failed >= 1:
                inst.append({"key": "failed_logins", "severity": "info",
                             "message": f"{failed} login SSH gagal (ringan)"
                                         + (f" · terakhir {_rel_dt(event_at)}" if event_at else ""),
                             "tip": SECURITY_TIPS["info"], "event_at": event_at,
                             "context": _build_problem_context("failed_logins", srv, failed=failed, invalid=invalid, source_ips=sec.get("source_ips") or {}, severity="info")})
    # Evaluasi Event Fatal Kernel & Sistem (OOM Killer, Storage I/O Error, Segfault, Panic)
    oom_event_map: dict[str, dict] = {}
    if extras is not None and getattr(extras, "kernel_events", None):
        try:
            ke_data = json.loads(extras.kernel_events) if isinstance(extras.kernel_events, str) else extras.kernel_events
            if isinstance(ke_data, dict):
                now_ts = time.time()
                for ev in (ke_data.get("events") or []):
                    if not isinstance(ev, dict):
                        continue
                    ev_type = ev.get("type")
                    ev_epoch = float(ev.get("epoch") or 0.0)
                    ev_age = now_ts - ev_epoch if ev_epoch > 0 else 0

                    # Pertahankan event aktif selama jendela 30 menit (1800 dtk)
                    if ev_epoch > 0 and ev_age > 1800:
                        continue

                    ev_time_str = ev.get("time") or ""
                    ev_dt = None
                    if ev_epoch > 0:
                        try:
                            ev_dt = datetime.fromtimestamp(ev_epoch, timezone.utc).replace(tzinfo=None)
                        except Exception:
                            ev_dt = None

                    if ev_type == "oom_kill":
                        p_name = str(ev.get("proc") or "proses").strip()
                        pid = ev.get("pid")
                        pid_txt = f" (PID {pid})" if pid else ""
                        u_name = str(ev.get("unit") or "").strip()
                        clean_proc = p_name.lower()
                        clean_unit = u_name[:-8].lower() if u_name.endswith(".service") else u_name.lower()

                        oom_info = {
                            "proc": p_name,
                            "pid": pid,
                            "unit": u_name,
                            "time": ev_time_str,
                            "message": ev.get("message"),
                        }
                        if clean_proc:
                            oom_event_map[clean_proc] = oom_info
                        if clean_unit:
                            oom_event_map[clean_unit] = oom_info

                        oom_sev = "danger" if is_prod else "warning"
                        inst.append({
                            "key": f"oom_kill:{clean_proc}",
                            "severity": oom_sev,
                            "message": f"Proses '{p_name}' dihentikan paksa oleh Kernel (Out of Memory - OOM Killer)",
                            "tip": f"Kernel Linux menghentikan paksa proses {p_name}{pid_txt} karena server kehabisan memori RAM/Swap fisik. Periksa kebocoran memori aplikasi, kurangi beban kerja, atau tingkatkan kapasitas RAM server.",
                            "event_at": ev_dt,
                            "context": _build_problem_context("oom_kill", srv, process=p_name, pid=pid, unit=u_name, event_time=ev_time_str, raw=ev.get("message")),
                        })

                    elif ev_type == "disk_io_error":
                        dev_name = str(ev.get("dev") or "storage").strip()
                        io_sev = "danger" if is_prod else "warning"
                        inst.append({
                            "key": f"disk_io_error:{dev_name}",
                            "severity": io_sev,
                            "message": f"Galat I/O Storage Terdeteksi pada {dev_name}: Kemungkinan Kerusakan Media Fisik",
                            "tip": f"Kernel Linux mencatat kegagalan baca/tulis sektor fisik (I/O error) pada drive {dev_name}. Segera amankan cadangan data (backup) dan periksa integritas media penyimpanan.",
                            "event_at": ev_dt,
                            "context": _build_problem_context("disk_io_error", srv, device=dev_name, event_time=ev_time_str, raw=ev.get("message")),
                        })

                    elif ev_type == "kernel_panic":
                        panic_sev = "danger" if is_prod else "warning"
                        inst.append({
                            "key": "kernel_panic",
                            "severity": panic_sev,
                            "message": "Kernel Panic atau Kegagalan Fatal Hardware (MCE) Terdeteksi",
                            "tip": "Kernel Linux mengalami kegagalan fatal (kernel panic) atau Machine Check Exception (MCE). Periksa log dmesg/journalctl untuk analisis hardware crash dump.",
                            "event_at": ev_dt,
                            "context": _build_problem_context("kernel_panic", srv, detail=ev.get("detail"), raw=ev.get("message")),
                        })

                    elif ev_type == "segfault":
                        p_name = str(ev.get("proc") or "proses").strip()
                        seg_sev = "average" if is_prod else "warning"
                        inst.append({
                            "key": f"segfault:{p_name.lower()}",
                            "severity": seg_sev,
                            "message": f"Proses '{p_name}' Mengalami Segmentasi Galat (Segfault / Crash)",
                            "tip": f"Aplikasi {p_name} mengalami crash memori tidak valid (segfault). Periksa berkas konfigurasi, kompatibilitas binary, atau bug memori aplikasi.",
                            "event_at": ev_dt,
                            "context": _build_problem_context("segfault", srv, process=p_name, event_time=ev_time_str, raw=ev.get("message")),
                        })
        except Exception as e:
            logger.debug("Gagal evaluasi kernel_events untuk server %s: %s", srv.id, e)

    # Kumpulkan seluruh layanan yang sengaja dihentikan oleh operator pada server ini
    # (dari tabel Service dan riwayat Command stop systemd/service terkini)
    op_action_map: dict[str, dict] = {}
    if db is not None:
        try:
            # 1. Dari tabel Service (layanan yang sengaja dihentikan/dimatikan operator)
            for s in db.query(Service).filter(Service.server_id == srv.id).all():
                if s.ignored_reason and ("DIMATIKAN OLEH OPERATOR" in s.ignored_reason or "DIHENTIKAN OLEH OPERATOR" in s.ignored_reason):
                    by_txt = s.ignored_by or "operator"
                    if s.service_name:
                        op_action_map[s.service_name.lower()] = {"action": "stop", "by": by_txt}
                    if s.process_name:
                        op_action_map[s.process_name.lower()] = {"action": "stop", "by": by_txt}

            # 2. Dari riwayat Command aksi stop terkini (dibatasi 15 menit terakhir)
            cmd_cutoff = datetime.utcnow() - timedelta(minutes=15)
            recent_cmds = (
                db.query(Command)
                .filter(
                    Command.server_id == srv.id,
                    Command.action.in_(["stop", "start"]),
                    Command.created_at >= cmd_cutoff,
                )
                .order_by(desc(Command.id))
                .limit(20)
                .all()
            )
            seen_cmd_targets = set()
            for cmd in recent_cmds:
                tgt = None
                if cmd.service_id:
                    s_rec = db.query(Service).filter(Service.id == cmd.service_id).first()
                    if s_rec:
                        tgt = s_rec.service_name
                elif cmd.params:
                    try:
                        cp = json.loads(cmd.params) if isinstance(cmd.params, str) else cmd.params
                        tgt = cp.get("service_name") or cp.get("unit") or cp.get("process_name")
                    except Exception:
                        tgt = None
                if tgt:
                    clean_tgt = (tgt[:-8] if tgt.endswith(".service") else tgt).lower()
                    if clean_tgt not in seen_cmd_targets:
                        seen_cmd_targets.add(clean_tgt)
                        if cmd.action == "stop" and cmd.status in ("pending", "executing", "success"):
                            by_txt = cmd.issued_by or "operator"
                            op_action_map[clean_tgt] = {"action": "stop", "by": by_txt}
                            op_action_map[tgt.lower()] = {"action": "stop", "by": by_txt}
        except Exception as e:
            logger.debug("Gagal memetakan layanan operator server %s: %s", srv.id, e)

    # Saring agar layanan yang saat ini aktif (up) tidak dianggap sebagai dihentikan operator
    up_names = {
        (d.get("name") or "").lower() for d in svc_data or [] if d.get("status") == "up"
    } | {
        (d.get("proc") or d.get("process") or "").lower() for d in svc_data or [] if d.get("status") == "up"
    }
    up_names.discard("")
    for u_n in up_names:
        op_action_map.pop(u_n, None)
        op_action_map.pop(u_n + ".service", None)

    for d in svc_data or []:
        name = d.get("name", "?")
        st = d.get("status")
        port = d.get("port")
        proc = d.get("proc") or d.get("process")
        is_admin = _is_admin_service(name, port, proc)

        name_lower = (name or "").lower()
        proc_lower = (proc or "").lower()
        act_info = op_action_map.get(name_lower) or op_action_map.get(proc_lower)
        is_op_action = bool(act_info)
        op_by = act_info.get("by", "operator") if act_info else "operator"
        oom_info = None

        if st == "down":
            if is_op_action:
                # Semua tindakan operator yang sengaja mematikan layanan
                # diklasifikasikan sebagai insiden tingkat keparahan PERINGATAN (warning)
                svc_sev = "warning"
                svc_msg = f"Layanan {name} dimatikan oleh operator ({op_by})"
                svc_tip = f"Unit layanan {name} sengaja dihentikan melalui panel kontrol oleh operator ({op_by}). Tindakan pemeliharaan tidak memicu alarm darurat."
            else:
                # Periksa apakah layanan down karena dihentikan paksa oleh OOM Killer
                oom_info = oom_event_map.get(name_lower) or oom_event_map.get(proc_lower)
                if not oom_info:
                    for oom_key, o_info in oom_event_map.items():
                        if (oom_key and (oom_key in name_lower or name_lower in oom_key)) or \
                           (proc_lower and (oom_key in proc_lower or proc_lower in oom_key)):
                            oom_info = o_info
                            break
                if oom_info:
                    svc_sev = "danger" if is_prod else "warning"
                    svc_msg = f"Layanan {name} Down — Dihentikan paksa oleh Kernel (OOM Killer)"
                    svc_tip = f"Layanan {name} tidak aktif karena proses utamanya ({oom_info.get('proc')}) dihentikan paksa oleh Kernel Linux akibat kehabisan memori RAM/Swap (OOM Killer). Jalankan: sudo systemctl restart {name} setelah memastikan ketersediaan RAM."
                else:
                    # Hitung durasi layanan telah down dari rekaman ServerProblem terbuka
                    down_secs = 0.0
                    if db is not None:
                        try:
                            open_svc_prob = db.query(ServerProblem).filter(
                                ServerProblem.server_id == srv.id,
                                ServerProblem.key == f"service_down:{name}",
                                ServerProblem.resolved_at.is_(None),
                            ).first()
                            if open_svc_prob and open_svc_prob.started_at:
                                now_utc = datetime.utcnow()
                                st_dt = open_svc_prob.started_at
                                if st_dt.tzinfo:
                                    st_dt = st_dt.replace(tzinfo=None)
                                down_secs = max(0.0, (now_utc - st_dt).total_seconds())
                        except Exception:
                            pass

                    if is_prod:
                        # Server Produksi (Layanan Vital 24/7):
                        # Seluruh services server produksi:
                        # - 0 s/d 60 detik (< 60s): GAWAT (average)
                        # - > 60 detik (>= 60s): KRITIS (danger — Memicu alarm, badge & banner merah)
                        if down_secs >= 60:
                            svc_sev = "danger"
                            svc_msg = f"Layanan {name} Down (KRITIS)"
                            svc_tip = SVC_DOWN_TIP.format(name=name)
                        else:
                            svc_sev = "average"
                            svc_msg = f"Layanan {name} Down"
                            svc_tip = SVC_DOWN_TIP.format(name=name)
                    else:
                        # Server Non-Produksi (Lab / Pengujian / Uji Coba / Kloning / Dev):
                        # Seluruh services server non-produksi:
                        # - Hanya PERINGATAN (warning) tanpa eskalasi! Tenang tanpa sirene/banner merah.
                        svc_sev = "warning"
                        svc_msg = f"Layanan {name} Down"
                        svc_tip = SVC_DOWN_TIP.format(name=name)

            inst.append({
                "key": f"service_down:{name}", "severity": svc_sev,
                "message": svc_msg,
                "tip": svc_tip,
                "context": _build_problem_context(
                    "service_down:", srv,
                    service_name=name, port=port, proc=proc,
                    health_msg=d.get("health_msg"),
                    conflict_ips=active_ips if len(active_ips) > 1 else None,
                    is_op_stop=is_op_action,
                    op_by=op_by,
                    oom_killed=bool(oom_info),
                    oom_proc=oom_info.get("proc") if oom_info else None,
                    oom_time=oom_info.get("time") if oom_info else None,
                ),
            })
        elif st == "unknown":
            inst.append({"key": f"svc_no_data:{name}", "severity": "info",
                         "message": f"Layanan {name} belum ada data",
                         "tip": SVC_NODATA_TIP,
                         "context": _build_problem_context(f"svc_no_data:{name}", srv, service_name=name, port=d.get("port"))})
    return inst




def _fmt_duration(start: datetime, end: datetime) -> str:
    s = max(0, int((end - start).total_seconds()))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h} j {m} mnt"
    if m:
        return f"{m} mnt {sec} dtk"
    return f"{sec} dtk"


def _rel_dt(dt: datetime, now: datetime | None = None) -> str:
    """Waktu relatif (bebas zona waktu) untuk menampilkan aktivitas terakhir."""
    now = now or datetime.utcnow()
    s = int((now - dt).total_seconds())
    if s < 10:
        return "baru saja"
    if s < 60:
        return f"{s} dtk lalu"
    if s < 3600:
        return f"{s // 60} mnt lalu"
    if s < 86400:
        h, m = divmod(s // 60, 60)
        return f"{h} j {m} mnt lalu"
    return f"{s // 86400} h lalu"


def _problem_component(key: str) -> str:
    if not key:
        return "Sistem"
    if key.startswith("service_down:") or key.startswith("svc_no_data:"):
        svc = key.split(":", 1)[1]
        return f"Layanan ({svc})"
    if key.startswith("oom_kill:"):
        proc = key.split(":", 1)[1] if ":" in key else ""
        return f"Kernel / OOM ({proc})" if proc else "Kernel (OOM Killer)"
    if key.startswith("disk_io_error:"):
        dev = key.split(":", 1)[1] if ":" in key else ""
        return f"Penyimpanan (I/O {dev})" if dev else "Penyimpanan (I/O Error)"
    if key in ("kernel_panic", "hardware_error_mce"):
        return "Kernel / Sistem"
    if key.startswith("segfault:"):
        proc = key.split(":", 1)[1] if ":" in key else ""
        return f"Aplikasi Crash ({proc})" if proc else "Aplikasi (Segfault)"
    if key == "agent_stale":
        return "Agen / Host"
    if key in ("cpu_usage", "cpu_high", "cpu_saturated", "cpu_load"):
        return "Processor (CPU)"
    if key in ("ram_usage", "ram_high", "ram_critical", "swap_usage", "swap_high", "swap_critical", "mem_high"):
        return "Memori (RAM)"
    if key.startswith("disk_usage:") or key.startswith("disk_high:") or key.startswith("disk_critical:") or key.startswith("disk_ro:"):
        mount = key.split(":", 1)[1] if ":" in key else ""
        return f"Penyimpanan ({mount})" if mount else "Penyimpanan (Disk)"
    if key.startswith("disk_smart_"):
        dev = key.split(":", 1)[1] if ":" in key else ""
        return f"Drive ({dev})" if dev else "Penyimpanan (SMART)"
    if key in ("security_danger", "failed_logins"):
        return "Keamanan (SSH)"
    if key == "apt_updates":
        return "Paket OS (APT)"
    if key == "agent_conflict":
        return "Jaringan / IP Agen"
    if key == "platform_conflict":
        return "Platform / Virtualisasi"
    if key.startswith("ssh_active_session:"):
        return "Sesi Remote (SSH)"
    return "Sistem"


def _problem_row2dict(row) -> dict:
    end = row.resolved_at
    is_op = bool(
        ("dimatikan oleh operator" in (row.message or "").lower())
        or ("dihentikan oleh operator" in (row.message or "").lower())
        or ("di-reboot oleh operator" in (row.message or "").lower())
        or ("oleh operator" in (row.message or "").lower())
        or (row.ignored_reason and "OPERATOR" in row.ignored_reason)
    )

    raw_ack = getattr(row, "acknowledged_by", None)
    ack_by = None
    if raw_ack:
        raw_str = str(raw_ack).strip()
        ack_by = "master-admin" if raw_str.lower() in ("admin", "master-admin", "master_admin") else raw_str

    res_note = getattr(row, "resolved_note", None)
    res_note_str = str(res_note).strip().lower() if res_note else ""
    key = getattr(row, "key", "") or ""

    if ack_by:
        res_type = "manual"
        op_label = "Master Admin" if ack_by == "master-admin" else ack_by
        res_label = f"✓ Ditangani ({op_label})"
        res_label_en = f"✓ Handled ({op_label})"
        res_tip = f"Diselesaikan secara manual oleh operator {op_label}"
        res_tip_en = f"Handled manually by operator {op_label}"
        res_badge_cls = "badge-up"
    elif res_note_str == "server_offline":
        res_type = "stale_closed"
        res_label = "Ditutup Otomatis (Host Terputus)"
        res_label_en = "Closed (Host Down)"
        res_tip = "Insiden layanan ditutup sementara otomatis karena host terputus / agen berhenti melapor (supresi alarm bertingkat)"
        res_tip_en = "Service incident closed automatically because host disconnected (alarm suppression)"
        res_badge_cls = "badge-muted"
    elif res_note_str == "server_online" or key == "agent_stale":
        res_type = "online"
        res_label = "✓ Koneksi Pulih (Kembali Online)"
        res_label_en = "✓ Host Back Online"
        res_tip = "Koneksi agen pulih sepenuhnya dan server aktif melapor kembali"
        res_tip_en = "Agent connection restored and server reporting online"
        res_badge_cls = "badge-up"
    elif res_note_str == "service_up":
        res_type = "service_up"
        res_label = "✓ Layanan Berjalan Kembali"
        res_label_en = "✓ Service Running"
        res_tip = "Layanan sistem telah beroperasi normal kembali"
        res_tip_en = "System service resumed and running normally"
        res_badge_cls = "badge-up"
    elif res_note_str == "session_closed":
        res_type = "session_closed"
        res_label = "✓ Sesi SSH Ditutup"
        res_label_en = "✓ SSH Closed"
        res_tip = "Sesi remote SSH telah selesai ditutup dengan aman"
        res_tip_en = "Remote SSH session closed safely"
        res_badge_cls = "badge-muted"
    elif res_note_str in ("duplicate_cleanup", "dedup"):
        res_type = "dedup"
        res_label = "Dibersihkan (Duplikasi)"
        res_label_en = "Cleaned (Duplicate)"
        res_tip = "Entri insiden duplikat dibersihkan secara otomatis oleh sistem konsolidasi"
        res_tip_en = "Duplicate incident record cleaned automatically by consolidation engine"
        res_badge_cls = "badge-muted"
    elif res_note_str == "operator_start":
        res_type = "manual"
        res_label = "✓ Dijalankan Operator"
        res_label_en = "✓ Started by Operator"
        res_tip = "Layanan berhasil dihidupkan kembali melalui tindakan operator"
        res_tip_en = "Service restarted by operator action"
        res_badge_cls = "badge-up"
    elif "upgrade" in res_note_str:
        res_type = "auto"
        res_label = "✓ Pembaruan Selesai"
        res_label_en = "✓ Upgrade Completed"
        res_tip = "Pembaruan paket sistem selesai dan kondisi kembali aman"
        res_tip_en = "Package upgrade finished and condition secured"
        res_badge_cls = "badge-up"
    elif res_note_str in ("auto", "resolved", "auto (reset)", "ok", "normal"):
        res_type = "auto"
        res_label = "✓ Pulih Normal (Otomatis)"
        res_label_en = "✓ Auto Recovered"
        res_tip = "Metrik sistem kembali normal dan aman secara otomatis"
        res_tip_en = "System metrics normalized automatically"
        res_badge_cls = "badge-up"
    elif res_note:
        res_type = "other"
        res_label = f"✓ {res_note}"
        res_label_en = f"✓ {res_note}"
        res_tip = str(res_note)
        res_tip_en = str(res_note)
        res_badge_cls = "badge-up"
    else:
        res_type = "auto"
        res_label = "✓ Pulih Normal"
        res_label_en = "✓ Recovered"
        res_tip = "Kondisi sistem kembali beroperasi normal"
        res_tip_en = "System condition recovered normally"
        res_badge_cls = "badge-up"

    return {
        "id": row.id,
        "key": row.key, "severity": row.severity, "message": row.message,
        "tip": row.tip, "started_at": row.started_at, "resolved_at": end,
        "is_open": end is None,
        "component": _problem_component(row.key),
        "acknowledged_by": ack_by,
        "acknowledged_at": row.acknowledged_at,
        "resolved_note": row.resolved_note,
        "res_type": res_type,
        "res_label": res_label,
        "res_label_en": res_label_en,
        "res_tip": res_tip,
        "res_tip_en": res_tip_en,
        "res_badge_cls": res_badge_cls,
        "durasi": _fmt_duration(row.started_at, end if end else datetime.utcnow()),
        "is_ignored": bool(getattr(row, "is_ignored", 0)),
        "is_operator_action": is_op,
        "ignored_until": getattr(row, "ignored_until", None),
        "ignored_by": ("master-admin" if getattr(row, "ignored_by", None) == "admin" else getattr(row, "ignored_by", None)),
        "ignored_reason": getattr(row, "ignored_reason", None),
        "ignore_mode": getattr(row, "ignore_mode", None),
        "context": getattr(row, "context", None),
    }


def _enrich_problems_for_ui(open_problems, services, extra, user_or_role="viewer"):
    """Enrich masalah terbuka dengan aksi tombol (restart, log, mitigate, apt_update) untuk UI."""
    svc_map = {s.service_name: s for s in services}
    log_units = {"SYSLOG", "AUTH", "SYSTEM"}
    try:
        log_units |= set(json.loads(extra.units) or []) if extra and extra.units else set()
    except (TypeError, ValueError):
        pass
    sec = _parse_extras_security(extra)
    can_apt = False
    can_term = False
    if hasattr(user_or_role, "has_perm"):
        can_apt = user_or_role.has_perm("can_apt")
        can_term = (
            getattr(user_or_role, "is_master_admin", lambda: False)()
            or user_or_role.has_perm("can_users_sys")
            or user_or_role.has_perm("can_manage_servers")
            or user_or_role.has_perm("can_services")
        )
    elif isinstance(user_or_role, str):
        can_apt = user_or_role in ("admin", "master_admin")
        can_term = user_or_role in ("admin", "master_admin")

    for r in open_problems:
        if r["key"].startswith("service_down:"):
            sname = r["key"].split(":", 1)[1]
            svc = svc_map.get(sname)
            r["action"] = "restart" if svc else None
            r["svc_id"] = svc.id if svc else None
            r["log_unit"] = sname
        elif r["key"].startswith("svc_no_data:"):
            sname = r["key"].split(":", 1)[1]
            r["action"] = "log"
            r["log_unit"] = sname
        elif r["key"] in ("security_danger", "failed_logins"):
            r["action"] = "mitigate"
            r["log_unit"] = "AUTH"
            r["ip_count"] = len(sec.get("source_ips") or {})
        elif r["key"] == "agent_stale":
            r["action"] = None
        elif r["key"] == "agent_outdated":
            r["action"] = "agent_update_cmd"
        elif r["key"] == "apt_updates":
            r["action"] = "apt_update" if can_apt else None
        elif r["key"].startswith("ssh_active_session:"):
            r["action"] = "terminate_session" if can_term else "inspect_sessions"
            r["log_unit"] = "AUTH"
            # Format key: ssh_active_session:{u_name}:{clean_tty_key}:{clean_from_key}
            kparts = r["key"].split(":")
            if len(kparts) >= 3:
                r["session_user"] = kparts[1]
                r["tty"] = kparts[2].replace("_", "/")
        elif r["key"] == "platform_conflict":
            r["action"] = "reset_platform"
        elif r["key"].startswith("oom_kill:"):
            r["action"] = "log"
            proc = r["key"].split(":", 1)[1] if ":" in r["key"] else ""
            r["log_unit"] = f"{proc}.service" if proc else "SYSTEM"
        elif r["key"].startswith("disk_io_error:"):
            r["action"] = "log"
            r["log_unit"] = "SYSTEM"
        elif r["key"].startswith("segfault:"):
            r["action"] = "log"
            proc = r["key"].split(":", 1)[1] if ":" in r["key"] else ""
            r["log_unit"] = f"{proc}.service" if proc else "SYSTEM"
        elif r["key"] in ("kernel_panic", "hardware_error_mce"):
            r["action"] = "log"
            r["log_unit"] = "SYSTEM"
        else:
            r["action"] = None


def _serialize_problem_list(prob_list):
    """Konversi field datetime ke ISO string agar aman diserialisasikan ke JSON."""
    res = []
    for p in prob_list:
        d = dict(p)
        if isinstance(d.get("started_at"), datetime):
            d["started_at_str"] = _fmt_short_dt(d["started_at"])
            d["started_at_full"] = _fmt_dt(d["started_at"], with_sec=True)
        if isinstance(d.get("resolved_at"), datetime):
            d["resolved_at_str"] = _fmt_short_dt(d["resolved_at"])
            d["resolved_at_full"] = _fmt_dt(d["resolved_at"], with_sec=True)
        for k in ("started_at", "resolved_at", "acknowledged_at", "last_active_at", "ignored_until"):
            v = d.get(k)
            if isinstance(v, datetime):
                iso_str = v.isoformat()
                if not iso_str.endswith("Z") and not v.tzinfo:
                    iso_str += "Z"
                d[k] = iso_str
        if d.get("started_at"):
            d["started_at_iso"] = d["started_at"]
        res.append(d)
    return res


def sync_server_problems(db, srv, instances, keep_history=40, now=None):
    """Rekonsiliasi masalah dengan tabel server_problems (mirip evaluasi Zabbix).

    - Instance baru  -> insert terbuka (started_at=now, last_active_at).
    - Masih ada      -> perbarui severity/message/tip; majukan last_active_at.
    - Tidak ada lagi -> tandai resolved_at=now; untuk tipe berjendela-tenang,
      hanya bila sudah tenang >= jendela (resolved_note='auto').
    - Kejadian berbasis (keamanan): instans tertutup otomatis bila kejadian
      terakhir lebih tua dari jendela tenang (sisa data auth.log tidak macetkan banner).
    Arsip teratasi > 30 hari dihapus. Kembalikan (level, open, history).
    """
    now = now or datetime.utcnow()
    is_srv_maint = False
    maint_reason = None
    if getattr(srv, "is_maintenance", 0):
        m_until = getattr(srv, "maintenance_until", None)
        if m_until and m_until < now:
            srv.is_maintenance = 0
            srv.maintenance_until = None
            srv.maintenance_reason = None
            db.commit()
        else:
            is_srv_maint = True
            maint_reason = getattr(srv, "maintenance_reason", None) or "Mode Pemeliharaan Aktif"

    # Migrasi transparan key lama (ram_high/ram_critical, dll) ke key terpadu (ram_usage, dll)
    LEGACY_KEY_MAP = {
        "ram_high": "ram_usage",
        "ram_critical": "ram_usage",
        "cpu_high": "cpu_usage",
        "cpu_saturated": "cpu_usage",
        "swap_high": "swap_usage",
        "swap_critical": "swap_usage",
        "security_danger": "failed_logins",
    }
    open_legacy = (
        db.query(ServerProblem)
        .filter(ServerProblem.server_id == srv.id, ServerProblem.resolved_at.is_(None))
        .all()
    )
    for r in open_legacy:
        tgt_key = LEGACY_KEY_MAP.get(r.key)
        if not tgt_key:
            if r.key.startswith("disk_high:"):
                tgt_key = "disk_usage:" + r.key.split(":", 1)[1]
            elif r.key.startswith("disk_critical:"):
                tgt_key = "disk_usage:" + r.key.split(":", 1)[1]
        if tgt_key:
            dupe = next((x for x in open_legacy if x.key == tgt_key and x.id != r.id), None)
            if dupe:
                db.delete(r)
            else:
                r.key = tgt_key

    current_keys = {p["key"] for p in instances}

    svc_map = {}
    try:
        for s in db.query(Service).filter(Service.server_id == srv.id).all():
            s_mode = getattr(s, "ignore_mode", None)
            if getattr(s, "is_ignored", 0) and s_mode == "duration" and s.ignored_until and s.ignored_until <= now:
                s.is_ignored = 0
                s.ignored_until = None
                s.ignored_reason = None
                s.ignore_mode = None
            svc_map[s.service_name] = s
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    for p in instances:
        quiet = _quiet_secs_for(p["key"])
        ev = p.get("event_at")
        existing_rows = (
            db.query(ServerProblem).filter(
                ServerProblem.server_id == srv.id,
                ServerProblem.key == p["key"],
                ServerProblem.resolved_at.is_(None),
            ).order_by(ServerProblem.id.asc()).all()
        )
        row = existing_rows[0] if existing_rows else None
        if len(existing_rows) > 1:
            for extra in existing_rows[1:]:
                extra.resolved_at = now
                extra.resolved_note = "duplicate_cleanup"
        if quiet > 0 and ev is not None and (now - ev).total_seconds() >= quiet:
            # Sudah tenang melebihi jendela -> tutup otomatis (jangan buka baru).
            if row is not None:
                row.resolved_at = now
                row.updated_at = now
                row.resolved_note = "auto"
            continue
        active = max(ev, now) if ev else now

        svc_obj = None
        if p["key"].startswith("service_down:"):
            svc_name = p["key"].split(":", 1)[1]
            svc_obj = svc_map.get(svc_name)
        is_svc_ignored = bool(svc_obj and getattr(svc_obj, "is_ignored", 0))

        # Tentukan apakah insiden ini merupakan tindakan yang disengaja oleh operator
        target_ignored = 0
        target_ignored_until = None
        target_ignored_by = None
        target_ignored_reason = None
        target_ignore_mode = None

        is_operator_action = False
        operator_action_reason = None
        operator_action_by = None

        if is_srv_maint:
            # Mode Pemeliharaan aktif: tetap catat insiden sebagai masalah terbuka,
            # tetapi statusnya diabaikan sehingga tidak memicu alarm banner atau sirine kritis
            target_ignored = 1
            target_ignored_by = "Mode Pemeliharaan"
            target_ignored_reason = maint_reason
            target_ignore_mode = "duration" if srv.maintenance_until else "permanent"
            target_ignored_until = srv.maintenance_until
        elif p["key"] == "agent_stale":
            # Periksa apakah host dimatikan atau direboot melalui perintah resmi oleh operator
            host_cmd_cutoff = datetime.utcnow() - timedelta(minutes=30)
            last_cmd = (
                db.query(Command)
                .filter(
                    Command.server_id == srv.id,
                    Command.action.in_(["poweroff_host", "reboot_host"]),
                    Command.created_at >= host_cmd_cutoff,
                )
                .order_by(desc(Command.created_at))
                .first()
            )
            if last_cmd:
                cmd_time = last_cmd.created_at
                ls_time = srv.last_seen
                if ls_time and ls_time.tzinfo:
                    ls_time = ls_time.replace(tzinfo=None)
                # Jika poweroff/reboot dikirim dan sejak itu mesin belum melapor kembali
                if cmd_time and (ls_time is None or cmd_time >= ls_time - timedelta(seconds=60)):
                    is_operator_action = True
                    operator_action_by = (last_cmd.issued_by or "operator").upper()
                    if last_cmd.action == "reboot_host":
                        operator_action_reason = f"SERVER SEDANG DI-REBOOT OLEH OPERATOR ({operator_action_by})"
                    else:
                        operator_action_reason = f"SERVER DIMATIKAN OLEH OPERATOR ({operator_action_by})"
        elif is_svc_ignored:
            target_ignored = 1
            target_ignored_by = svc_obj.ignored_by
            target_ignored_reason = svc_obj.ignored_reason
            target_ignore_mode = getattr(svc_obj, "ignore_mode", "permanent") or "permanent"
            target_ignored_until = svc_obj.ignored_until
        elif svc_obj and svc_obj.ignored_reason and ("DIMATIKAN OLEH OPERATOR" in svc_obj.ignored_reason or "DIHENTIKAN OLEH OPERATOR" in svc_obj.ignored_reason):
            is_operator_action = True
            operator_action_by = (svc_obj.ignored_by or "operator")
            operator_action_reason = svc_obj.ignored_reason

        # Deteksi penghentian oleh operator dari pesan instans atau riwayat Command terkini
        if p["key"].startswith("service_down:"):
            p_msg_l = p.get("message", "").lower()
            if "dimatikan oleh operator" in p_msg_l or "dihentikan oleh operator" in p_msg_l:
                is_operator_action = True
                if not operator_action_reason:
                    operator_action_reason = p.get("message")
                if not operator_action_by:
                    operator_action_by = operator_action_reason.split("(")[-1].rstrip(")") if "(" in operator_action_reason else "operator"

            if not is_operator_action:
                s_name = p["key"].split(":", 1)[1].lower()
                try:
                    cmd_cutoff = datetime.utcnow() - timedelta(minutes=15)
                    recent_c = (
                        db.query(Command)
                        .filter(
                            Command.server_id == srv.id,
                            Command.action.in_(["stop", "start"]),
                            Command.created_at >= cmd_cutoff,
                        )
                        .order_by(desc(Command.id))
                        .limit(20)
                        .all()
                    )
                    for c in recent_c:
                        c_unit = None
                        if c.service_id and svc_obj and c.service_id == svc_obj.id:
                            c_unit = svc_obj.service_name
                        elif c.params:
                            try:
                                cp = json.loads(c.params) if isinstance(c.params, str) else c.params
                                c_unit = cp.get("service_name") or cp.get("unit") or cp.get("process_name")
                            except Exception:
                                pass
                        if c_unit:
                            c_cl = (c_unit[:-8] if c_unit.endswith(".service") else c_unit).lower()
                            if c_cl == s_name:
                                if c.action == "stop" and c.status in ("pending", "executing", "success"):
                                    is_operator_action = True
                                    operator_action_by = c.issued_by or "operator"
                                    operator_action_reason = f"LAYANAN DIMATIKAN OLEH OPERATOR ({operator_action_by})"
                                break
                except Exception:
                    pass

        if row and row.ignored_reason and ("DIMATIKAN OLEH OPERATOR" in row.ignored_reason or "DIHENTIKAN OLEH OPERATOR" in row.ignored_reason or "DI-REBOOT OLEH OPERATOR" in row.ignored_reason):
            is_operator_action = True
            if not operator_action_reason:
                operator_action_reason = row.ignored_reason
            if not operator_action_by:
                operator_action_by = row.ignored_by

        if row and ("dimatikan oleh operator" in (row.message or "").lower() or "dihentikan oleh operator" in (row.message or "").lower() or "di-reboot oleh operator" in (row.message or "").lower()):
            is_operator_action = True
            if not operator_action_reason:
                operator_action_reason = row.message
            if not operator_action_by and "(" in (row.message or ""):
                operator_action_by = row.message.split("(")[-1].rstrip(")")

        if row is None:
            start_time = ev if (ev and (p["key"] == "agent_stale" or "_usage" in p["key"] or p["key"] == "failed_logins")) else now
            new_row = ServerProblem(
                server_id=srv.id, key=p["key"], severity=p["severity"],
                message=p["message"], tip=p["tip"], started_at=start_time,
                last_active_at=active,
                context=p.get("context"),
            )
            if target_ignored:
                new_row.is_ignored = 1
                new_row.ignored_until = target_ignored_until
                new_row.ignored_by = target_ignored_by
                new_row.ignored_reason = target_ignored_reason
                new_row.ignore_mode = target_ignore_mode
                new_row.acknowledged_at = now
                new_row.acknowledged_by = target_ignored_by or "operator"
            elif is_operator_action:
                new_row.severity = "warning"
                new_row.is_ignored = 1
                new_row.ignored_until = None
                new_row.ignored_by = operator_action_by
                new_row.ignored_reason = operator_action_reason
                new_row.ignore_mode = "permanent"
                new_row.acknowledged_at = now
                new_row.acknowledged_by = operator_action_by or "operator"
            else:
                # 2. Cek riwayat ServerProblem sebelumnya untuk key ini (termasuk non-service atau flappy)
                lookup_keys = [p["key"]]
                tgt_k = LEGACY_KEY_MAP.get(p["key"])
                if not tgt_k:
                    if p["key"].startswith("disk_high:"):
                        tgt_k = "disk_usage:" + p["key"].split(":", 1)[1]
                    elif p["key"].startswith("disk_critical:"):
                        tgt_k = "disk_usage:" + p["key"].split(":", 1)[1]
                if tgt_k:
                    lookup_keys.append(tgt_k)
                prev_prob = (
                    db.query(ServerProblem)
                    .filter(
                        ServerProblem.server_id == srv.id,
                        ServerProblem.key.in_(lookup_keys),
                        ServerProblem.is_ignored == 1,
                    )
                    .order_by(desc(ServerProblem.updated_at))
                    .first()
                )
                if prev_prob:
                    prev_mode = getattr(prev_prob, "ignore_mode", None)
                    if prev_mode == "permanent" or (prev_mode is None and prev_prob.ignored_until is None):
                        new_row.is_ignored = 1
                        new_row.ignore_mode = "permanent"
                        new_row.ignored_until = None
                        new_row.ignored_by = prev_prob.ignored_by
                        new_row.ignored_reason = prev_prob.ignored_reason
                        new_row.acknowledged_at = now
                        new_row.acknowledged_by = prev_prob.ignored_by or "operator"
                    elif prev_mode == "duration" and prev_prob.ignored_until and prev_prob.ignored_until > now:
                        new_row.is_ignored = 1
                        new_row.ignore_mode = "duration"
                        new_row.ignored_until = prev_prob.ignored_until
                        new_row.ignored_by = prev_prob.ignored_by
                        new_row.ignored_reason = prev_prob.ignored_reason
                        new_row.acknowledged_at = now
                        new_row.acknowledged_by = prev_prob.ignored_by or "operator"

            db.add(new_row)
            try:
                audit_status = "diabaikan" if new_row.is_ignored else "aktif"
                _audit(db, "sistem", f"masalah_{new_row.severity}", f"{srv.hostname}: terdeteksi [{new_row.severity.upper()}] {new_row.message}", audit_status, server_id=srv.id)
            except Exception:
                pass
        else:
            if getattr(row, "is_ignored", 0) and getattr(row, "ignore_mode", None) == "duration" and row.ignored_until and row.ignored_until <= now:
                row.is_ignored = 0
                row.ignored_until = None
                row.ignored_reason = operator_action_reason if is_operator_action else None
                row.ignore_mode = None
            elif getattr(row, "is_ignored", 0) and getattr(row, "ignored_by", None) == "Mode Pemeliharaan" and not is_srv_maint:
                row.is_ignored = 0
                row.ignored_until = None
                row.ignored_by = None
                row.ignored_reason = operator_action_reason if is_operator_action else None
                row.ignore_mode = None
            elif target_ignored:
                row.is_ignored = 1
                row.ignored_until = target_ignored_until
                row.ignored_by = target_ignored_by
                row.ignored_reason = target_ignored_reason
                row.ignore_mode = target_ignore_mode
                row.acknowledged_at = row.acknowledged_at or now
                row.acknowledged_by = row.acknowledged_by or target_ignored_by or "operator"
            elif is_operator_action:
                row.severity = "warning"
                # Hanya pertahankan pengabaian jika row memang sedang berstatus diabaikan.
                # Jangan pernah memaksa kembali is_ignored = 1 jika operator sudah mencabut pengabaiannya (is_ignored == 0).
                if getattr(row, "is_ignored", 0) == 1:
                    row.is_ignored = 1
                    row.ignore_mode = getattr(row, "ignore_mode", "permanent") or "permanent"
                    if not row.ignored_reason:
                        row.ignored_reason = operator_action_reason
                    if not row.ignored_by:
                        row.ignored_by = operator_action_by
                    row.acknowledged_at = row.acknowledged_at or now
                    row.acknowledged_by = row.acknowledged_by or operator_action_by or "operator"

            if p["key"] == "agent_stale" and ev and (row.started_at > ev):
                row.started_at = ev

            if active > (row.last_active_at or row.started_at):
                row.last_active_at = active
            incoming_sev = "warning" if is_operator_action else p["severity"]
            if (row.severity != incoming_sev or row.message != p["message"]
                    or row.tip != p["tip"]):
                old_sev = row.severity
                new_sev = incoming_sev
                row.severity, row.message, row.tip = incoming_sev, p["message"], p["tip"]
                if old_sev != new_sev:
                    try:
                        _audit(db, "sistem", "eskalasi_insiden",
                               f"{srv.hostname}: eskalasi keparahan [{old_sev.upper()} → {new_sev.upper()}] — {p['message']}",
                               "eskalasi", server_id=srv.id)
                    except Exception:
                        pass
            if p.get("context") and (not row.context or p["severity"] in ("average", "danger")):
                row.context = p.get("context")
            row.updated_at = now

    for row in (
        db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).all()
    ):
        if row.key in current_keys or row.key.startswith("probe_failed:") or row.probe_id is not None:
            continue

        # Jika masalah terkait layanan yang sudah dihapus/tidak ada lagi di daftar pantau server
        if row.key.startswith("service_down:") or row.key.startswith("svc_no_data:"):
            svc_name = row.key.split(":", 1)[1]
            if svc_name not in svc_map:
                # Layanan telah dihapus: bersihkan row problem seketika tanpa jeda 60s
                # dan JANGAN catat audit 'masalah_selesai' (karena layanan sengaja dihapus)
                db.delete(row)
                continue

        quiet = _quiet_secs_for(row.key)
        last = row.last_active_at or row.started_at
        if quiet <= 0 or (now - last).total_seconds() >= quiet:
            row.resolved_at = now
            row.updated_at = now
            if _server_stale(srv) and (row.key.startswith("service_down:") or row.key.startswith("svc_no_data:")):
                row.resolved_note = "server_offline"
            elif row.key == "agent_stale":
                row.resolved_note = "server_online"
            elif row.key.startswith("service_down:"):
                row.resolved_note = "service_up"
            elif row.key.startswith("ssh_active_session:"):
                row.resolved_note = "session_closed"
            else:
                row.resolved_note = "auto" if quiet > 0 else "resolved"
            if row.key == "agent_stale":
                audit_msg = f"{srv.hostname}: server kembali online dan aktif melapor"
                audit_res = "online"
            elif row.key.startswith("ssh_active_session:"):
                audit_msg = f"{srv.hostname}: sesi remote SSH telah ditutup ({row.message})"
                audit_res = "selesai"
            elif _server_stale(srv):
                audit_msg = f"{srv.hostname}: insiden '{row.message}' ditutup karena server offline"
                audit_res = "offline"
            else:
                audit_msg = f"{srv.hostname}: insiden '{row.message}' telah selesai"
                audit_res = "selesai"
            try:
                _audit(db, "sistem", "masalah_selesai", audit_msg, audit_res, server_id=srv.id)
            except Exception:
                pass

            if row.key.startswith("service_down:"):
                svc_name = row.key.split(":", 1)[1]
                svc_obj = svc_map.get(svc_name)
                if svc_obj:
                    svc_mode = getattr(svc_obj, "ignore_mode", None)
                    if svc_mode == "incident":
                        # Mode insiden: hanya untuk satu kejadian, reset saat layanan kembali normal
                        svc_obj.is_ignored = 0
                        svc_obj.ignored_until = None
                        svc_obj.ignored_reason = None
                        svc_obj.ignore_mode = None
                    elif svc_mode == "duration":
                        # Mode durasi: jika batas waktu telah lewat, kembalikan ke pemantauan normal
                        if not (svc_obj.ignored_until and svc_obj.ignored_until > now):
                            svc_obj.is_ignored = 0
                            svc_obj.ignored_until = None
                            svc_obj.ignored_reason = None
                            svc_obj.ignore_mode = None
                    elif svc_mode == "permanent":
                        # Mode permanen: TETAP diabaikan (is_ignored = 1), tidak di-reset saat layanan pulih!
                        pass
                    else:
                        if svc_obj.ignored_until and svc_obj.ignored_until <= now:
                            svc_obj.is_ignored = 0
                            svc_obj.ignored_until = None
                            svc_obj.ignored_reason = None
                            svc_obj.ignore_mode = None

    stale = now - timedelta(days=30)
    db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.resolved_at.isnot(None),
        ServerProblem.resolved_at < stale,
        (ServerProblem.is_ignored == 0) | (ServerProblem.is_ignored.is_(None)) | (ServerProblem.ignore_mode != "permanent"),
    ).delete(synchronize_session=False)
    db.commit()  # Simpan pembaruan status problem ke database agar ID valid saat di-ack/resolve

    open_rows = (
        db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).order_by(desc(ServerProblem.started_at)).all()
    )
    history = (
        db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.isnot(None),
        ).order_by(desc(ServerProblem.resolved_at)).limit(keep_history).all()
    )
    active_unignored = [r for r in open_rows if not getattr(r, "is_ignored", 0)]
    level = "ok"
    if active_unignored:
        level = max((r.severity for r in active_unignored),
                    key=lambda x: PROBLEM_RANK.get(x, 0))
    cutoff_24 = now - timedelta(hours=24)
    counts: dict = {}
    for r in db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.started_at >= cutoff_24,
    ).all():
        counts[r.key] = counts.get(r.key, 0) + 1
    open_list = [_problem_row2dict(r) for r in open_rows]
    hist_list = [_problem_row2dict(r) for r in history]
    for d in open_list + hist_list:
        d["count_24h"] = counts.get(d["key"], 0)
    return level, open_list, hist_list


def _agg_row(srv, row, counts=None) -> dict:
    d = _problem_row2dict(row)
    s_tier = getattr(srv, "tier", 2) or 2
    eff_sev = d.get("severity", "warning")
    if s_tier != 1 and eff_sev in ("danger", "average"):
        eff_sev = "warning"
    d.update({
        "server_id": srv.id,
        "hostname": srv.hostname,
        "group_name": getattr(srv, "group_name", None) or None,
        "tier": s_tier,
        "severity": eff_sev,
        "tags": getattr(srv, "tags", "") or "",
        "is_offline": (srv.last_seen is None) or _server_stale(srv),
        "ip_address": getattr(srv, "ip_address", "") or "",
    })
    if counts:
        d["count_24h"] = counts.get(row.key, 0)
    return d


def problems_aggregate(
    db,
    res_period: str = "24h",
    res_start: str | None = None,
    res_end: str | None = None,
    res_server: int | None = None,
    res_sev: str | None = None,
    res_type: str | None = None,
    res_q: str | None = None,
    res_limit: int = 500,
):
    """Daftar masalah semua server untuk halaman /problems.

    Kembalikan (open_list, recent_resolved), urut severity lalu waktu.
    """
    extras_map = {e.server_id: e for e in db.query(ServerExtras).all()}
    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    now_utc = datetime.utcnow()
    cutoff_24 = now_utc - timedelta(hours=24)

    p_clean = (res_period or "24h").strip().lower()
    res_cutoff_end = None
    if res_start or res_end:
        p_clean = "custom"
        if res_start:
            try:
                res_cutoff = datetime.strptime(res_start.strip(), "%Y-%m-%d")
            except Exception:
                res_cutoff = cutoff_24
        else:
            res_cutoff = datetime(2020, 1, 1)
        if res_end:
            try:
                res_cutoff_end = datetime.strptime(res_end.strip(), "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            except Exception:
                res_cutoff_end = None
    elif p_clean == "today":
        res_cutoff = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    elif p_clean == "7d":
        res_cutoff = now_utc - timedelta(days=7)
    elif p_clean == "30d":
        res_cutoff = now_utc - timedelta(days=30)
    else:
        res_cutoff = cutoff_24

    open_list: list = []
    resolved_list: list = []
    for srv in servers:
        ex = extras_map.get(srv.id)
        services = db.query(Service).filter(Service.server_id == srv.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        svc_data = []
        for svc in services:
            latest = latest_map.get(svc.id)
            svc_data.append({"name": svc.service_name,
                             "status": latest.status if latest else "unknown",
                             "port": svc.port,
                             "proc": svc.process_name,
                             "is_core": bool(getattr(svc, "is_core", 1))})
        if _server_stale(srv):
            for d in svc_data:
                d["status"] = "offline"
        sync_server_problems(db, srv, _problem_instances(srv, ex, svc_data, db))
        counts = {}
        for r in db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.started_at >= cutoff_24,
        ).all():
            counts[r.key] = counts.get(r.key, 0) + 1
        seen_open_keys = set()
        for r in db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).order_by(ServerProblem.id.desc()).all():
            if r.key in seen_open_keys:
                continue
            seen_open_keys.add(r.key)
            open_list.append(_agg_row(srv, r, counts))

    # Masukkan open problems dari Synthetic Probing mandiri (tanpa server_id)
    standalone_open = db.query(ServerProblem).filter(
        ServerProblem.server_id.is_(None),
        ServerProblem.probe_id.isnot(None),
        ServerProblem.resolved_at.is_(None),
    ).all()
    probes_map = {p.id: p for p in db.query(ProbeTarget).all()}
    if standalone_open:
        for r in standalone_open:
            prb = probes_map.get(r.probe_id)
            prb_name = prb.name if prb else f"Probe #{r.probe_id}"
            prb_tier = getattr(prb, "tier", 2) or 2 if prb else 2
            d = _problem_row2dict(r)
            eff_sev = d.get("severity", "warning")
            if prb_tier != 1 and eff_sev in ("danger", "average"):
                eff_sev = "warning"
            d.update({
                "server_id": None,
                "hostname": prb_name,
                "group_name": "Probing",
                "tier": prb_tier,
                "severity": eff_sev,
                "tags": prb.probe_type if prb else "probe",
                "count_24h": 1,
            })
            open_list.append(d)

    # Riwayat insiden teratasi terpadu (Kinerja Tinggi & Skalabilitas NOC)
    q_res = db.query(ServerProblem).filter(
        ServerProblem.resolved_at.isnot(None),
        ServerProblem.resolved_at >= res_cutoff,
    )
    if res_cutoff_end:
        q_res = q_res.filter(ServerProblem.resolved_at <= res_cutoff_end)
    if res_server:
        q_res = q_res.filter(ServerProblem.server_id == res_server)
    if res_sev:
        q_res = q_res.filter(ServerProblem.severity == res_sev)

    servers_map = {s.id: s for s in servers}
    resolved_rows = q_res.order_by(ServerProblem.resolved_at.desc()).limit(res_limit).all()
    for r in resolved_rows:
        if r.server_id and r.server_id in servers_map:
            resolved_list.append(_agg_row(servers_map[r.server_id], r))
        elif r.probe_id and r.probe_id in probes_map:
            prb = probes_map[r.probe_id]
            prb_name = prb.name if prb else f"Probe #{r.probe_id}"
            prb_tier = getattr(prb, "tier", 2) or 2 if prb else 2
            d = _problem_row2dict(r)
            eff_sev = d.get("severity", "warning")
            if prb_tier != 1 and eff_sev in ("danger", "average"):
                eff_sev = "warning"
            d.update({
                "server_id": None,
                "hostname": prb_name,
                "group_name": "Probing",
                "tier": prb_tier,
                "severity": eff_sev,
                "tags": prb.probe_type if prb else "probe",
                "count_24h": 1,
            })
            resolved_list.append(d)

    # Filter kriteria tambahan pada recent_resolved
    if res_type:
        resolved_list = [p for p in resolved_list if p.get("res_type") == res_type]
    if res_q:
        q_lower = res_q.strip().lower()
        resolved_list = [
            p for p in resolved_list
            if q_lower in f"{p.get('hostname','')} {p.get('message','')} {p.get('component','')} {p.get('res_label','')} {p.get('group_name','')}".lower()
        ]

    rank = {"danger": 4, "average": 3, "warning": 2, "info": 1}
    open_list.sort(key=lambda r: (rank.get(r["severity"], 0), r["started_at"]),
                   reverse=True)
    resolved_list.sort(key=lambda r: r["resolved_at"], reverse=True)
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return open_list, resolved_list




def _alert_dict(row, hostname: str, now: datetime) -> dict:
    ctx = row.context
    if isinstance(ctx, str) and ctx:
        try:
            ctx = json.loads(ctx)
        except Exception:
            pass
    s_iso = row.started_at.isoformat()
    if not s_iso.endswith("Z"):
        s_iso += "Z"
    ack_user = getattr(row, "acknowledged_by", None)
    disp_ack = "master-admin" if ack_user == "admin" else ack_user
    return {
        "id": row.id,
        "server_id": row.server_id,
        "hostname": hostname,
        "key": row.key,
        "severity": row.severity,
        "message": row.message,
        "tip": row.tip,
        "started_at": s_iso,
        "durasi": _fmt_duration(row.started_at, now),
        "acknowledged": row.acknowledged_at is not None,
        "acknowledged_by": disp_ack,
        "context": ctx,
        "is_ignored": bool(getattr(row, "is_ignored", 0)),
        "ignore_mode": getattr(row, "ignore_mode", None),
        "ignored_until": row.ignored_until.isoformat() if getattr(row, "ignored_until", None) else None,
        "ignored_by": ("master-admin" if getattr(row, "ignored_by", None) == "admin" else getattr(row, "ignored_by", None)),
        "ignored_reason": getattr(row, "ignored_reason", None),
    }




def _problem_bg_loop() -> None:
    while True:
        time.sleep(BG_PROBLEM_EVAL_SECS)
        try:
            with SessionLocal() as sess:
                _evaluate_maintenance_windows(sess)
                problems_aggregate(sess)
        except Exception as exc:  # noqa: BLE001 -- jangan matikan thread
            print(f"[bg-problems] error: {exc}", flush=True)


# Retensi data: bersihkan sesi/login-attempt/riwayat yang sudah terlalu tua
# setiap jam supaya tabel tidak bertumbuh tanpa batas (disk + query lambat).
_RETENTION_LIMITS = {
    "login_attempts_days": 1,
    "audit_logs_days": 365,
    "commands_days": 180,      # hanya status sukses/gagal (bukan yang berjalan)
    "log_requests_days": 30,   # hanya yang sudah selesai
    "resolved_problems_days": 90, # masalah yang sudah terselesaikan lampau
}


def _retention_prune(db: Session) -> None:
    now = datetime.utcnow()
    _prune_expired_sessions(db)
    db.query(LoginAttempt).filter(
        LoginAttempt.updated_at < now - timedelta(days=_RETENTION_LIMITS["login_attempts_days"])
    ).delete(synchronize_session=False)
    db.query(AuditLog).filter(
        AuditLog.created_at < now - timedelta(days=_RETENTION_LIMITS["audit_logs_days"])
    ).delete(synchronize_session=False)
    db.query(Command).filter(
        Command.status.in_(["success", "failed"]),
        Command.created_at < now - timedelta(days=_RETENTION_LIMITS["commands_days"]),
    ).delete(synchronize_session=False)
    db.query(LogRequest).filter(
        LogRequest.status.in_(["success", "failed"]),
        LogRequest.updated_at < now - timedelta(days=_RETENTION_LIMITS["log_requests_days"]),
    ).delete(synchronize_session=False)
    db.query(ServerProblem).filter(
        ServerProblem.resolved_at.isnot(None),
        ServerProblem.resolved_at < now - timedelta(days=_RETENTION_LIMITS["resolved_problems_days"]),
    ).delete(synchronize_session=False)
    db.commit()


def _retention_loop() -> None:
    while True:
        time.sleep(3600)  # tiap jam
        try:
            with SessionLocal() as sess:
                _retention_prune(sess)
        except Exception as exc:  # noqa: BLE001 -- jangan matikan thread
            logger.error("[retention] error: %s", exc)
