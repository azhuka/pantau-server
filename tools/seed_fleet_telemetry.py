#!/usr/bin/env python3
"""
Seed Fleet Telemetry
Populates pantau_server_db with high-fidelity kernel-grade telemetry for demonstration and visual validation.
"""
import sys
import json
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from core.database import SessionLocal
from models.server import Server, ServerExtras, SystemSnapshot, Service
from models.problem import ServerProblem

def seed():
    db = SessionLocal()
    try:
        # Check if already seeded
        existing_count = db.query(Server).count()
        if existing_count > 0:
            print(f"Database already contains {existing_count} servers. Refreshing telemetry snapshots...")
        else:
            print("Seeding initial fleet servers...")

            servers_data = [
                {
                    "hostname": "rj45",
                    "ip_address": "192.168.1.100",
                    "api_key": "key_rj45_master_node_sec89a",
                    "group_name": "Core NOC",
                    "tier": 1,
                    "is_active": 1,
                    "is_proxmox_ha": 0,
                    "notes": "Node Kontrol Utama NOC & Dashboard Telemetri Server.",
                    "kernel": "6.8.0-45-generic",
                    "os_label": "Ubuntu 24.04.1 LTS (Noble Numbat)",
                    "arch": "x86_64",
                    "agent_version": "0.1.0",
                    "apt_upgradable": 3,
                    "cpu_model": "AMD EPYC 7763 64-Core Processor",
                    "cores": 16,
                    "cpu": 18.5,
                    "mem_total": 33554432000,
                    "mem_used": 12884901888,
                    "swap_total": 8589934592,
                    "swap_used": 536870912,
                    "uptime_secs": 842000,
                    "services": [
                        {"name": "pantau-server.service", "active": "active", "sub": "running", "description": "Pantau Server Control Plane Daemon"},
                        {"name": "agent_pantau.service", "active": "active", "sub": "running", "description": "Pantau Monitoring Client Agent"},
                        {"name": "nginx.service", "active": "active", "sub": "running", "description": "Nginx High-Performance Web Server"},
                        {"name": "mariadb.service", "active": "active", "sub": "running", "description": "MariaDB Relational Database Server"},
                        {"name": "ssh.service", "active": "active", "sub": "running", "description": "OpenBSD Secure Shell server"},
                        {"name": "systemd-journald.service", "active": "active", "sub": "running", "description": "Journal Service"},
                        {"name": "cron.service", "active": "active", "sub": "running", "description": "Regular background program processing daemon"}
                    ],
                    "ports": [
                        {"port": 8400, "proto": "tcp", "bind": "0.0.0.0", "process": "pantau-server", "service": "Pantau Control"},
                        {"port": 8401, "proto": "tcp", "bind": "0.0.0.0", "process": "uvicorn", "service": "Pantau API v0.1"},
                        {"port": 443, "proto": "tcp", "bind": "0.0.0.0", "process": "nginx", "service": "HTTPS Edge"},
                        {"port": 80, "proto": "tcp", "bind": "0.0.0.0", "process": "nginx", "service": "HTTP Redirect"},
                        {"port": 22, "proto": "tcp", "bind": "0.0.0.0", "process": "sshd", "service": "SSH Remote"},
                        {"port": 3306, "proto": "tcp", "bind": "127.0.0.1", "process": "mariadbd", "service": "MySQL/MariaDB Core"}
                    ],
                    "processes": [
                        {"pid": 1, "user": "root", "cpu": 0.0, "mem": 0.1, "cmd": "/sbin/init"},
                        {"pid": 1235, "user": "bos", "cpu": 2.4, "mem": 1.2, "cmd": "uvicorn main:app --port 8401"},
                        {"pid": 386478, "user": "pantau", "cpu": 0.8, "mem": 0.9, "cmd": "python3 /opt/pantau/agent/agent_pantau.py"},
                        {"pid": 1824, "user": "mysql", "cpu": 1.5, "mem": 4.5, "cmd": "/usr/sbin/mariadbd"},
                        {"pid": 2401, "user": "www-data", "cpu": 0.2, "mem": 0.5, "cmd": "nginx: worker process"}
                    ],
                    "accounts": [
                        {"user": "root", "uid": 0, "home": "/root", "shell": "/bin/bash", "sessions": []},
                        {"user": "bos", "uid": 1000, "home": "/home/bos", "shell": "/bin/bash", "sessions": [
                            {"from": "192.168.1.55", "tty": "pts/0", "time": "2026-11-21 10:14:00"}
                        ]},
                        {"user": "operator", "uid": 1001, "home": "/home/operator", "shell": "/bin/bash", "sessions": []},
                        {"user": "pantau", "uid": 999, "home": "/opt/pantau", "shell": "/usr/sbin/nologin", "sessions": []}
                    ],
                    "firewall": {
                        "status": "active",
                        "rules": [
                            {"to": "22/tcp", "action": "ALLOW", "from": "Anywhere"},
                            {"to": "8400/tcp", "action": "ALLOW", "from": "Anywhere"},
                            {"to": "8401/tcp", "action": "ALLOW", "from": "Anywhere"},
                            {"to": "443/tcp", "action": "ALLOW", "from": "Anywhere"}
                        ],
                        "blocked_ips": []
                    },
                    "cron": {
                        "jobs": [
                            {"schedule": "0 2 * * *", "user": "root", "command": "/usr/local/bin/pantau-backup.sh", "source": "/etc/crontab"},
                            {"schedule": "*/5 * * * *", "user": "pantau", "command": "/opt/pantau/agent/health_check.sh", "source": "/var/spool/cron/crontabs/pantau"}
                        ]
                    },
                    "disks": [
                        {"mount": "/", "filesystem": "/dev/nvme0n1p2", "total": 107374182400, "used": 34359738368, "free": 73014444032, "percent": 32.0},
                        {"mount": "/var/log", "filesystem": "/dev/nvme0n1p3", "total": 53687091200, "used": 8589934592, "free": 45097156608, "percent": 16.0}
                    ]
                },
                {
                    "hostname": "srv-web-edge-01",
                    "ip_address": "10.10.1.15",
                    "api_key": "key_web_edge_01_a9fbc812",
                    "group_name": "DMZ Edge",
                    "tier": 1,
                    "is_active": 1,
                    "is_proxmox_ha": 1,
                    "notes": "Edge Load Balancer & SSL Termination Cluster.",
                    "kernel": "6.8.0-40-generic",
                    "os_label": "Ubuntu 24.04 LTS",
                    "arch": "x86_64",
                    "agent_version": "0.1.0",
                    "apt_upgradable": 0,
                    "cpu_model": "Intel Xeon Gold 6338 CPU @ 2.00GHz",
                    "cores": 8,
                    "cpu": 42.1,
                    "mem_total": 16777216000,
                    "mem_used": 6710886400,
                    "swap_total": 4294967296,
                    "swap_used": 0,
                    "uptime_secs": 1250000,
                    "services": [
                        {"name": "nginx.service", "active": "active", "sub": "running", "description": "Nginx Web Proxy"},
                        {"name": "keepalived.service", "active": "active", "sub": "running", "description": "VRRP High Availability"},
                        {"name": "ssh.service", "active": "active", "sub": "running", "description": "OpenSSH Daemon"}
                    ],
                    "ports": [
                        {"port": 80, "proto": "tcp", "bind": "0.0.0.0", "process": "nginx", "service": "HTTP"},
                        {"port": 443, "proto": "tcp", "bind": "0.0.0.0", "process": "nginx", "service": "HTTPS"},
                        {"port": 22, "proto": "tcp", "bind": "0.0.0.0", "process": "sshd", "service": "SSH"}
                    ],
                    "processes": [
                        {"pid": 1, "user": "root", "cpu": 0.0, "mem": 0.1, "cmd": "/sbin/init"},
                        {"pid": 4510, "user": "www-data", "cpu": 12.5, "mem": 2.1, "cmd": "nginx: worker process"}
                    ],
                    "accounts": [
                        {"user": "root", "uid": 0, "home": "/root", "shell": "/bin/bash", "sessions": []},
                        {"user": "deploy", "uid": 1001, "home": "/home/deploy", "shell": "/bin/bash", "sessions": []}
                    ],
                    "firewall": {
                        "status": "active",
                        "rules": [
                            {"to": "80/tcp", "action": "ALLOW", "from": "Anywhere"},
                            {"to": "443/tcp", "action": "ALLOW", "from": "Anywhere"},
                            {"to": "22/tcp", "action": "ALLOW", "from": "10.10.0.0/16"}
                        ],
                        "blocked_ips": []
                    },
                    "cron": {"jobs": []},
                    "disks": [
                        {"mount": "/", "filesystem": "/dev/sda1", "total": 42949672960, "used": 15032385536, "free": 27917287424, "percent": 35.0}
                    ]
                },
                {
                    "hostname": "srv-db-cluster-01",
                    "ip_address": "10.10.2.11",
                    "api_key": "key_db_cluster_01_c71e892",
                    "group_name": "Database",
                    "tier": 1,
                    "is_active": 1,
                    "is_proxmox_ha": 0,
                    "notes": "Primary MariaDB 11.4 Galera Replication Node.",
                    "kernel": "6.1.0-21-amd64",
                    "os_label": "Debian GNU/Linux 12 (bookworm)",
                    "arch": "x86_64",
                    "agent_version": "0.1.0",
                    "apt_upgradable": 5,
                    "cpu_model": "AMD EPYC 7543 32-Core Processor",
                    "cores": 32,
                    "cpu": 68.4,
                    "mem_total": 67108864000,
                    "mem_used": 52428800000,
                    "swap_total": 17179869184,
                    "swap_used": 1073741824,
                    "uptime_secs": 2450000,
                    "services": [
                        {"name": "mariadb.service", "active": "active", "sub": "running", "description": "MariaDB Database Server"},
                        {"name": "ssh.service", "active": "active", "sub": "running", "description": "OpenSSH Daemon"}
                    ],
                    "ports": [
                        {"port": 3306, "proto": "tcp", "bind": "0.0.0.0", "process": "mariadbd", "service": "MySQL Client Port"},
                        {"port": 4567, "proto": "tcp", "bind": "0.0.0.0", "process": "mariadbd", "service": "Galera Replication"},
                        {"port": 22, "proto": "tcp", "bind": "0.0.0.0", "process": "sshd", "service": "SSH"}
                    ],
                    "processes": [
                        {"pid": 1, "user": "root", "cpu": 0.0, "mem": 0.1, "cmd": "/sbin/init"},
                        {"pid": 2981, "user": "mysql", "cpu": 45.2, "mem": 62.1, "cmd": "/usr/sbin/mariadbd --wsrep-new-cluster"}
                    ],
                    "accounts": [
                        {"user": "root", "uid": 0, "home": "/root", "shell": "/bin/bash", "sessions": []},
                        {"user": "sysadmin_sadri", "uid": 1002, "home": "/home/sysadmin_sadri", "shell": "/bin/bash", "sessions": [
                            {"from": "10.10.99.12", "tty": "pts/1", "time": "2026-11-21 12:05:00"}
                        ]}
                    ],
                    "firewall": {
                        "status": "active",
                        "rules": [
                            {"to": "3306/tcp", "action": "ALLOW", "from": "10.10.0.0/16"},
                            {"to": "4567/tcp", "action": "ALLOW", "from": "10.10.2.0/24"},
                            {"to": "22/tcp", "action": "ALLOW", "from": "10.10.99.0/24"}
                        ],
                        "blocked_ips": []
                    },
                    "cron": {"jobs": []},
                    "disks": [
                        {"mount": "/", "filesystem": "/dev/sda1", "total": 53687091200, "used": 16106127360, "free": 37580963840, "percent": 30.0},
                        {"mount": "/var/lib/mysql", "filesystem": "/dev/nvme0n1", "total": 536870912000, "used": 268435456000, "free": 268435456000, "percent": 50.0}
                    ]
                },
                {
                    "hostname": "srv-app-worker-02",
                    "ip_address": "10.10.3.22",
                    "api_key": "key_app_worker_02_e341b",
                    "group_name": "Compute",
                    "tier": 2,
                    "is_active": 1,
                    "is_proxmox_ha": 0,
                    "notes": "Celery Asynchronous Tasks & Background Jobs.",
                    "kernel": "5.15.0-107-generic",
                    "os_label": "Ubuntu 22.04 LTS",
                    "arch": "x86_64",
                    "agent_version": "0.1.0",
                    "apt_upgradable": 12,
                    "cpu_model": "Intel Xeon E5-2680 v4 @ 2.40GHz",
                    "cores": 14,
                    "cpu": 25.0,
                    "mem_total": 16777216000,
                    "mem_used": 5033164800,
                    "swap_total": 4294967296,
                    "swap_used": 0,
                    "uptime_secs": 450000,
                    "services": [
                        {"name": "redis-server.service", "active": "active", "sub": "running", "description": "Advanced key-value store"},
                        {"name": "celery.service", "active": "active", "sub": "running", "description": "Celery Task Queue Worker"}
                    ],
                    "ports": [
                        {"port": 6379, "proto": "tcp", "bind": "127.0.0.1", "process": "redis-server", "service": "Redis Cache"},
                        {"port": 22, "proto": "tcp", "bind": "0.0.0.0", "process": "sshd", "service": "SSH"}
                    ],
                    "processes": [
                        {"pid": 1, "user": "root", "cpu": 0.0, "mem": 0.1, "cmd": "/sbin/init"},
                        {"pid": 8901, "user": "celery", "cpu": 15.2, "mem": 4.1, "cmd": "celery worker -A tasks --concurrency=8"}
                    ],
                    "accounts": [
                        {"user": "root", "uid": 0, "home": "/root", "shell": "/bin/bash", "sessions": []},
                        {"user": "celery", "uid": 1001, "home": "/home/celery", "shell": "/bin/bash", "sessions": []}
                    ],
                    "firewall": {"status": "inactive", "rules": [], "blocked_ips": []},
                    "cron": {"jobs": []},
                    "disks": [
                        {"mount": "/", "filesystem": "/dev/sda1", "total": 53687091200, "used": 21474836480, "free": 32212254720, "percent": 40.0}
                    ]
                }
            ]

            now = datetime.utcnow()
            for s_data in servers_data:
                server = Server(
                    hostname=s_data["hostname"],
                    ip_address=s_data["ip_address"],
                    api_key=s_data["api_key"],
                    group_name=s_data["group_name"],
                    tier=s_data["tier"],
                    is_active=s_data["is_active"],
                    is_proxmox_ha=s_data["is_proxmox_ha"],
                    notes=s_data["notes"],
                    last_seen=now,
                    created_at=now
                )
                db.add(server)
                db.flush()

                extras = ServerExtras(
                    server_id=server.id,
                    kernel=s_data["kernel"],
                    os_label=s_data["os_label"],
                    arch=s_data["arch"],
                    agent_version=s_data["agent_version"],
                    apt_upgradable=s_data["apt_upgradable"],
                    hardware_specs=json.dumps({
                        "cpu_model": s_data["cpu_model"],
                        "cores": s_data["cores"]
                    }),
                    systemd_units=json.dumps(s_data["services"]),
                    listening_ports=json.dumps(s_data["ports"]),
                    top_procs=json.dumps(s_data["processes"]),
                    accounts=json.dumps(s_data["accounts"]),
                    firewall=json.dumps(s_data["firewall"]),
                    cron_jobs=json.dumps(s_data["cron"]),
                    updated_at=now
                )
                db.add(extras)

                snapshot = SystemSnapshot(
                    server_id=server.id,
                    timestamp=now,
                    cpu=s_data["cpu"],
                    load1=round(s_data["cpu"] / 20.0, 2),
                    load5=round(s_data["cpu"] / 25.0, 2),
                    load15=round(s_data["cpu"] / 30.0, 2),
                    mem_total=s_data["mem_total"],
                    mem_used=s_data["mem_used"],
                    mem_avail=s_data["mem_total"] - s_data["mem_used"],
                    swap_total=s_data["swap_total"],
                    swap_used=s_data["swap_used"],
                    procs=len(s_data["processes"]) * 10,
                    uptime_secs=s_data["uptime_secs"],
                    disks=json.dumps(s_data["disks"]),
                    net=json.dumps({"rx_rate": 154200, "tx_rate": 320100})
                )
                db.add(snapshot)

                # Add sample problem if active SSH or high load
                if s_data["hostname"] == "srv-db-cluster-01":
                    prob = ServerProblem(
                        server_id=server.id,
                        key="ssh_active_session:sysadmin_sadri:pts/1",
                        severity="warning",
                        message="Human SSH Session Detected: sysadmin_sadri on pts/1 from 10.10.99.12",
                        tip="Audit session command execution in Tasks or terminate via Sever SSH button.",
                        started_at=now - timedelta(minutes=42)
                    )
                    db.add(prob)
                elif s_data["hostname"] == "srv-app-worker-02":
                    prob = ServerProblem(
                        server_id=server.id,
                        key="apt_upgradable_packages:12",
                        severity="info",
                        message="12 APT system packages are available for upgrade.",
                        tip="Execute Upgrade OS from the tactical action deck.",
                        started_at=now - timedelta(hours=3)
                    )
                    db.add(prob)

            db.commit()
            print("Successfully seeded 4 fleet servers with physical kernel telemetry, extras, snapshots, and problem tickets!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed()
