#!/usr/bin/env bash
#
# preflight.sh - Cek kesiapan server untuk instalasi Agen Pantau
# ==============================================================
# Jalankan di server target (non-root boleh):
#     bash preflight.sh
#
# Hasil:
#   PASS  -> siap
#   WARN  -> bisa jalan tapi perlu perhatian
#   FAIL  -> perbaiki dulu sebelum `sudo bash install.sh`
#
# Exit code: 0 jika tidak ada FAIL, selain itu 1.
#
set -u

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0; WARN=0; FAIL=0
note() { printf '  [%-7s] %s\n' "$1" "$2"; }
pass() { PASS=$((PASS+1)); note PASS "$1"; }
warn() { WARN=$((WARN+1)); note WARN "$1"; }
fail() { FAIL=$((FAIL+1)); note FAIL "$1"; }

echo
echo "== Preflight Agen Pantau (server: $(hostname), $(hostname -I 2>/dev/null | awk '{print $1}')) =="

# --- 1. Python >= 3.10 ---
if command -v python3 >/dev/null 2>&1; then
    PV="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null)"
    MAJ="${PV%%.*}"; MIN="${PV#*.}"
    if { [ "$MAJ" -gt 3 ] || { [ "$MAJ" -eq 3 ] && [ "$MIN" -ge 10 ]; }; }; then
        pass "Python $PV (minimal 3.10 terpenuhi)"
    else
        fail "Python $PV < 3.10 — agent butuh >= 3.10 (sintaks 'str | None')"
    fi
else
    fail "python3 tidak ditemukan — install dulu (Ubuntu: sudo apt install python3)"
fi

# --- 2. binary ss ---
SS_BIN=/usr/bin/ss
if [ -x "$SS_BIN" ]; then
    pass "ss ditemukan di $SS_BIN"
elif command -v ss >/dev/null 2>&1; then
    warn "ss ada di '$(command -v ss)', bukan $SS_BIN — sesuaikan SS_BIN di agent & /etc/sudoers.d/pantau-agent"
else
    fail "ss tidak ditemukan — install iproute2 (Ubuntu: sudo apt install iproute2)"
fi

# --- 3. sudo ---
if command -v sudo >/dev/null 2>&1; then
    pass "sudo tersedia"
else
    fail "sudo tidak ada — install sudo (Ubuntu: sudo apt install sudo)"
fi

# --- 4. systemd ---
if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
    pass "systemd aktif"
else
    warn "systemd tidak aktif — instalasi butuh systemd (bukan init non-systemd)"
fi

# --- 5. cari file config ---
CFG=""
CFG_FALLBACK=0
for c in /etc/pantau/config.json "$PKG/etc/pantau/config.json"; do
    [ -r "$c" ] && CFG="$c" && [ "$c" != "/etc/pantau/config.json" ] && CFG_FALLBACK=1 && break
done
if [ -n "$CFG" ]; then
    pass "config terbaca: $CFG"
    if [ "$CFG_FALLBACK" = "1" ]; then
        warn "di-ujikan salinan paket, BUKAN /etc/pantau/config.json — file terpasang bisa beda. Periksa dengan: sudo cat /etc/pantau/config.json"
    fi
else
    fail "config.json tidak ditemukan — pastikan ada di $PKG/etc/pantau/config.json"
fi

# --- 6. paket agent ikut tersedia? ---
AGENT_SRC="$PKG/opt/pantau/agent/agent_pantau.py"
if [ -f "$AGENT_SRC" ]; then
    pass "kode agent siap di paket ($AGENT_SRC)"
else
    warn "kode agent tidak ada di paket — pastikan folder package lengkap"
fi

# --- 7. validasi isi config + koneksi (butuh python3) ---
if command -v python3 >/dev/null 2>&1 && [ -n "$CFG" ]; then
    while IFS='|' read -r TAG MSG; do
        [ -z "$TAG" ] && continue
        case "$TAG" in
            PASS) pass "$MSG" ;;
            WARN) warn "$MSG" ;;
            *)    fail "$MSG" ;;
        esac
    done < <(python3 - "$CFG" <<'PY'
import json, re, socket, sys, urllib.error, urllib.request

cfg_path = sys.argv[1]
try:
    cfg = json.load(open(cfg_path))
except Exception as e:
    print("[FAIL|config bukan JSON valid: %s" % e)
    sys.exit(2)

url = (cfg.get("server_url") or "").strip().rstrip("/")
key = (cfg.get("api_key") or "").strip()

if not url:
    print("FAIL|server_url kosong di config")
    sys.exit(1)
m = re.match(r"^https?://([^:/]+)(?::(\d+))?", url)
if not m:
    print("FAIL|server_url tidak valid: %s" % url)
    sys.exit(1)
print("PASS|server_url = %s" % url)

if not key:
    print("FAIL|api_key kosong -- salin dari Dashboard (edit server -> API key)")
    sys.exit(1)
if re.fullmatch(r"[0-9a-f]{64}", key):
    print("PASS|api_key format ok (64 hex) -- fp:", key[:8] + "..." + key[-8:])
else:
    print("WARN|api_key bukan 64 hex standar (format token_hex(32))")

host, port = m.group(1), int(m.group(2) or (443 if url.startswith("https") else 80))
try:
    s = socket.create_connection((host, port), timeout=5); s.close()
    print("PASS|dapat terhubung ke %s:%s (TCP)" % (host, port))
except Exception as e:
    print("FAIL|TIDAK bisa terhubung ke %s:%s -> %s" % (host, port, e))
    sys.exit(1)

try:
    req = urllib.request.Request(url + "/api/commands")
    req.add_header("X-Api-Key", key)
    with urllib.request.urlopen(req, timeout=5) as r:
        print("PASS|API key diterima (HTTP %d) -- server sudah terdaftar" % r.status)
except urllib.error.HTTPError as e:
    if e.code == 401:
        print("WARN|HTTP %d dari dashboard -- key tak dikenali; pastikan server sudah ditambahkan di Dashboard & key disalin benar" % e.code)
    else:
        print("WARN|HTTP %d dari dashboard" % e.code)
except Exception as e:
    print("WARN|tidak bisa uji autentikasi: %s" % e)
PY
)
else
    warn "python3 tidak tersedia di PATH -- cek config/koneksi dilewati"
fi

# --- 8. deny-list ada? ---
DENY_FILE=""
for d in /etc/pantau/restart.deny "$PKG/etc/pantau/restart.deny"; do
    [ -r "$d" ] && DENY_FILE="$d" && break
done
if [ -n "$DENY_FILE" ]; then
    pass "restart.deny ada ($DENY_FILE)"
else
    warn "restart.deny tidak ditemukan — install akan menaruh versi bawaan"
fi

echo
echo "== Ringkasan: $PASS PASS, $WARN WARN, $FAIL FAIL =="
if [ "$FAIL" -gt 0 ]; then
    echo "Perbaiki item FAIL di atas, lalu jalankan ulang preflight."
    exit 1
fi
echo "Verdict: server LAYAK dipasang agen pantau."
echo "         WARN bukan penghalang; instalasi tetap dilanjutkan."
exit 0