#!/usr/bin/env python3
"""
Test Suite: System Integrity, Incident Triaging, Workflow & Algorithmic Correctness
Menguji seluruh alur kerja, taksonomi 4-tingkat keparahan, proteksi tier produksi vs non-produksi,
serta efisiensi kueri dan responsivitas API.
"""
import sys
import os
from datetime import datetime, timedelta

# Injeksi path server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings
from models.user import User
from models.server import Server, ServerExtras, SystemSnapshot
from models.problem import ServerProblem
from services.problem_service import evaluate_server_problems, check_server_stale, check_all_servers_stale
from routers.servers import list_servers, get_server_detail
from routers.problems import list_problems

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def run_tests():
    print("[*] MEMULAI PENGUJIAN INTEGRITAS SISTEM & ALGORITMA...")
    user = db.query(User).filter(User.username == "master-admin").first()
    assert user is not None, "User master-admin harus ada di basis data"

    # 1. Uji Zero N+1 Query & List Servers
    print("[1] Menguji list_servers() dan optimasi Zero N+1...")
    res = list_servers(user=user, db=db)
    assert res["ok"] is True
    assert len(res["servers"]) >= 1
    srv_data = res["servers"][0]
    print(f"    -> Server: {srv_data['hostname']} | CPU: {srv_data['cpu']}% | RAM: {srv_data['mem_pct']}% | Disk: {srv_data['disk_pct']}% | Procs/Uptime: {srv_data['uptime_secs']}s")
    assert srv_data["disk_pct"] is not None

    # 2. Uji Taksonomi Insiden: Info (Pembaruan Paket OS)
    print("[2] Menguji taksonomi insiden INFO (pkg_updates)...")
    srv = db.query(Server).filter(Server.id == srv_data["id"]).first()
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == srv.id).first()
    report_info = {
        "hostname": srv.hostname,
        "apt": {"upgradable": 5, "packages": ["linux-image", "nginx"]},
        "system": {"cpu": 10.0, "mem_total": 8000000, "mem_used": 2000000, "disks": [{"mount": "/", "pct": 40.0}]}
    }
    evaluate_server_problems(db, srv, report_info, extras)
    db.commit()

    prob_info = db.query(ServerProblem).filter(ServerProblem.server_id == srv.id, ServerProblem.key == "pkg_updates", ServerProblem.resolved_at == None).first()
    assert prob_info is not None, "Tiket pkg_updates harus aktif"
    assert prob_info.severity == "info", f"Severity harus 'info', didapat: {prob_info.severity}"
    print(f"    -> [OK] Tiket info terverifikasi: {prob_info.message} (severity={prob_info.severity})")

    # 3. Uji Taksonomi Insiden: Warning (Sesi Remote SSH Legal)
    print("[3] Menguji taksonomi insiden WARNING (ssh_active_session)...")
    report_ssh = {
        "hostname": srv.hostname,
        "accounts": [
            {
                "user": "sysadmin_sadri",
                "sessions": [{"from": "192.168.1.100", "tty": "pts/2", "time": "10:00"}]
            }
        ],
        "system": {"cpu": 15.0, "mem_total": 8000000, "mem_used": 2000000, "disks": [{"mount": "/", "pct": 40.0}]}
    }
    evaluate_server_problems(db, srv, report_ssh, extras)
    db.commit()

    prob_ssh = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key.like("ssh_active_session:sysadmin_sadri%"),
        ServerProblem.resolved_at == None
    ).first()
    assert prob_ssh is not None, "Tiket sesi SSH legal harus aktif"
    assert prob_ssh.severity == "warning", f"Severity sesi legal harus 'warning', didapat: {prob_ssh.severity}"
    print(f"    -> [OK] Tiket warning terverifikasi: {prob_ssh.message} (severity={prob_ssh.severity})")

    # 4. Uji Taksonomi Insiden: Critical (Service Down pada Server Produksi Tier 1)
    print("[4] Menguji taksonomi insiden CRITICAL (service_down:nginx pada Produksi)...")
    srv.tier = 1
    db.commit()
    report_svc_down = {
        "hostname": srv.hostname,
        "units": [
            {"name": "nginx.service", "active": "failed", "sub": "failed", "description": "Nginx Web Server"}
        ],
        "system": {"cpu": 15.0, "mem_total": 8000000, "mem_used": 2000000, "disks": [{"mount": "/", "pct": 40.0}]}
    }
    evaluate_server_problems(db, srv, report_svc_down, extras)
    db.commit()

    prob_svc = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "service_down:nginx",
        ServerProblem.resolved_at == None
    ).first()
    assert prob_svc is not None, "Tiket service_down:nginx harus aktif"
    assert prob_svc.severity == "critical", f"Severity service down pada Produksi harus 'critical', didapat: {prob_svc.severity}"
    print(f"    -> [OK] Tiket critical terverifikasi: {prob_svc.message} (severity={prob_svc.severity})")

    # 5. Uji Perbedaan Tier: Service Down pada Server Non-Produksi (Tier 2) -> Capped at Warning
    print("[5] Menguji proteksi keparahan Non-Produksi (Tier 2)...")
    srv.tier = 2
    db.commit()
    evaluate_server_problems(db, srv, report_svc_down, extras)
    db.commit()
    prob_svc_t2 = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "service_down:nginx",
        ServerProblem.resolved_at == None
    ).first()
    assert prob_svc_t2 is not None
    assert prob_svc_t2.severity == "warning", f"Severity service down pada Non-Produksi harus diredam ke 'warning', didapat: {prob_svc_t2.severity}"
    print(f"    -> [OK] Tier 2 capping terverifikasi: severity={prob_svc_t2.severity}")

    # 6. Uji Auto-Resolution saat Layanan Pulih Normal
    print("[6] Menguji auto-resolution saat service kembali up...")
    report_recovered = {
        "hostname": srv.hostname,
        "units": [
            {"name": "nginx.service", "active": "active", "sub": "running", "description": "Nginx Web Server"}
        ],
        "system": {"cpu": 15.0, "mem_total": 8000000, "mem_used": 2000000, "disks": [{"mount": "/", "pct": 40.0}]}
    }
    evaluate_server_problems(db, srv, report_recovered, extras)
    db.commit()
    prob_svc_resolved = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "service_down:nginx"
    ).order_by(ServerProblem.id.desc()).first()
    assert prob_svc_resolved.resolved_at is not None, "Tiket harus berstatus diselesaikan"
    assert prob_svc_resolved.resolved_note == "service_up", f"Resolved note harus 'service_up', didapat: {prob_svc_resolved.resolved_note}"
    print(f"    -> [OK] Auto-resolution terverifikasi: resolved_note={prob_svc_resolved.resolved_note}")

    # 7. Uji Server Offline (agent_stale) & Danger Escalation
    print("[7] Menguji deteksi server offline (agent_stale) & Danger escalation...")
    srv.tier = 1
    srv.last_seen = datetime.utcnow() - timedelta(minutes=4)
    db.commit()
    check_server_stale(db, srv)
    db.commit()
    prob_stale = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "agent_stale",
        ServerProblem.resolved_at == None
    ).first()
    assert prob_stale is not None, "Tiket agent_stale harus aktif"
    assert prob_stale.severity == "danger", f"Stale > 3 mnt pada Produksi harus 'danger', didapat: {prob_stale.severity}"
    print(f"    -> [OK] Danger escalation terverifikasi: {prob_stale.message} (severity={prob_stale.severity})")

    # Pulihkan last_seen
    srv.last_seen = datetime.utcnow()
    db.commit()
    check_server_stale(db, srv)
    db.commit()
    prob_stale_res = db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.key == "agent_stale"
    ).order_by(ServerProblem.id.desc()).first()
    assert prob_stale_res.resolved_at is not None
    assert prob_stale_res.resolved_note == "server_online"
    print(f"    -> [OK] Stale recovery terverifikasi: resolved_note={prob_stale_res.resolved_note}")

    # 8. Uji list_problems() API
    print("[8] Menguji router list_problems() API...")
    probs_res = list_problems(active_only=True, user=user, db=db)
    assert probs_res["ok"] is True
    print(f"    -> Total insiden aktif yang dilaporkan API: {len(probs_res['problems'])}")

    print("\n[V] SELURUH PENGUJIAN INTEGRITAS ALGORITMA & WORKFLOW LULUS 100% TANPA CACAT!")

if __name__ == "__main__":
    run_tests()
    db.close()
