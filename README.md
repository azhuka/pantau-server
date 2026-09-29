# Pantau Server — Central Monitoring (Dashboard + Agent)

Web app pusat monitoring server: satu dashboard FastAPI + MariaDB melihat status
layanan, kinerja hardware, log, akun, dan masalah keamanan dari banyak mesin.
Keamanan **dipantau dari akar sampai permukaan — tidak ada yang disembunyikan.**

## Arsitektur

```
┌──────────────┐  HTTPS/JSON   ┌──────────────────┐
│  Dashboard   │ ◄──────────── │  Agent (Python)  │   tiap server klien
│  FastAPI     │   report  10s │  /opt/pantau/... │   User=pantau, sudo
│  :8400       │ ►─perintah──► │  systemd unit    │   di-per-sempit
│  MariaDB     │               └──────────────────┘
└──────────────┘
```

- Dashboard menerima laporan agent: daftar layanan (port + health), snapshot
  kinerja (CPU/memori/disk/jaringan), akun user, unit systemd, dan info apt.
- Dashboard juga mengirim **perintah** ke agent (restart service, apt
  update/upgrade streaming, riset log, blokir IP) — divalidasi & diaudit.
- Agent berjalan sebagai user non-login `pantau`; akses root diperoleh lewat
  sudo **hanya** untuk wrapper kecil (restart/history/firewall/apt) yang
  dibatasi di `/etc/sudoers.d/pantau-agent`.

Fitur utama: status layanan live + riwayat uptime, kartu kinerja per server
(sparkline/grafik), deteksi & aksi masalah (IP menyerang → block; service mati
→ restart), log layanan (journalctl/syslog), aktivitas user, **apt
update/upgrade streaming persis terminal SSH**, audit trail, login multi-role
(admin/viewer).

## Struktur repo

```
server/                 Web app (back-end FastAPI + template/static)
  main.py               semua endpoint & logika
  models.py             skema DB (sumber kebenaran; create_all saat start)
  config.py             settings dari .env
  seed_admin.py         CLI buat/update akun admin
  pantau-server.service unit systemd generic (dipasang install-server.sh)
database/schema.sql     skema acuan (untuk referensi)
package/                Paket AGEN yang bisa di-`git clone` ke mesin klien
  install.sh            pasang agen + nilai kesiapan (idempotent)
  setup.sh              arahkan agen ke dashboard (uji API key dulu)
  preflight.sh          cek prasyarat klien (PASS/WARN/FAIL)
  opt/pantau/agent/     kode agen Python
  etc/                  config, sudoers, unit systemd, wrapper
  usr/local/sbin/       wrapper: pantau-restart, pantau-history,
                        pantau-firewall, pantau-apt
install-server.sh       Pemasangan dashboard di mesin baru (satu perintah)
```

## 1) Instal Dashboard (mesin pusat monitoring)

Prasyarat (Ubuntu/Debian):

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb
```

Ambil kode & jalankan installer:

```bash
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Repo ini **public** — tidak perlu akun/kredensial untuk mengunduh.

Flow installer:

1. buat user sistem `pantau-server` (non-login);
2. salin web app ke `/opt/pantau/server`, buat `venv`, `pip install`;
3. buat database `pantau_db` + user DB terpisah dengan password acak
   (`openssl rand -hex 16`) yang disimpan hanya di `/opt/pantau/server/.env` (mode 640);
4. pasang & nyalakan `pantau-server.service` (port **8400**);
5. minta password admin → buat akun admin.

Verifikasi:

```bash
systemctl status pantau-server.service
# buka http://<ip>:8400  → login admin yg tadi dibuat
journalctl -u pantau-server -n 50 -f
```

> Skema tabel dibuat otomatis oleh aplikasi (`models.py`, `create_all`) saat
> pertama berjalan — `database/schema.sql` hanya referensi.

## 2) Pasang Agent di tiap server klien

Siapkan dulu dari dashboard: **Menu Server → Tambah Server** (isi hostname/IP) →
salin **API key** (64 hex). Lalu di mesin klien:

```bash
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server/package
sudo bash install.sh      # pasang agen + nilai kesiapan (LAYAK?)
sudo bash setup.sh        # arahkan ke dashboard: alamat + API key
```

Tanpa git di klien? Unduh arsip langsung (public, tanpa kredensial):

```bash
curl -L https://github.com/azhuka/pantau-server/archive/refs/heads/master.tar.gz | tar xz
cd pantau-server-master/package
sudo bash install.sh && sudo bash setup.sh
```

Detail:

- `install.sh` memasang user `pantau`, kode agen → `/opt/pantau/agent/`,
  config `/etc/pantau/config.json`, wrapper sudo, dan `agent_pantau.service`
  (systemd, `User=pantau`) — **idempotent**, aman diulang.
- `setup.sh` **menguji API key ke dashboard dulu** sebelum menyimpan.
- Verifikasi akhir: di dashboard, server klien tampil **online**; atau jalankan
  `sudo bash install.sh` lagi dan lihat verdict `LAYAK`.

Cek agen di klien:

```bash
systemctl status agent_pantau.service
journalctl -u agent_pantau -f
```

Perbarui agen tanpa kiriman manual: `git pull` di mesin klien lalu
`sudo bash install.sh` (menimpa kode, tidak menimpa config).

## Penggunaan singkat

- **Status layanan** — halaman Rincian: tombol restart per service (log di
  audit trail), riwayat uptime & koneksi per service.
- **Apt update/upgrade** — kartu "Paket OS" di Rincian: Jalankan `Update`,
  lalu `Upgrade` (streaming live persis terminal SSH). Hanya admin; tidak ada
  dua proses apt paralel.
- **Masalah** — halaman Masalah menggabungkan deteksi pola (IP menyerang,
  service mati lama, disk penuh) dengan aksi cepat Block/Restart.
- **Log** — lihat log service klien (journalctl/syslog/auth) langsung dari
  dashboard tanpa SSH.

## Keamanan

- API key disimpan **hash sha256** di DB — DB bocor ≠ key jatuh.
- Password user di-hash bcrypt (`passlib`), sesi cookie acak, login dibatasi
  (lockout setelah gagal berulang).
- Akses sudo agent dibatasi lewat sudoers `pantau-agent` ke wrapper tertentu
  saja (bukan "ALL"), diverifikasi `visudo -c` saat instal.
- Sandbox systemd dasar aktif di unit server & agent.
- Jangan mengekspos port 8400 ke internet terbuka tanpa reverse-proxy + HTTPS
  (mis. Caddy/Nginx + Tailscale).

## Lisensi

Bebas dipakai untuk lingkungan sendiri. Tidak disertai garansi apa pun.