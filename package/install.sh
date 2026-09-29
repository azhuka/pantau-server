#!/usr/bin/env bash
# install.sh — PASANG AGEN PANTAU DI SERVER KLIEN (SATU LANGKAH)
# ==============================================================
# Satu-satunya file yang perlu dijalankan di server klien. Tidak perlu
# mengunduh seluruh repo. Dua cara menjalankan (sama saja):
#
#   cara A — dari folder paket (git clone / arsip):
#       sudo bash install.sh
#
#   cara B — tanpa folder sama sekali (unduh SATU file ini, lalu jalankan):
#       sudo curl -fsSL -o /tmp/pantau-install.sh \
#         https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
#       sudo bash /tmp/pantau-install.sh
#
# Yang dilakukan, berurutan:
#   1) Periksa prasyarat (python3, ss, sudo, systemd) — hanya hentikan
#      bila ada yang wajib tidak ada.
#   2) Buat user khusus 'pantau' (tanpa login) + grup 'adm' (baca log).
#   3) Pasang agen, wrapper, sudoers, unit systemd; file diambil dari
#      folder paket bila ada, SELAIN ITU diunduh satu-per-satu dari GitHub
#      (hanya file yang dibutuhkan agen, bukan seluruh repo).
#   4) Arahkan ke Dashboard: minta URL + API key, DIUJI dulu ke server,
#      baru disimpan. Bila sudah terkonfigurasi valid, nilai lama dipakai.
#   5) Jalankan service & beri verdict (LAYAK / catatan untuk diperbaiki).
#
# Idempotent: aman dijalankan ulang (tidak menimpa config yang valid).
#
# Tanpa interaksi (opsional):
#   sudo bash install.sh http://127.0.0.1:8400 9a3f...c1cb
#   SETUP_SERVER_URL=... SETUP_API_KEY=... sudo bash install.sh
set -u

BASE_URL="https://raw.githubusercontent.com/azhuka/pantau-server/master/package"

if [[ $EUID -ne 0 ]]; then
    echo "Jalankan sebagai root: sudo bash $0"
    exit 1
fi
command -v python3 >/dev/null 2>&1 || { echo "[ERROR] python3 tidak ada di mesin ini — wajib untuk agen."; exit 1; }

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$PKG/opt/pantau/agent/agent_pantau.py" ]; then
    echo "  Paket sumber : folder $PKG (file lokal)"
    SRC_MODE="local"
else
    echo "  Paket sumber : diunduh per-file dari GitHub (agen saja, bukan seluruh repo)"
    SRC_MODE="remote"
fi

echo '================================================================'
echo '  AGEN PANTAU — INSTALASI SATU LANGKAH'
echo '================================================================'
echo "Server        : $(hostname) (IP $(hostname -I | awk '{print $1}'))"
echo '  Yang dibutuhkan nanti: alamat Dashboard + API key (buat di'
echo '  Dashboard -> menu Server, salin key LENGKAP 64 hex).'
echo '================================================================'

# ---------------------------------------------------------------------------
# Prasyarat (hanya fatal bila komponen wajib tidak ada)
# ---------------------------------------------------------------------------
FAIL=0
check() {
    printf '  [%s] %s\n' "$1" "$2"
}
if command -v python3 >/dev/null 2>&1; then
    PVER="$(python3 -c 'import sys;print(sys.version_info[:2])' 2>/dev/null || echo '?')"
    check "OK   " "Python $PVER"
else
    check "FAIL " "python3 tidak ada (wajib)"; FAIL=1
fi
command -v ss    >/dev/null 2>&1 && check "OK   " "ss tersedia"                 || { check "FAIL " "ss tidak ada (/usr/bin/ss, paket iproute2)"; FAIL=1; }
command -v sudo  >/dev/null 2>&1 && check "OK   " "sudo tersedia"               || { check "FAIL " "sudo tidak ada (wajib)"; FAIL=1; }
command -v systemctl >/dev/null 2>&1 && check "OK   " "systemd aktif"           || { check "FAIL " "systemd tidak ada (wajib)"; FAIL=1; }
if [ "$FAIL" != "0" ]; then
    echo "[ERROR] Prasyarat wajib ada yang kurang. Perbaiki lalu ulangi."
    exit 1
fi

# ---------------------------------------------------------------------------
# Ambil file (lokal bila ada; selain itu unduh dari GitHub)
#                                                            rel:file-sumber
# ---------------------------------------------------------------------------
get_file() {
    local rel="$1" dst="$2" mode="$3" owner_group="$4"
    local owner="${owner_group%%:*}" group="${owner_group##*:}"
    local tmp; tmp="$(mktemp)"
    if [ "$SRC_MODE" = "local" ]; then
        if [ ! -f "$PKG/$rel" ]; then rm -f "$tmp"; echo "[ERROR] Tidak ada $rel di paket."; return 1; fi
        cp "$PKG/$rel" "$tmp"
    else
        curl -fsSL --connect-timeout 15 "$BASE_URL/$rel" -o "$tmp" || { rm -f "$tmp"; echo "[ERROR] Gagal mengunduh $rel"; return 1; }
    fi
    install -o "$owner" -g "$group" -m "$mode" "$tmp" "$dst" || { rm -f "$tmp"; echo "[ERROR] Gagal menulis $dst"; return 1; }
    rm -f "$tmp"
}

# ---------------------------------------------------------------------------
# 1. User khusus 'pantau' + grup adm
# ---------------------------------------------------------------------------
if ! id -u pantau >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin pantau || { echo "[ERROR] Gagal membuat user 'pantau'."; exit 1; }
    echo "[OK]   User 'pantau' dibuat"
else
    echo "[SKIP] User 'pantau' sudah ada"
fi
if ! id -nG pantau | tr ' ' '\n' | grep -qx adm; then
    usermod -a -G adm pantau || { echo "[ERROR] Gagal menambah pantau ke grup adm."; exit 1; }
    echo "[OK]   pantau -> grup adm (baca journal & /var/log)"
else
    echo "[SKIP] pantau sudah di grup adm"
fi

# ---------------------------------------------------------------------------
# 2. Software, config, wrapper, sudoers, systemd (idempotent)
# ---------------------------------------------------------------------------
install -d -o root -g root -m 755 /opt/pantau/agent
get_file opt/pantau/agent/agent_pantau.py /opt/pantau/agent/agent_pantau.py 755 root:root
echo "[OK]   Agen -> /opt/pantau/agent/agent_pantau.py"

install -d -o root -g pantau -m 750 /etc/pantau
get_file etc/pantau/restart.deny /etc/pantau/restart.deny 640 root:pantau
echo "[OK]   restart.deny terpasang"

install -d -o root -g root -m 755 /usr/local/sbin
for wr in pantau-restart pantau-history pantau-firewall pantau-apt; do
    get_file usr/local/sbin/$wr /usr/local/sbin/$wr 750 root:root
    echo "[OK]   Wrapper $wr"
done

install -d -o root -g root -m 750 /etc/sudoers.d
TMP_SD="$(mktemp)"; cp /dev/null "$TMP_SD"
if [ "$SRC_MODE" = "local" ]; then
    cp "$PKG/etc/sudoers.d/pantau-agent" "$TMP_SD"
else
    curl -fsSL --connect-timeout 15 "$BASE_URL/etc/sudoers.d/pantau-agent" -o "$TMP_SD" \
        || { rm -f "$TMP_SD"; echo "[ERROR] Gagal mengunduh sudoers."; exit 1; }
fi
chmod 440 "$TMP_SD"
if ! visudo -c -f "$TMP_SD" >/dev/null 2>&1; then
    rm -f "$TMP_SD"; echo "[ERROR] Sudoers tidak lolos visudo — batal."; exit 1
fi
install -o root -g root -m 440 "$TMP_SD" /etc/sudoers.d/pantau-agent
rm -f "$TMP_SD"
echo "[OK]   Sudoers -> /etc/sudoers.d/pantau-agent"

get_file etc/systemd/system/agent_pantau.service /etc/systemd/system/agent_pantau.service 644 root:root
systemctl daemon-reload
echo "[OK]   Unit manager daemon-reload"

# ---------------------------------------------------------------------------
# 3. Arahkan ke Dashboard (config) — pakai lama bila valid, selain itu minta.
# ---------------------------------------------------------------------------
CUR_URL=$(python3 -c 'import json,sys
try: print(json.load(open("/etc/pantau/config.json")).get("server_url",""))
except Exception: print("")' 2>/dev/null)
CUR_KEY=$(python3 -c 'import json,sys
try: print(json.load(open("/etc/pantau/config.json")).get("api_key",""))
except Exception: print("")' 2>/dev/null)

key_ok() {  # 64 hex, bukan placeholder
    local k="$1"
    [ "$(printf '%s' "$k" | wc -c)" = 64 ] || return 1
    case "$k" in
        *[!0-9a-fA-F]*) return 1 ;;
        0000000000000000000000000000000000000000000000000000000000000000) return 1 ;;
        sha256:*) return 1 ;;
        *) return 0 ;;
    esac
}
url_ok() { case "$1" in http://*|https://*) return 0 ;; *) return 1 ;; esac; }

URL="${1:-}"; KEY="${2:-}"
if [ -z "$URL" ] && [ -z "$KEY" ]; then
    URL="${SETUP_SERVER_URL:-}"; KEY="${SETUP_API_KEY:-}"
fi
if [ -z "$URL" ] && url_ok "$CUR_URL" && key_ok "$CUR_KEY"; then
    URL="$CUR_URL"; KEY="$CUR_KEY"
    echo "[INFO] Config lama dipakai -> ${URL}  (fp ${CUR_KEY:0:8}...${CUR_KEY: -8})"
fi

if [ -z "$URL" ] || [ -z "$KEY" ]; then
    if [ -t 0 ]; then
        read -rp $'URL Dashboard pantau server (contoh: http://172.30.1.40:8400)\n  > ' URL
        read -rp $'API key 64 hex (salin key LENGKAP, bukan "xxxx…xxxx")\n  > ' KEY
    else
        echo "[ERROR] Tidak ada konfigurasi valid & tidak ada input (TTY/env).
        Berikan: sudo bash install.sh <URL> <APIKEY64hex>"
        exit 1
    fi
fi
URL="${URL%/}"
url_ok "$URL" || { echo "[ERROR] server_url harus http(s):// ... — contoh: http://172.30.1.40:8400"; exit 1; }
key_ok "$KEY" || { echo "[ERROR] api_key bukan 64 hex (ada $(printf '%s' "$KEY" | wc -c) karakter) — salin key LENGKAP dari Dashboard."; exit 1; }

# Uji dulu ke Dashboard sebelum menyimpan.
echo
echo "== Validasi ke Dashboard =="
RES="$(URL_VAL="$URL" KEY_VAL="$KEY" python3 - <<'PY'
import os, socket, re, urllib.error, urllib.request
url, key = os.environ["URL_VAL"], os.environ["KEY_VAL"]
m = re.match(r"^https?://([^:/]+)(?::(\d+))?", url)
if not m:
    print("URLINVALID"); raise SystemExit
try:
    socket.create_connection((m.group(1), int(m.group(2) or (443 if url.startswith("https") else 80))), timeout=5).close()
except Exception as e:
    print("UNREACHABLE:%s" % e); raise SystemExit
try:
    req = urllib.request.Request(url + "/api/commands")
    req.add_header("X-Api-Key", key)
    with urllib.request.urlopen(req, timeout=8) as r:
        print("OK" if r.status == 200 else "HTTP%d" % r.status)
except urllib.error.HTTPError as e:
    print("HTTP%d" % e.code)
except Exception as e:
    print("ERR:%s" % e)
PY
)"
case "$RES" in
    OK)   echo "  [PASS] API key diterima (HTTP 200)." ;;
    HTTP401) echo "  [ERROR] API key DITOLAK (HTTP 401) — key bukan milik server terdaftar."; exit 1 ;;
    HTTP*) echo "  [ERROR] Respon HTTP ${RES#HTTP} dari Dashboard."; exit 1 ;;
    *)    echo "  [ERROR] Dashboard tak terjangkau: $RES"; echo "         Periksa alamat, firewall, dan bahwa dashboard online."; exit 1 ;;
esac

TMP="$(mktemp)"
python3 - "$URL" "$KEY" "$TMP" <<'PY' || { rm -f "$TMP"; exit 1; }
import json, sys
doc = {"server_url": sys.argv[1], "api_key": sys.argv[2], "interval_seconds": 10, "exclude_ports": []}
open(sys.argv[3], "w").write(json.dumps(doc, indent=2) + "\n")
PY
install -o root -g pantau -m 640 "$TMP" /etc/pantau/config.json \
    || { rm -f "$TMP"; echo "[ERROR] Gagal menulis /etc/pantau/config.json."; exit 1; }
rm -f "$TMP"
echo "[OK]   /etc/pantau/config.json disimpan (root:pantau, 640)"

# ---------------------------------------------------------------------------
# 4. Jalankan service + verdict
# ---------------------------------------------------------------------------
systemctl enable agent_pantau.service >/dev/null 2>&1
if ! systemctl restart agent_pantau.service; then
    echo "[ERROR] Service tidak bisa dijalankan — cek: journalctl -u agent_pantau -e"
    exit 1
fi
echo "[OK]   agent_pantau.service aktif (jalan sebagai 'pantau')."

if pgrep -f "/home/bos/rj45/agent/agent_pantau.py" >/dev/null 2>&1; then
    pkill -f "/home/bos/rj45/agent/agent_pantau.py"
    echo "[OK]   Agent dev lama dihentikan."
fi

echo
echo "=================================================================="
echo "  VERDICT: LAYAK — agen terpasang & terhubung ke $URL"
echo "  Verifikasi akhir: Dashboard -> server \"$(hostname)\" -> status 'online'."
echo "  Log  : journalctl -u agent_pantau -f"
echo "=================================================================="
exit 0