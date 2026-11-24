# Pantau Server

[![Version](https://img.shields.io/badge/version-v0.1.32-blue.svg)](file:///home/bos/pantau-server/server/config.py)
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

## Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
```

### 2. Configure Backend
```bash
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r server/requirements.txt
```

### 3. Build Frontend
```bash
cd frontend
npm install
npm run build
cd ..
```

### 4. Environment Setup
```bash
cp server/.env.example server/.env
```
Edit `server/.env` with your database credentials and secret key:
```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=pantau_db
DB_PASS=pantau_server
DB_NAME=pantau_server_db
SERVER_HOST=0.0.0.0
SERVER_PORT=8401
SECRET_KEY=your_secure_secret_key
```

### 5. Run the Server
```bash
source env/bin/activate
uvicorn main:app --app-dir server --host 0.0.0.0 --port 8401
```
Access the control console at `http://<SERVER_IP>:8401`.

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
