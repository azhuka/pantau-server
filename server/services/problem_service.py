import json
import re
from datetime import datetime
from sqlalchemy.orm import Session
from models.server import Server
from models.problem import ServerProblem
from models.misc import AuditLog, SystemSetting

# Ambang batas masalah default (Bawaan Pabrik)
DEFAULT_THRESHOLDS = {
    "cpu_warn": 85.0,
    "cpu_average": 90.0,
    "cpu_danger": 95.0,
    "ram_warn": 85.0,
    "ram_average": 90.0,
    "ram_danger": 95.0,
    "disk_warn": 90.0,
    "disk_average": 92.5,
    "disk_danger": 95.0,
    "swap_warn": 80.0,
    "swap_average": 86.0,
    "swap_danger": 92.0,
    "ssh_fail_warn": 5,
    "ssh_fail_danger": 10,
}

_RETENTION_LIMITS = {
    "login_attempts_days": 1,
    "audit_logs_days": 365,
    "commands_days": 180,
    "log_requests_days": 30,
    "resolved_problems_days": 30,
}


def get_global_thresholds(db: Session) -> dict:
    """Ambil ambang batas global dari tabel system_settings (fallback ke DEFAULT_THRESHOLDS)."""
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
    except Exception:
        pass
    return dict(DEFAULT_THRESHOLDS)

# Daftar layanan krusial yang dipantau status kegagalannya
CRITICAL_SERVICES = {
    "nginx", "mariadb", "mysql", "sshd", "cloudflared", "docker",
    "redis", "postgresql", "apache2", "caddy", "php-fpm", "systemd-resolved"
}


def check_server_stale(db: Session, srv: Server, now: datetime = None):
    """
    Evaluasi apakah node server klien mati / tidak melapor (agent_stale).
    - Tier 1 (Produksi): >= 60s critical (gawat), >= 180s danger (bahaya/lumpuh).
    - Tier 2 (Non-Produksi): warning (peringatan non-eskalasi).
    """
    if now is None:
        now = datetime.utcnow()

    # Redam jika sedang dalam mode pemeliharaan aktif
    if getattr(srv, "is_maintenance", 0):
        m_until = getattr(srv, "maintenance_until", None)
        if m_until and m_until < now:
            srv.is_maintenance = 0
            srv.maintenance_until = None
            srv.maintenance_reason = None
            db.commit()
        else:
            return

    sec_silent = (now - srv.last_seen).total_seconds() if srv.last_seen else 999999.0
    is_prod = (getattr(srv, "tier", 1) == 1)

    existing_stale = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "agent_stale",
        ServerProblem.resolved_at == None
    ).first()

    if sec_silent >= 60.0:
        dur_mins = max(1, int(sec_silent // 60))
        dur_txt = f"{dur_mins} mnt"

        if is_prod:
            if sec_silent >= 180.0:
                sev = "danger"
                msg = f"Agen tidak melapor (> {dur_txt}) — SERVER OFFLINE"
                tip = "Periksa suplai daya, virtualisasi/mesin fisik, dan konektivitas jaringan server Produksi."
            else:
                sev = "critical"
                msg = f"Agen tidak melapor (> {dur_txt})"
                tip = "Layanan vital terganggu. Periksa daemon pantau-agent atau konektivitas jaringan."
        else:
            sev = "warning"
            msg = f"Agen tidak melapor (> {dur_txt})"
            tip = "Server non-produksi (lab/pengujian) sedang tidak aktif atau pantau-agent belum berjalan."

        if existing_stale:
            existing_stale.severity = sev
            existing_stale.message = msg
            existing_stale.tip = tip
            existing_stale.updated_at = now
            existing_stale.last_active_at = now
        else:
            new_prob = ServerProblem(
                server_id=srv.id,
                key="agent_stale",
                severity=sev,
                message=msg,
                tip=tip,
                started_at=now,
                updated_at=now,
                last_active_at=now
            )
            db.add(new_prob)
            db.flush()

            audit = AuditLog(
                server_id=srv.id,
                username="sistem",
                action="masalah_terdeteksi",
                target="agent_stale",
                result="terdeteksi",
                meta=f"{srv.hostname}: {msg}",
                created_at=now
            )
            db.add(audit)
        db.commit()
    else:
        # Server pulih dan melapor normal
        if existing_stale:
            existing_stale.resolved_at = now
            existing_stale.updated_at = now
            existing_stale.resolved_note = "server_online"

            audit = AuditLog(
                server_id=srv.id,
                username="sistem",
                action="masalah_selesai",
                target="agent_stale",
                result="selesai",
                meta=f"{srv.hostname}: node kembali online dan melapor normal",
                created_at=now
            )
            db.add(audit)
            db.commit()


def check_all_servers_stale(db: Session):
    """Memeriksa status online/stale seluruh server armada secara berkala."""
    now = datetime.utcnow()
    servers = db.query(Server).filter(Server.is_active == 1).all()
    for srv in servers:
        try:
            check_server_stale(db, srv, now=now)
        except Exception:
            pass


def evaluate_server_problems(db: Session, srv: Server, report_dict: dict, extras):
    """
    Evaluasi kesehatan server dan sinkronisasi tiket insiden di server_problems.
    Tunduk pada Glosarium Baku 4-Tingkat Keparahan:
      - info (biru): pembaruan sistem / update paket OS (non-ancaman).
      - warning (kuning): potensi gangguan, layanan utama tetap jalan (remote SSH legal, utilisasi tinggi non-prod).
      - critical (oranye pekat): layanan utama terganggu / mati (nginx down, mysql down, SSH ilegal).
      - danger (merah): kelumpuhan sistem utama (server offline, filesystem read-only, RAM/CPU habis pada produksi).
    """
    now = datetime.utcnow()

    # 1. Mode Pemeliharaan (Maintenance Mode Auto-Expiry & Alert Suppression)
    if getattr(srv, "is_maintenance", 0):
        m_until = getattr(srv, "maintenance_until", None)
        if m_until and m_until < now:
            srv.is_maintenance = 0
            srv.maintenance_until = None
            srv.maintenance_reason = None
            db.commit()
        else:
            return

    # Pastikan tiket agent_stale tertutup karena agen baru saja melapor
    existing_stale = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "agent_stale",
        ServerProblem.resolved_at == None
    ).first()
    if existing_stale:
        existing_stale.resolved_at = now
        existing_stale.updated_at = now
        existing_stale.resolved_note = "server_online"

    active_keys = set()
    active_instances = []
    is_prod = (getattr(srv, "tier", 1) == 1)

    # 2. Evaluasi Pembaruan Paket OS (info = Biru Baku)
    apt_up = getattr(extras, "apt_upgradable", 0) or 0
    if not apt_up and isinstance(report_dict.get("apt"), dict):
        apt_up = int(report_dict["apt"].get("upgradable") or 0)

    if apt_up > 0:
        k = "apt_updates"
        active_keys.add(k)
        active_keys.add("pkg_updates")
        active_instances.append({
            "key": k,
            "severity": "info",
            "message": f"{apt_up} paket pembaruan sistem OS tersedia",
            "tip": "Pembaruan paket keamanan atau versi baru tersedia. Jalankan 'apt update && apt upgrade' saat jendela pemeliharaan.",
            "context": json.dumps({"upgradable_count": apt_up}, ensure_ascii=False)
        })

    # 3. Evaluasi Sesi Remote SSH Aktif (ssh_active_session)
    accounts = report_dict.get("accounts")
    if isinstance(accounts, str):
        try:
            accounts = json.loads(accounts)
        except Exception:
            accounts = []

    if isinstance(accounts, list):
        for acc in accounts:
            if not isinstance(acc, dict):
                continue
            u_name = str(acc.get("user") or "unknown").strip()
            if u_name == "pantau":
                continue

            sessions = acc.get("sessions") or []
            for s in sessions:
                if not isinstance(s, dict):
                    continue
                raw_from = str(s.get("from") or "").strip().strip("()")
                r_tty = str(s.get("tty") or "").strip()
                r_time = str(s.get("time") or "").strip()

                if raw_from and not raw_from.startswith(":") and not raw_from.lower().startswith("local"):
                    clean_tty_key = r_tty.replace("/", "_") if r_tty else "ssh"
                    clean_from_key = re.sub(r"[^a-zA-Z0-9_\.:-]", "_", raw_from)
                    sess_key = f"ssh_active_session:{u_name}:{clean_tty_key}:{clean_from_key}"[:150]
                    active_keys.add(sess_key)

                    tty_disp = f" ({r_tty})" if r_tty else ""
                    time_disp = f" sejak {r_time}" if r_time else ""

                    # User legal = warning (kuning); User root langsung via SSH atau asing = critical (oranye pekat)
                    is_suspicious = (u_name == "root" or u_name.startswith("tmp_"))
                    sev = "critical" if is_suspicious else "warning"

                    context_data = {
                        "diagnosa": "Sesi Remote SSH Sedang Berlangsung",
                        "diagnosa_en": "Active Remote SSH Session in Progress",
                        "penyebab": f"Pengguna '{u_name}' terhubung ke server melalui koneksi remote SSH dari alamat IP {raw_from}{tty_disp}.",
                        "penyebab_en": f"User '{u_name}' connected to the client server via remote SSH from {raw_from}{tty_disp}.",
                        "dampak": "Aktivitas administratif sedang berlangsung di server target.",
                        "dampak_en": "Administrative operational session in progress on target server.",
                        "data_teknis": {
                            "user": u_name,
                            "source_ip": raw_from,
                            "tty": r_tty,
                            "login_time": r_time,
                        },
                        "rekomendasi": [
                            "Pantau aktivitas pengguna melalui tab Accounts / Riwayat Aksi.",
                            "Gunakan tombol 'Putus Sesi' untuk memutuskan koneksi paksa jika ini sesi tidak sah."
                        ]
                    }

                    active_instances.append({
                        "key": sess_key,
                        "severity": sev,
                        "message": f"Sesi remote SSH aktif: user '{u_name}' dari {raw_from}{tty_disp}",
                        "tip": f"Pengguna '{u_name}' sedang aktif terhubung ke server klien via remote SSH dari {raw_from}{tty_disp}{time_disp}.",
                        "context": json.dumps(context_data, ensure_ascii=False)
                    })

    # 4. Evaluasi Layanan Krusial Down / Failed (service_down:{name})
    units_raw = report_dict.get("units") or report_dict.get("services") or report_dict.get("systemd_units")
    if isinstance(units_raw, str):
        try:
            units_raw = json.loads(units_raw)
        except Exception:
            units_raw = []

    if isinstance(units_raw, list):
        for u in units_raw:
            if not isinstance(u, dict):
                continue
            svc_name = str(u.get("name") or "").replace(".service", "").strip().lower()
            if not svc_name:
                continue

            active_state = str(u.get("active") or "").strip().lower()
            sub_state = str(u.get("sub") or "").strip().lower()

            # Deteksi service yang mengalami kegagalan fisik
            is_failed = (active_state == "failed" or sub_state == "failed")
            # Jika ini layanan vital utama dan statusnya mati/failed
            if is_failed and (svc_name in CRITICAL_SERVICES or u.get("monitored")):
                k = f"service_down:{svc_name}"
                active_keys.add(k)
                sev = "critical" if is_prod else "warning"

                active_instances.append({
                    "key": k,
                    "severity": sev,
                    "message": f"Service {svc_name} Down / Gagal Beroperasi",
                    "tip": f"Layanan krusial '{svc_name}' terhenti (state: {active_state}/{sub_state}). Lakukan restart service atau inspeksi log systemd.",
                    "context": json.dumps({
                        "service": svc_name,
                        "active": active_state,
                        "sub": sub_state,
                        "description": u.get("description", "")
                    }, ensure_ascii=False)
                })

    # 5. Evaluasi Metrik Sumber Daya (CPU / RAM / Disk)
    sysd = report_dict.get("system") if isinstance(report_dict.get("system"), dict) else report_dict

    # 5a. CPU
    cpu_val = float(sysd.get("cpu") or report_dict.get("cpu") or 0.0)
    if cpu_val >= 95.0:
        k = "cpu_critical"
        active_keys.add(k)
        active_instances.append({
            "key": k,
            "severity": "danger" if is_prod else "warning",
            "message": f"Utilisasi CPU sangat kritis: {cpu_val:.1f}%",
            "tip": "Beban CPU mendekati batas maksimum 100%. Periksa proses yang mengonsumsi CPU tinggi.",
            "context": None
        })
    elif cpu_val >= 85.0:
        k = "cpu_high"
        active_keys.add(k)
        active_instances.append({
            "key": k,
            "severity": "warning",
            "message": f"Utilisasi CPU tinggi: {cpu_val:.1f}%",
            "tip": "Utilisasi CPU melampaui batas ambang normal 85%.",
            "context": None
        })

    # 5b. RAM
    mem_total = int(sysd.get("mem_total") or (report_dict.get("mem") or {}).get("total") or 0)
    mem_used = int(sysd.get("mem_used") or (report_dict.get("mem") or {}).get("used") or 0)
    if mem_total > 0:
        mem_pct = (mem_used / mem_total) * 100.0
        if mem_pct >= 95.0:
            k = "ram_danger"
            active_keys.add(k)
            active_instances.append({
                "key": k,
                "severity": "danger" if is_prod else "warning",
                "message": f"Alokasi RAM kritis: {mem_pct:.1f}%",
                "tip": "Ketersediaan memori fisik hampir habis. Waspadai pemanggilan kernel OOM Killer.",
                "context": None
            })
        elif mem_pct >= 85.0:
            k = "ram_warning"
            active_keys.add(k)
            active_instances.append({
                "key": k,
                "severity": "warning",
                "message": f"Alokasi RAM tinggi: {mem_pct:.1f}%",
                "tip": "Pemakaian RAM melampaui ambang normal 85%.",
                "context": None
            })

    # 5c. Disk Partitions
    disks_raw = sysd.get("disks") if sysd.get("disks") is not None else report_dict.get("disk")
    if isinstance(disks_raw, list):
        for d in disks_raw:
            if not isinstance(d, dict):
                continue
            mount = d.get("mount") or d.get("mounted_on") or "/"
            pct = float(d.get("pct") or d.get("used_percent") or d.get("percent") or 0.0)
            is_ro = bool(d.get("is_ro"))

            if is_ro and mount == "/":
                k = "disk_ro_root"
                active_keys.add(k)
                active_instances.append({
                    "key": k,
                    "severity": "danger",
                    "message": "Filesystem root (/) beralih ke mode Read-Only",
                    "tip": "Bahaya integritas sistem! Kernel mengunci penyimpanan ke read-only untuk mencegah korupsi data.",
                    "context": None
                })
            elif pct >= 95.0:
                k = f"disk_danger:{mount}"
                active_keys.add(k)
                active_instances.append({
                    "key": k,
                    "severity": "danger" if is_prod else "warning",
                    "message": f"Kapasitas penyimpanan hampir habis pada {mount}: {pct:.1f}%",
                    "tip": f"Partisi {mount} tersisa kurang dari 5%. Segera lakukan pembersihan log atau ekspansi disk.",
                    "context": None
                })
            elif pct >= 85.0:
                k = f"disk_warning:{mount}"
                active_keys.add(k)
                active_instances.append({
                    "key": k,
                    "severity": "warning",
                    "message": f"Kapasitas penyimpanan tinggi pada {mount}: {pct:.1f}%",
                    "tip": f"Partisi {mount} melampaui 85%.",
                    "context": None
                })

    # 6. Sinkronisasi ke Database ServerProblem
    existing_active = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.resolved_at == None
    ).all()
    existing_map = {p.key: p for p in existing_active}

    for inst in active_instances:
        k = inst["key"]
        if k in existing_map:
            prob = existing_map[k]
            prob.severity = inst["severity"]
            prob.updated_at = now
            prob.last_active_at = now
            prob.message = inst["message"]
            if inst.get("tip"):
                prob.tip = inst["tip"]
            if inst.get("context"):
                prob.context = inst["context"]
        else:
            new_prob = ServerProblem(
                server_id=srv.id,
                key=k,
                severity=inst["severity"],
                message=inst["message"],
                tip=inst.get("tip"),
                started_at=now,
                updated_at=now,
                last_active_at=now,
                context=inst.get("context")
            )
            db.add(new_prob)
            db.flush()

            audit_msg = f"{srv.hostname}: {inst['message']}"
            audit_log = AuditLog(
                server_id=srv.id,
                username="sistem",
                action="masalah_terdeteksi",
                target=k,
                result="terdeteksi",
                meta=audit_msg,
                created_at=now
            )
            db.add(audit_log)

    # 7. Tutup Tiket yang Telah Selesai
    for k, prob in existing_map.items():
        if k == "agent_stale":
            continue
        if k not in active_keys:
            prob.resolved_at = now
            prob.updated_at = now
            if k.startswith("ssh_active_session:"):
                prob.resolved_note = "session_closed"
            elif k.startswith("service_down:"):
                prob.resolved_note = "service_up"
            elif k in ("pkg_updates", "apt_updates"):
                prob.resolved_note = "packages_updated"
            elif k.startswith(("cpu_", "ram_", "disk_")):
                prob.resolved_note = "auto"
            else:
                prob.resolved_note = "resolved"

            audit = AuditLog(
                server_id=srv.id,
                username="sistem",
                action="masalah_selesai",
                target=k,
                result="selesai",
                meta=f"{srv.hostname}: anomali {k} telah teratasi ({prob.resolved_note})",
                created_at=now
            )
            db.add(audit)
