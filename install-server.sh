#!/usr/bin/env bash
#
# install-server.sh — Production Installer for Pantau Server
# ==========================================================
# Installs Pantau Server (FastAPI + Vue 3 SPA + MariaDB) to /opt/pantau/
# with a dedicated system user and systemd service.
#
# Prerequisites (Ubuntu/Debian):
#   sudo apt update && sudo apt install -y python3 python3-venv python3-pip mariadb-server curl rsync openssl
#   (Plus nodejs & npm if frontend/dist is not prebuilt)
#
# Usage:
#   sudo bash install-server.sh
#
# Optional environment variables (for non-interactive runs):
#   ADMIN_USER      Default: admin
#   ADMIN_PASS      Password for initial master_admin (min 12 chars)
#   DB_ROOT_PASS    MariaDB root password if not using unix_socket auth
#   SERVER_PORT     Default: 8400
#   BUILD_FRONTEND  Set to 1 to force rebuilding frontend/dist
#
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo bash $0" >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="/opt/pantau"
APP_DIR="${BASE_DIR}/server"
FRONTEND_DIR="${BASE_DIR}/frontend/dist"
APP_USER="pantau-server"
APP_PORT="${SERVER_PORT:-8400}"
DB_NAME="pantau_db"
DB_USER="pantau_dash"

for c in mysql openssl python3 rsync curl; do
    command -v "$c" >/dev/null 2>&1 || { echo "[ERROR] '$c' is not installed." >&2; exit 1; }
done
python3 -c 'import venv' >/dev/null 2>&1 \
    || { echo "[ERROR] Python venv (python3-venv) is not available." >&2; exit 1; }

echo '================================================================'
echo '  PANTAU SERVER — PRODUCTION INSTALLATION'
echo '================================================================'
echo "Source       : $SRC"
echo "Target       : $APP_DIR"
echo "Frontend     : $FRONTEND_DIR"
echo

# --- 1. Dedicated system user ---
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    echo "[OK]   System user '$APP_USER' created"
else
    echo "[SKIP] System user '$APP_USER' already exists"
fi

# --- 2. Build frontend if needed & sync code ---
if [[ "${BUILD_FRONTEND:-0}" == "1" ]] || [[ ! -f "$SRC/frontend/dist/index.html" ]]; then
    command -v npm >/dev/null 2>&1 || { echo "[ERROR] 'npm' is required to build frontend/dist." >&2; exit 1; }
    echo "==> Building frontend SPA ..."
    npm ci --prefix "$SRC/frontend" --silent
    npm run build --prefix "$SRC/frontend"
    echo "[OK]   Frontend built"
fi

mkdir -p "$APP_DIR" "$FRONTEND_DIR"
rsync -a --delete \
    --exclude '__pycache__' --exclude '*.pyc' --exclude 'env' --exclude '.env' --exclude 'static/uploads' \
    "$SRC/server/" "$APP_DIR/"
rsync -a --delete "$SRC/frontend/dist/" "$FRONTEND_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$BASE_DIR/frontend"
chmod 755 "$BASE_DIR" "$APP_DIR" "$BASE_DIR/frontend" "$FRONTEND_DIR"
echo "[OK]   Application files synced to $BASE_DIR"

# --- 3. Virtualenv + Python dependencies ---
if [[ ! -x "$APP_DIR/env/bin/uvicorn" ]]; then
    echo "==> Creating Python virtualenv ..."
    python3 -m venv "$APP_DIR/env"
fi
echo "==> Installing Python dependencies ..."
"$APP_DIR/env/bin/pip" install --upgrade pip -q
"$APP_DIR/env/bin/pip" install -r "$APP_DIR/requirements.txt" -q
chown -R "$APP_USER:$APP_USER" "$APP_DIR/env"
echo "[OK]   Virtualenv ready"

# --- 4. MariaDB database & user ---
OLD_PASS="$(awk -F= '/^DB_PASS=/{print $2}' "$APP_DIR/.env" 2>/dev/null || true)"
DB_PASS="${OLD_PASS:-$(openssl rand -hex 16)}"
MYSQL_ROOT=(-u root)
[[ -n "${DB_ROOT_PASS:-}" ]] && MYSQL_ROOT+=(-p"$DB_ROOT_PASS")

if ! mysql "${MYSQL_ROOT[@]}" -e "SELECT 1" >/dev/null 2>&1; then
    echo "[ERROR] Cannot connect to MariaDB as root. Check service or set DB_ROOT_PASS." >&2
    exit 1
fi

mysql "${MYSQL_ROOT[@]}" <<SQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME}
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL
echo "[OK]   Database ${DB_NAME} and user ${DB_USER} ready"

# --- 5. .env configuration (preserve existing) ---
if [[ ! -f "$APP_DIR/.env" ]]; then
    SECRET_VAL="$(openssl rand -hex 32)"
    TMP_ENV="$(mktemp)"
    umask 077
    cat > "$TMP_ENV" <<EOF
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=${DB_USER}
DB_PASS=${DB_PASS}
DB_NAME=${DB_NAME}
SERVER_HOST=0.0.0.0
SERVER_PORT=${APP_PORT}
SECRET_KEY=${SECRET_VAL}
EOF
    install -o "$APP_USER" -g "$APP_USER" -m 640 "$TMP_ENV" "$APP_DIR/.env"
    rm -f "$TMP_ENV"
    echo "[OK]   Configuration written to $APP_DIR/.env (mode 640)"
else
    echo "[SKIP] Existing $APP_DIR/.env preserved"
fi

# --- 6. Initialize schema tables (idempotent) ---
PYTHONPATH="$APP_DIR" "$APP_DIR/env/bin/python" -c "
from core.database import Base, engine
import models  # noqa: F401
Base.metadata.create_all(bind=engine)
"
echo "[OK]   Database schema verified"

# --- 7. Systemd unit ---
TMP_UNIT="$(mktemp)"
cat > "$TMP_UNIT" <<EOF
[Unit]
Description=Pantau Server (FastAPI + Uvicorn)
Wants=network-online.target
After=network-online.target mariadb.service
StartLimitIntervalSec=0

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=HOME=${BASE_DIR}
ExecStart=${APP_DIR}/env/bin/uvicorn main:app --host 0.0.0.0 --port ${APP_PORT}
Restart=always
RestartSec=3
Nice=0

StandardOutput=journal
StandardError=journal

ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ProtectClock=yes

[Install]
WantedBy=multi-user.target
EOF
install -o root -g root -m 644 "$TMP_UNIT" /etc/systemd/system/pantau-server.service
rm -f "$TMP_UNIT"

systemctl daemon-reload
systemctl enable pantau-server.service >/dev/null 2>&1
systemctl restart pantau-server.service
echo "[OK]   pantau-server.service active (port ${APP_PORT})"

# --- 8. Health check ---
for i in $(seq 1 20); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null 2>&1; then
        echo "[OK]   Health check passed at http://127.0.0.1:${APP_PORT}/api/health"
        break
    fi
    if [[ "$i" == "20" ]]; then
        echo "[WARN] Health check did not respond in time — check: journalctl -u pantau-server -e" >&2
    fi
    sleep 1
done

# --- 9. Initial Master Admin account ---
ADMIN_COUNT="$(PYTHONPATH="$APP_DIR" "$APP_DIR/env/bin/python" -c "
from core.database import SessionLocal
from models.user import User
db = SessionLocal()
try:
    print(db.query(User).filter(User.role == 'master_admin').count())
finally:
    db.close()
" 2>/dev/null || echo "0")"

if [[ -n "${ADMIN_PASS:-}" ]] || [[ "$ADMIN_COUNT" == "0" ]]; then
    ADMIN_USER="${ADMIN_USER:-admin}"
    if [[ -z "${ADMIN_PASS:-}" ]]; then
        echo "  Password requirement: min 12 characters (uppercase, lowercase, digit, symbol)."
        read -rsp "  Password for user '$ADMIN_USER': " ADMIN_PASS
        echo
        [[ -n "$ADMIN_PASS" ]] || { echo "[ERROR] Password cannot be empty." >&2; exit 1; }
    fi
    PYTHONPATH="$APP_DIR" "$APP_DIR/env/bin/python" "$APP_DIR/seed_admin.py" \
        --username "$ADMIN_USER" --role master_admin --password "$ADMIN_PASS"
    echo "[OK]   Master admin '$ADMIN_USER' ready"
else
    echo "[SKIP] Existing master_admin account preserved"
fi

echo
echo '================================================================'
echo '  INSTALLATION COMPLETE'
echo '================================================================'
echo "  Dashboard : http://$(hostname -I | awk '{print $1}'):${APP_PORT}"
echo "  Service   : sudo systemctl status pantau-server"
echo "  Logs      : sudo journalctl -u pantau-server -f"
echo '================================================================'
