# Pantau Server

[![Version](https://img.shields.io/badge/version-v0.1.105-blue.svg)](file:///home/bos/pantau-server/server/config.py)
[![Backend](https://img.shields.io/badge/backend-FastAPI%20%7C%20Python%203.12-emerald.svg)](file:///home/bos/pantau-server/server/main.py)
[![Frontend](https://img.shields.io/badge/frontend-Vue%203%20%7C%20Tailwind%20CSS-cyan.svg)](file:///home/bos/pantau-server/frontend/src/App.vue)
[![Database](https://img.shields.io/badge/database-MySQL%208.0%2B%20%7C%20MariaDB-orange.svg)](file:///home/bos/pantau-server/server/models/)
[![License](https://img.shields.io/badge/license-Proprietary-darkred.svg)](#license)

Pantau Server is a self-hosted Linux infrastructure monitoring and operations control plane designed for Network Operations Centers (NOC) and system administrators. It delivers real-time telemetry, centralized incident triaging, and host management across multi-node server environments with kernel-level physical accuracy.

---

## Key Capabilities

* **Real-Time Fleet Observability:** Monitor physical host telemetry across your entire infrastructure, including CPU load, memory and swap utilization, root and mount storage capacity, system uptime, and active network interfaces.
* **Centralized Incident Triage:** Immediate visibility into anomalies, service failures, high resource thresholds, and unannounced SSH logins with categorized severity levels (Critical, High, Warning, Info).
* **Asset Workspace Controller:** Perform deep-dive node inspections directly from a high-efficiency floating workspace without losing fleet context:
  - **System Services:** Audit `systemd` units, view service execution states, and safely trigger restarts.
  - **Process Management:** Identify resource-intensive processes with prioritized sorting and secure termination controls.
  - **Network & Ports:** Inspect active listening sockets, binding addresses, and transport protocols.
  - **Firewall Rules:** View and manage UFW status, port rules, and traffic directions.
  - **Task Automation:** Review user crontabs and systemd timer schedules.
  - **User & SSH Sessions:** Monitor logged-in users and actively connected SSH terminal sessions with instant disconnect capability.
* **Integrated Operations Deck:** Built-in web terminal console, remote file explorer, and host maintenance controls with strict confirmation guardrails.
* **Workspace Shelf Tray:** Minimize active inspection windows to the bottom shelf tray and resume seamlessly across multiple server nodes.

---

## Architecture & Technology Stack

* **Backend:** FastAPI (Python 3.12+), SQLAlchemy 2.0 ORM, Uvicorn ASGI server.
* **Frontend:** Vue 3 (Composition API), Vite, Tailwind CSS. Single-page application compiled directly into standalone static assets.
* **Database:** MySQL 8.0+ / MariaDB 10.6+ InnoDB with strictly normalized relational schemas.
* **Client Agent:** Lightweight standalone Python daemon (`agent_pantau.py`) utilizing standard library only (zero external package dependencies).

---

## Prerequisites

* **Operating System:** Linux (Ubuntu 22.04 / 24.04 LTS, Debian 12, RHEL / Rocky Linux 9).
* **Python:** 3.10 or higher.
* **Database:** MySQL 8.0+ or MariaDB 10.6+ (InnoDB storage engine).
* **Node.js:** 18 LTS or higher (for building frontend assets).

---

## Production Installation

Run on the central monitoring server (Ubuntu 22.04/24.04 LTS or Debian 12):

```bash
# 1. Install system prerequisites
sudo apt update && sudo apt install -y python3 python3-venv python3-pip mariadb-server git curl rsync openssl

# 2. Clone repository
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server

# 3. Run production installer
sudo bash install-server.sh
```

The installer automatically:
- Creates the dedicated `pantau-server` system user and installs backend files to `/opt/pantau/server/` and compiled SPA assets to `/opt/pantau/frontend/dist/`.
- Creates `/opt/pantau/server/env` and installs dependencies from `server/requirements.txt`.
- Initializes MariaDB database `pantau_db` and user `pantau_dash`, and writes `/opt/pantau/server/.env` (mode `640`).
- Installs, enables, and starts `pantau-server.service` on port `8400`.
- Creates the initial `master_admin` account via `seed_admin.py` (skipped if a `master_admin` already exists).

Access the control console at `http://<SERVER_IP>:8400`.

---

## Development Setup

### 1. Backend
```bash
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r server/requirements.txt
cp server/.env.example server/.env
uvicorn main:app --app-dir server --host 0.0.0.0 --port 8400 --reload
```

### 2. Frontend
```bash
cd frontend
npm install
npm run build
```

---

## Keyboard Navigation

* `1`: Navigate to Dashboard
* `2`: Navigate to Fleet Inventory
* `3`: Navigate to Audit Trail
* `4`: Navigate to Settings
* `[`: Switch to previous host in active workspace
* `]`: Switch to next host in active workspace
* `ESC`: Close active modal or console

---

## License

Copyright © 2026 Pantau Server Project (azhuka). All rights reserved.
