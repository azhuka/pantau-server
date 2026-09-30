#!/usr/bin/env bash
#
# install-server.sh — Instalasi Dashboard Pantau Server
# ======================================================
# Pasang web app Pusat Monitoring (FastAPI + MySQL/MariaDB) ke /opt/pantau/server
# pada mesin baru, dengan systemd, tanpa disalin manual dari mesin lain.
#
# Prasyarat (Ubuntu/Debian):
#   sudo apt install python3 python3-venv python3-pip mariadb-server -y
#
# Jalankan sebagai root:
#   sudo bash install-server.sh
#
# Opsional env (bila tidak ingin interaktif):
#   ADMIN_USER   default admin
#   ADMIN_PASS   default diminta interaktif
#   DB_ROOT_PASS password root MariaDB bila root tidak pakai socket auth
#
# Cara pakai:
#   1) sudo bash install-server.sh
#   2) Buka http://<ip>:8400 , login dengan admin yang tadi dibuat
#   3) Menu Server -> Tambah server -> salin API key
#   4) Di tiap mesin klien: jalankan package/install.sh (SATU FILE, tanpa repo)
#
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Jalankan sebagai root: sudo bash $0" >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/pantau/server"
APP_USER="pantau-server"
APP_PORT="${SERVER_PORT:-8400}"
DB_NAME="pantau_db"
DB_USER="pantau_dash"

for c in mysql openssl python3 rsync; do
    command -v "$c" >/dev/null 2>&1 || { echo "[ERROR] '$c' tidak ada. Install dulu." >&2; exit 1; }
done
python3 -c 'import venv' >/dev/null 2>&1 \
    || { echo "[ERROR] Python venv (python3-venv) tidak tersedia. Install dulu." >&2; exit 1; }

echo '================================================================'
echo '  PANTAU SERVER — INSTALASI DASHBOARD'
echo '================================================================'
echo "Sumber paket : $SRC"
echo "Target       : $APP_DIR"
echo

# --- 1. User khusus ---
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    echo "[OK]   User '$APP_USER' dibuat"
else
    echo "[SKIP] User '$APP_USER' sudah ada"
fi

# --- 2. Salin kode aplikasi ---
mkdir -p "$APP_DIR"
rsync -a --delete \
    --exclude '__pycache__' --exclude '*.pyc' --exclude 'env' --exclude '.env' \
    "$SRC/server/" "$APP_DIR/"
install -d -o "$APP_USER" -g "$APP_USER" -m 755 "$APP_DIR"
echo "[OK]   Kode web app -> $APP_DIR"

# --- 3. Virtualenv + dependensi ---
if [[ ! -x "$APP_DIR/env/bin/uvicorn" ]]; then
    echo "==> Membuat virtualenv ..."
    python3 -m venv "$APP_DIR/env"
fi
echo "==> Install/update dependensi (bisa beberapa menit)..."
"$APP_DIR/env/bin/pip" install --upgrade pip -q
"$APP_DIR/env/bin/pip" install -r "$APP_DIR/requirements.txt" -q
echo "[OK]   Virtualenv siap (dependensi selalu dikunci ke requirements.txt)"

# --- 4. Database MariaDB ---
# Rerun (pemasangan ulang) HARUS memakai password yang sama dengan .env lama;
# kalau tidak, user MariaDB tetap ber-password lama sementara .env tertulis yang
# baru → aplikasi gagal konek. Baca .env lama bila ada, buat baru bila belum.
OLD_PASS="$(awk -F= '/^DB_PASS=/{print $2}' "$APP_DIR/.env" 2>/dev/null || true)"
DB_PASS="${OLD_PASS:-$(openssl rand -hex 16)}"
if ! mysql -u root "${DB_ROOT_PASS:+-p$DB_ROOT_PASS}" -e "SELECT 1" >/dev/null 2>&1; then
    echo "[ERROR] Tidak bisa konek ke MariaDB sebagai root. Periksa service / beri DB_ROOT_PASS." >&2
    exit 1
fi
MYSQL_ROOT=(-u root)
[[ -n "${DB_ROOT_PASS:-}" ]] && MYSQL_ROOT+=(-p"$DB_ROOT_PASS")
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
echo "[OK]   Database ${DB_NAME} + user ${DB_USER} siap"

# --- 5. .env (rahasia; tulis dengan umask ketat biar tak pernah kebaca user lain) ---
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
EOF
install -o "$APP_USER" -g "$APP_USER" -m 640 "$TMP_ENV" "$APP_DIR/.env"
rm -f "$TMP_ENV"
echo "[OK]   Konfigurasi -> $APP_DIR/.env (rahasia, mode 640)"

# --- 6. Systemd ---
install -o root -g root -m 644 "$APP_DIR/pantau-server.service" \
    /etc/systemd/system/pantau-server.service
systemctl daemon-reload
systemctl enable pantau-server.service >/dev/null 2>&1
systemctl restart pantau-server.service
echo "[OK]   pantau-server.service aktif (port ${APP_PORT})"

# Health check HTTP: tunggu sampai server benar-benar merespons.
for i in $(seq 1 20); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${APP_PORT}/login" >/dev/null 2>&1; then
        echo "[OK]   Health check: dashboard merespons di 127.0.0.1:${APP_PORT}"
        break
    fi
    if [ "$i" = "20" ]; then
        echo "[WARN] Health check belum merespons — cek: journalctl -u pantau-server -e" >&2
    fi
    sleep 1
done

# --- 7. Akun admin ---
ADMIN_USER="${ADMIN_USER:-admin}"
if [[ -z "${ADMIN_PASS:-}" ]]; then
    read -rsp "  Password untuk user '$ADMIN_USER': " ADMIN_PASS
    echo
    [[ -n "$ADMIN_PASS" ]] || { echo "[ERROR] password kosong." >&2; exit 1; }
fi
"$APP_DIR/env/bin/python" "$APP_DIR/seed_admin.py" \
    --username "$ADMIN_USER" --role admin --password "$ADMIN_PASS"
echo "[OK]   Akun admin '$ADMIN_USER' siap"

echo
echo '================================================================'
echo '  INSTALASI SELESAI'
echo '================================================================'
echo "  Dashboard : http://$(hostname -I | awk '{print $1}'):${APP_PORT}  (login: $ADMIN_USER)"
echo
echo '  Langkah selanjutnya:'
echo '   1) Buka dashboard, menu Server -> Tambah Server -> simpan API key.'
echo '   2) Di tiap mesin yang mau dipantau, SATU file saja:'
echo "        sudo curl -fsSL -o /tmp/pantau-install.sh \\"
echo "          https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh"
echo '        sudo bash /tmp/pantau-install.sh'
echo '        (akan diminta alamat dashboard ini + API key tsb)'
echo '   3) Backups:  mysqldump pantau_db > backup.sql'
echo '================================================================'