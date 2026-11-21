import json
import re
from datetime import datetime
from sqlalchemy.orm import Session
from models.problem import ServerProblem
from models.misc import AuditLog

def evaluate_server_problems(db: Session, srv, report_dict: dict, extras):
    """
    Evaluasi kesehatan server dan buat/tutup tiket insiden di server_problems.
    Mendukung deteksi insiden sesi remote SSH aktif (ssh_active_session) dan kepatuhan sistem.
    """
    now = datetime.utcnow()
    active_keys = set()
    active_instances = []

    # 1. Evaluasi Sesi Remote SSH Aktif (ssh_active_session)
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
            # Abaikan akun internal 'pantau'
            if u_name == "pantau":
                continue
            
            sessions = acc.get("sessions") or []
            for s in sessions:
                if not isinstance(s, dict):
                    continue
                raw_from = str(s.get("from") or "").strip().strip("()")
                r_tty = str(s.get("tty") or "").strip()
                r_time = str(s.get("time") or "").strip()

                # Sesi remote SSH memiliki IP asal atau remote host (bukan sesi display lokal X11 atau empty)
                if raw_from and not raw_from.startswith(":") and not raw_from.lower().startswith("local"):
                    clean_tty_key = r_tty.replace("/", "_") if r_tty else "ssh"
                    clean_from_key = re.sub(r"[^a-zA-Z0-9_\.:-]", "_", raw_from)
                    sess_key = f"ssh_active_session:{u_name}:{clean_tty_key}:{clean_from_key}"[:150]
                    
                    active_keys.add(sess_key)
                    tty_disp = f" ({r_tty})" if r_tty else ""
                    time_disp = f" sejak {r_time}" if r_time else ""
                    
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
                            "Pantau aktivitas pengguna melalui tab Users / Riwayat Aksi.",
                            "Gunakan tombol 'Putus Sesi' untuk memutuskan koneksi paksa jika ini sesi tidak sah."
                        ]
                    }

                    active_instances.append({
                        "key": sess_key,
                        "severity": "info",
                        "message": f"Sesi remote SSH aktif: user '{u_name}' dari {raw_from}{tty_disp}",
                        "tip": f"Pengguna '{u_name}' sedang aktif terhubung ke server klien via remote SSH dari {raw_from}{tty_disp}{time_disp}.",
                        "context": json.dumps(context_data, ensure_ascii=False)
                    })

    # 2. Evaluasi Metrik Sumber Daya (CPU / RAM / Disk)
    cpu = report_dict.get("cpu")
    if cpu is not None and isinstance(cpu, (int, float)):
        if cpu >= 95.0:
            k = "cpu_critical"
            active_keys.add(k)
            active_instances.append({
                "key": k,
                "severity": "danger",
                "message": f"Utilisasi CPU sangat tinggi: {cpu:.1f}%",
                "tip": "Beban CPU mendekati batas maksimum 100%. Periksa proses yang mengonsumsi CPU tinggi.",
                "context": None
            })
        elif cpu >= 85.0:
            k = "cpu_high"
            active_keys.add(k)
            active_instances.append({
                "key": k,
                "severity": "warning",
                "message": f"Utilisasi CPU tinggi: {cpu:.1f}%",
                "tip": "Utilisasi CPU melampaui batas ambang 85%.",
                "context": None
            })

    mem = report_dict.get("mem")
    if isinstance(mem, dict):
        total = mem.get("total", 0)
        used = mem.get("used", 0)
        if total > 0:
            mem_pct = (used / total) * 100
            if mem_pct >= 95.0:
                k = "ram_danger"
                active_keys.add(k)
                active_instances.append({
                    "key": k,
                    "severity": "danger",
                    "message": f"Alokasi RAM kritis: {mem_pct:.1f}%",
                    "tip": "Ketersediaan memori fisik hampir habis.",
                    "context": None
                })
            elif mem_pct >= 85.0:
                k = "ram_warning"
                active_keys.add(k)
                active_instances.append({
                    "key": k,
                    "severity": "warning",
                    "message": f"Alokasi RAM tinggi: {mem_pct:.1f}%",
                    "tip": "Pemakaian RAM melampaui ambang normal.",
                    "context": None
                })

    # Sinkronisasi ke database server_problems
    # 1. Buka / perbarui tiket aktif
    existing_active = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.resolved_at == None
    ).all()
    existing_map = {p.key: p for p in existing_active}

    for inst in active_instances:
        k = inst["key"]
        if k in existing_map:
            prob = existing_map[k]
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

            # Catat audit log untuk insiden baru
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

    # 2. Tutup tiket insiden yang kondisinya sudah selesai (misal sesi SSH logout)
    for k, prob in existing_map.items():
        if k not in active_keys:
            # Jika ini adalah ssh_active_session dan sesi sudah tidak ada di accounts, selesaikan seketika!
            if k.startswith("ssh_active_session:"):
                prob.resolved_at = now
                prob.updated_at = now
                prob.resolved_note = "session_closed"

                audit_msg = f"{srv.hostname}: sesi remote SSH telah ditutup ({prob.message})"
                audit_log = AuditLog(
                    server_id=srv.id,
                    username="sistem",
                    action="masalah_selesai",
                    target=k,
                    result="selesai",
                    meta=audit_msg,
                    created_at=now
                )
                db.add(audit_log)
            elif k.startswith(("cpu_", "ram_", "disk_")):
                # Metrik normal kembali
                prob.resolved_at = now
                prob.updated_at = now
                prob.resolved_note = "auto"
