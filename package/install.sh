#!/usr/bin/env bash
#
# install.sh — Instalasi & Penilaian Kesiapan Agen Pantau
# ========================================================
# Langkah pertama di server klien, SEKALIGUS panduan instalasi.
# Aman dijalankan berulang (idempotent): tidak menimpa konfigurasi yang ada.
#
# ALUR 3 LANGKAH (cara memasang agen pantau di server klien):
#
#   1) sudo bash install.sh     <- LANGSUNG SEKARANG. Memeriksa & memasang
#                                   agen, lalu menilai: LAYAK / TIDAK LAYAK
#                                   untuk melangkah ke langkah 2.
#   2) sudo bash setup.sh       <- MENGARAHKAN AGEN KE DASHBOARD.
#                                   Anda akan diminta 2 informasi:
#                                     * alamat Dashboard pantau server
#                                       (contoh: http://172.30.1.40:8400)
#                                     * API key server ini (dibuat & di-
#                                       salin dari Dashboard -> menu Server)
#   3) Dashboard                <- Verifikasi terakhir. Status server ini
#                                   harus "online" di halaman server.
#
# Yang dipasang (ringkas):
#   user khusus 'pantau' (tanpa login) + grup 'adm' (baca log layanan)
#   agen   : /opt/pantau/agent/agent_pantau.py
#   config : /etc/pantau/config.json + restart.deny
#   layanan: agent_pantau.service (systemd, jalan sebagai 'pantau')
#
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Jalankan sebagai root: sudo bash $0"
    exit 1
fi

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo '================================================================'
echo '  AGEN PANTAU — INSTALASI & PENILAIAN KESIAPAN'
echo '================================================================'
echo "Server        : $(hostname) (IP $(hostname -I | awk '{print $1}'))"
echo "Paket sumber  : $PKG"
echo
echo '  LANGKAH 1 (sekarang) : pasang agen + periksa kesiapan'
echo '  LANGKAH 2 (berikut)  : sudo bash setup.sh  -> arahkan ke Dashboard'
echo '                         + API key (dari Dashboard -> menu Server)'
echo '  LANGKAH 3 (verifikasi): pastikan server ini "online" di Dashboard'
echo '================================================================'
echo

# --- LANGKAH 1: pemeriksaan prasyarat (preflight). Skip: SKIP_PREFLIGHT=1 ---
if [ "${SKIP_PREFLIGHT:-0}" != "1" ] && [ -x "$PKG/preflight.sh" ]; then
    echo "==> Memeriksa prasyarat (preflight)..."
    if ! "$PKG/preflight.sh"; then
        echo
        echo "[ERROR] Prasyarat ada yang FAIL. Perbaiki item FAIL lalu ulangi,"
        echo "        atau paksa instalasi dengan: SKIP_PREFLIGHT=1 sudo bash install.sh"
        exit 1
    fi
else
    echo "==> Preflight dilewati (SKIP_PREFLIGHT=1)."
fi

echo
echo "==> Memasang agen..."

# --- 1. User khusus 'pantau' ---
if ! id -u pantau >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin pantau
    echo "[OK]   User 'pantau' dibuat"
else
    echo "[SKIP] User 'pantau' sudah ada"
fi

# --- 1b. Group 'adm' utk akses read journalctl (/var/log) tanpa sudo ---
#       Baca journal + /var/log/syslog, auth.log (fitur log layanan klien)
if ! id -nG pantau | tr ' ' '\n' | grep -qx adm; then
    usermod -a -G adm pantau
    echo "[OK]   pantau ditambahkan ke grup adm (baca journal & /var/log)"
else
    echo "[SKIP] pantau sudah di grup adm"
fi

# --- 2. Software root (/opt/pantau) ---
install -d -o root -g root -m 755 /opt/pantau/agent
install -o root -g root -m 755 "$PKG/opt/pantau/agent/agent_pantau.py" \
    /opt/pantau/agent/agent_pantau.py
echo "[OK]   Agent -> /opt/pantau/agent/agent_pantau.py"

# --- 3. Config (/etc/pantau) ---
install -d -o root -g pantau -m 750 /etc/pantau
if [[ ! -f /etc/pantau/config.json ]]; then
    install -o root -g pantau -m 640 "$PKG/etc/pantau/config.json" \
        /etc/pantau/config.json
    echo "[OK]   config.json baru dibuat"
    echo "      -> Arahkan ke Dashboard:  sudo bash setup.sh"
else
    echo "[SKIP] /etc/pantau/config.json sudah ada (tidak ditimpa)"
    INST_KEY="$(python3 -c 'import json;print((json.load(open("'"$PKG"'/etc/pantau/config.json")).get("api_key","")[:8])+"...")' 2>/dev/null || true)"
    LIVE_KEY="$(python3 -c 'import json;print((json.load(open("/etc/pantau/config.json")).get("api_key","")[:8])+"...")' 2>/dev/null || true)"
    if [ -n "$INST_KEY" ] && [ -n "$LIVE_KEY" ] && [ "$INST_KEY" != "$LIVE_KEY" ]; then
        echo "[WARN] api_key di /etc/pantau/config.json ($LIVE_KEY) BEDA dari salinan paket ($INST_KEY)"
        echo "       -> salami key dari Dashboard, lalu:  sudo systemctl restart agent_pantau.service"
    fi
fi
install -o root -g pantau -m 640 "$PKG/etc/pantau/restart.deny" \
    /etc/pantau/restart.deny
echo "[OK]   restart.deny terpasang"

# --- 4. Wrapper restart ---
install -d -o root -g root -m 755 /usr/local/sbin
install -o root -g root -m 750 "$PKG/usr/local/sbin/pantau-restart" \
    /usr/local/sbin/pantau-restart
echo "[OK]   Wrapper restart -> /usr/local/sbin/pantau-restart"
install -o root -g root -m 750 "$PKG/usr/local/sbin/pantau-history" \
    /usr/local/sbin/pantau-history
echo "[OK]   Wrapper history -> /usr/local/sbin/pantau-history"
install -o root -g root -m 750 "$PKG/usr/local/sbin/pantau-firewall" \
    /usr/local/sbin/pantau-firewall
echo "[OK]   Wrapper firewall -> /usr/local/sbin/pantau-firewall"

# --- 5. Sudoers (validasi dulu, lalu pasang) ---
install -d -o root -g root -m 750 /etc/sudoers.d
TMP_SUDOERS="$(mktemp)"
cp "$PKG/etc/sudoers.d/pantau-agent" "$TMP_SUDOERS"
chmod 440 "$TMP_SUDOERS"
if ! visudo -c -f "$TMP_SUDOERS" >/dev/null 2>&1; then
    echo "[ERROR] Sudoers tidak lolos validasi visudo, batal." >&2
    rm -f "$TMP_SUDOERS"
    exit 1
fi
install -o root -g root -m 440 "$TMP_SUDOERS" /etc/sudoers.d/pantau-agent
rm -f "$TMP_SUDOERS"
echo "[OK]   Sudoers -> /etc/sudoers.d/pantau-agent (tidak ada akses sudo umum)"

# --- 6. Systemd service (agent_pantau.service) ---
install -o root -g root -m 644 "$PKG/etc/systemd/system/agent_pantau.service" \
    /etc/systemd/system/agent_pantau.service
# Migrasi dari nama lama "pantau.service" bila pernah ada
if [ -f /etc/systemd/system/pantau.service ] || systemctl list-unit-files pantau.service >/dev/null 2>&1; then
    systemctl disable --now pantau.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/pantau.service
    echo "[OK]   unit lama pantau.service dihapus (diganti agent_pantau.service)"
fi
systemctl daemon-reload
systemctl enable agent_pantau.service >/dev/null 2>&1
systemctl restart agent_pantau.service
echo "[OK]   agent_pantau.service aktif (User=pantau)"

# Hentikan agent dev/legacy (setsid manual) agar tidak lapor ganda
if pgrep -f "/home/bos/rj45/agent/agent_pantau.py" >/dev/null 2>&1; then
    pkill -f "/home/bos/rj45/agent/agent_pantau.py"
    echo "[OK]   Agent dev lama dihentikan (hindari laporan ganda)"
fi

# --- LANGKAH 3: penilaian kesiapan menuju setup.sh ---
echo
echo "==> Menilai kesiapan untuk LANGKAH 2 (setup.sh)..."
CFG_URL="$(python3 -c 'import json;print(json.load(open("/etc/pantau/config.json")).get("server_url",""))' 2>/dev/null || true)"
CFG_KEY="$(python3 -c 'import json;print(json.load(open("/etc/pantau/config.json")).get("api_key",""))' 2>/dev/null || true)"
VERDICT="UNKNOWN"
if [ -n "$CFG_URL" ] && [ -n "$CFG_KEY" ]; then
    VERDICT="$(python3 - "$CFG_URL" "$CFG_KEY" <<'PY'
import sys, urllib.error, urllib.request
try:
    req = urllib.request.Request(sys.argv[1].rstrip("/") + "/api/commands")
    req.add_header("X-Api-Key", sys.argv[2])
    with urllib.request.urlopen(req, timeout=8) as r:
        print("OK" if r.status == 200 else "AUTH%d" % r.status)
except urllib.error.HTTPError as e:
    print("AUTH%d" % e.code)
except Exception as e:
    print("UNREACH:%s" % (type(e).__name__))
PY
)"
fi

echo "  Dashboard : $CFG_URL"
case "$VERDICT" in
    OK)
        echo '================================================================'
        echo '  VERDICT: LAYAK - agen sudah terpasang DAN sudah terhubung'
        echo '           ke Dashboard (API key diterima).'
        echo '================================================================'
        echo "  Final: buka Dashboard -> server \"$(hostname)\" -> pastikan status 'online'."
        echo "  Info : systemctl status agent_pantau.service | journalctl -u agent_pantau -f"
        ;;
    AUTH*)
        echo '================================================================'
        echo '  VERDICT: TIDAK LAYAK KE LANGKAH 2 (belum/terhubung salah)'
        echo '  Agent TELAH terpasang, tapi API key belum dikenali Dashboard'
        echo '  (key placeholder/kedaluarsa, HTTP '"${VERDICT#AUTH}"').'
        echo '================================================================'
        ;;
    UNREACH*)
        echo '================================================================'
        echo '  VERDICT: TIDAK LAYAK KE LANGKAH 2 (Dashboard tak terjangkau)'
        echo "  Alamat '$CFG_URL' tidak bisa dihubungi. Pastikan alamat benar."
        echo '================================================================'
        ;;
    *)
        echo '================================================================'
        echo '  VERDICT: TIDAK LAYAK KE LANGKAH 2 (config belum terbaca)'
        echo '================================================================'
        ;;
esac

if [ "$VERDICT" != "OK" ]; then
    echo
    echo '  LANGKAH 2  ===  sudo bash setup.sh  ==='
    echo '  Jalankan dari folder paket:'
    if [ -x "$PKG/setup.sh" ]; then
        echo "      sudo bash $PKG/setup.sh"
    else
        echo '      sudo bash setup.sh'
    fi
    echo '  Yang perlu Anda siapkan:'
    echo '     * alamat Dashboard (contoh: http://172.30.1.40:8400)'
    echo '     * API key server ini — buat & salin di:'
    echo '         Dashboard pantau server -> menu Server -> tambah server ini.'
    echo '       SALIN KEY LENGKAP (64 hex). JANGAN pakai tampilan '
    echo '       terpotong seperti "abcd1234...5678ef90".'
    echo '  setup.sh akan MENGUJI key ke Dashboard dulu, baru menyimpan.'
    if [ -t 0 ]; then
        echo
        read -rp "  Jalankan setup.sh sekarang? [y/N]: " ANS
        if [[ "$ANS" =~ ^[yY]$ ]] && [ -x "$PKG/setup.sh" ]; then
            echo
            exec "$PKG/setup.sh"
        fi
    fi
    echo
    echo '  Setelah selesai, cek:  sudo bash install.sh  (verdict => LAYAK).'
fi

echo