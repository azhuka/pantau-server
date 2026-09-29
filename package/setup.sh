#!/usr/bin/env bash
#
# setup.sh - Konfigurasi interaktif Agen Pantau (pola ala Zabbix)
# ==============================================================
# Di jalankan SETELAH instalasi, untuk mengarahkan agent ke Dashboard:
#     sudo bash setup.sh
#
# Alur:
#   1. Baca nilai lama dari /etc/pantau/config.json (sebagai default)
#   2. Minta server_url + api_key + interval + exclude_ports (Enter=biarkan)
#   3. VALIDASI live ke Dashboard dulu (HTTP 200 pakai key tsb)
#   4. Hanya bila valid: tulis /etc/pantau/config.json (root:pantau, 640)
#      lalu restart agent_pantau.service
#
# Non-interaktif (CI/otomasi) lewat env:
#     SETUP_SERVER_URL=... SETUP_API_KEY=... sudo bash setup.sh
#
set -u

CFG=/etc/pantau/config.json
UNIT=agent_pantau.service

if [[ $EUID -ne 0 ]]; then
    echo "Jalankan sebagai root: sudo bash $0"
    exit 1
fi

command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 tidak ada (butuh untuk validasi JSON)"; exit 1; }

# Agen belum pernah dipasang? setup.sh TIDAK memasang agen — itu tugas install.sh.
# (grup 'pantau' dibuat oleh install.sh via useradd; unit agent_pantau.service
#  dipasang oleh install.sh juga). Menggagalkan lebih jujur daripada lanjut
#  sampai tahap tulis config lalu gagal diam-diam.
if ! id -g pantau >/dev/null 2>&1 || \
   ! { systemctl cat "$UNIT" >/dev/null 2>&1 || [ -f "/etc/systemd/system/$UNIT" ]; }; then
    echo
    echo "[ERROR] Agen pantau BELUM terpasang di mesin ini"
    echo "        (user/grup 'pantau' atau unit '$UNIT' tidak ada)."
    echo
    echo "   Jalankan dulu (dari folder paket klien):"
    echo "       sudo bash install.sh"
    echo "   lalu ulangi langkah ini:"
    echo "       sudo bash setup.sh"
    exit 1
fi

# --- 1. default dari config lama ---
DEF_URL=""; DEF_KEY=""; DEF_INT="10"; DEF_EXCL="[]"
if [ -f "$CFG" ]; then
    read -r DEF_URL < <(python3 - "$CFG" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("server_url", ""))
except Exception:
    print("")
PY
)
    read -r DEF_KEY < <(python3 - "$CFG" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("api_key", ""))
except Exception:
    print("")
PY
)
    read -r DEF_INT < <(python3 - "$CFG" <<'PY'
import json, sys
try:
    print(int(json.load(open(sys.argv[1])).get("interval_seconds", 10)))
except Exception:
    print("10")
PY
)
    read -r DEF_EXCL < <(python3 - "$CFG" <<'PY'
import json, sys
try:
    print(json.dumps(json.load(open(sys.argv[1])).get("exclude_ports", [])))
except Exception:
    print("[]")
PY
)
fi

echo "== Setup Agen Pantau =="
if [ -n "${SETUP_SERVER_URL:-}" ] && [ -n "${SETUP_API_KEY:-}" ]; then
    echo "[mode non-interaktif dari env]"
    URL="$SETUP_SERVER_URL"; KEY="$SETUP_API_KEY"
    read -r INT < <(echo "${SETUP_INTERVAL:-$DEF_INT}")
    read -r EXCL < <(echo "${SETUP_EXCLUDE_PORTS:-$DEF_EXCL}")
else
    read -rp "URL Dashboard pantau server   [${DEF_URL}]: " URL
    URL="${URL:-$DEF_URL}"
    case "$URL" in
        http://*|https://*) ;;
        *) echo "ERROR: server_url harus diawali http(s):// — contoh: http://172.30.1.40:8400"; exit 1 ;;
    esac
    read -rp $'API key 64 hex, PASTE KEY LENGKAP (jangan fingerprint "xxxx…xxxx")   ['"${DEF_KEY:0:8}"'...'"${DEF_KEY: -8}"']: ' KEY
    KEY="${KEY:-$DEF_KEY}"
    read -rp "Interval laporan detik        [$DEF_INT]: " INT
    INT="${INT:-$DEF_INT}"
    read -rp "Exclude port (koma, mis 80,443) [$DEF_EXCL]: " EXCL
    EXCL="${EXCL:-$DEF_EXCL}"
fi

URL="${URL%/}"
[ -n "$URL" ] || { echo "ERROR: server_url kosong."; exit 1; }
[ -n "$KEY" ] || { echo "ERROR: api_key kosong."; exit 1; }
case "$KEY" in
    *[!0-9a-fA-F]*) echo "ERROR: api_key harus 64 hex (mungkin Anda menyalin fingerprint 'xxxx…xxxx' dengan titik-titik — pakai key LENGKAP dari Dashboard)."; exit 1 ;;
esac
[ ${#KEY} -eq 64 ] || { echo "ERROR: api_key harus 64 hex (ada ${#KEY} karakter)."; exit 1; }
_INT="$(echo "$INT" | tr -dc '0-9')"; [ -n "$_INT" ] && [ "$_INT" -ge 5 ] && [ "$_INT" -le 3600 ] || { echo "ERROR: interval tidak valid ($INT)."; exit 1; }

# --- 3. validasi live ---
echo
echo "== Validasi koneksi ke Dashboard =="
RES="$(python3 - "$URL" "$KEY" <<'PY'
import re, socket, sys, urllib.error, urllib.request
url, key = sys.argv[1], sys.argv[2]
m = re.match(r"^https?://([^:/]+)(?::(\d+))?", url)
if not m:
    print("URLINVALID"); sys.exit(2)
try:
    sock = socket.create_connection((m.group(1), int(m.group(2) or (443 if url.startswith("https") else 80))), timeout=5)
    sock.close()
except Exception as e:
    print("UNREACHABLE:%s" % e); sys.exit(2)
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
    OK)
        echo "  [PASS] API key diterima (HTTP 200) — server sudah terdaftar."
        ;;
    HTTP401)
        echo "  [WARN] API key ditolak (HTTP 401) — key ini TIDAK dikenali Dashboard."
        read -rp "Tetap tulis (y/N)? " ANS
        case "$ANS" in y|Y) echo "  (menulis dengan key yang ditolak)";; *) echo "Batal."; exit 1;; esac
        ;;
    HTTP*)
        echo "  [WARN] Respon HTTP $RES dari Dashboard."
        read -rp "Tetap tulis (y/N)? " ANS
        case "$ANS" in y|Y) :;; *) echo "Batal."; exit 1;; esac
        ;;
    *)
        echo "  [ERROR] Gagal menjangkau Dashboard: $RES"
        exit 1
        ;;
esac

# --- 4. tulis + restart ---
if [ "$EXCL" = "[]" ] || [ -z "$EXCL" ]; then
    EXCL_JSON="[]"
elif [[ "$EXCL" == \[* ]]; then
    EXCL_JSON="$EXCL"
else
    EXCL_JSON="$(python3 -c 'import json,sys; print(json.dumps([int(x) for x in sys.argv[1].replace(" ","").split(",") if x]))' "$EXCL")"
fi

TMP="$(mktemp)"
python3 - "$URL" "$KEY" "$_INT" "$EXCL_JSON" "$TMP" <<'PY' || { rm -f "$TMP"; exit 1; }
import json, sys
url, key, interval, excl, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), json.loads(sys.argv[4]), sys.argv[5]
doc = {"server_url": url, "api_key": key, "interval_seconds": interval, "exclude_ports": excl}
open(out, "w").write(json.dumps(doc, indent=2) + "\n")
PY
install -o root -g pantau -m 640 "$TMP" "$CFG" || {
    rm -f "$TMP"
    echo "[ERROR] Gagal menulis $CFG (grup 'pantau' / izin / ruang disk)."
    echo "        Cek: ls -ld /etc/pantau && id pantau"
    exit 1
}
rm -f "$TMP"
echo "[OK]   $CFG ditulis (root:pantau, 640)."

if systemctl cat "$UNIT" >/dev/null 2>&1; then
    if systemctl restart "$UNIT"; then
        echo "[OK]   $UNIT di-restart."
        UNIT_OK=1
    else
        echo "[ERROR] Gagal restart $UNIT — cek: journalctl -u ${UNIT%.service} -e"
        exit 1
    fi
else
    echo "[FAIL] Unit $UNIT tidak terpasang."
    echo "        Jalankan 'sudo bash install.sh' dulu, lalu 'sudo bash setup.sh' lagi."
    UNIT_OK=0
fi

echo
echo "== Selesai (fp key: ${KEY:0:8}...${KEY: -8}) =="
if [ "${UNIT_OK:-0}" = "1" ]; then
    echo "   Verifikasi: dashboard -> server ini -> status harus online dalam $((_INT + 5)) detik."
    echo "   Log : journalctl -u ${UNIT%.service} -f"
else
    echo "   CATATAN: agen BELUM berjalan (unit tidak ada)."
fi
exit 0