# Pantau Server (v4.2.7)

Dashboard monitoring & management multi-server berbasis web (FastAPI + MariaDB) dengan agent daemon Python ringan untuk mengelola multi server Linux dari satu layar.

---

## Fitur Utama

- **Live Resource Monitoring:** CPU, RAM, Swap, Disk per mount point, Load Average, dan bandwidth network realtime (auto-polling tanpa refresh browser).
- **Deep Hardware & Platform Telemetry:** Deteksi model prosesor & clock speed, hypervisor/virtualisasi platform (DMI & systemd-detect-virt), jenis block storage (SSD/HDD), default gateway, DNS, interface network MAC & link speed, serta waktu boot sistem.
- **Fleet-Wide OTA Agent Self-Update:** Pembaruan versi armada agen otomatis (*self-update*) secara mandiri via polling heartbeat berkala tanpa perlu menekan tombol satu per satu, dengan verifikasi kriptografis SHA-256 dan auto-restart systemd.
- **Service & Process Control:** Start, Stop, Restart service systemd, dan kill process pemakan resource langsung dari web dengan guardrail proteksi sistem kritis.
- **Web Terminal (xterm.js):** Akses shell root interaktif langsung di browser. Mendukung ANSI color, shortcut bash, nano, htop, dan full screen.
- **Web File Manager:** Browse folder, edit config (auto-backup `.bak`), upload/download file, serta chmod/chown dengan proteksi path sistem kritis.
- **Emergency Critical Incident & Alert Tracking:** Sistem banner peringatan darurat global untuk insiden kritis (server tidak melapor / offline), eskalasi severity bertahap (Warning → Average → Critical), panduan mitigasi fisik/VM, serta alur penanganan (*acknowledge/resolve*).
- **Security & RBAC 3-Tier:** Pembagian role (Master Admin, Operator dengan wewenang sudo terdelegasi, Viewer), 2FA TOTP (Google/Microsoft Authenticator), recovery backup code, dan user activity audit trail.
- **Host Management Suite:** Kelola user Linux host (add, lock, unlock), cron job, port listening (kill/block via UFW), dan inspeksi masa aktif SSL.
- **One-Click & Automatic OTA Agent Update:** Push update agent manual per-server atau otomatis menyeluruh ke seluruh client langsung dari dashboard.

---

## 1. Install Dashboard (Server Pusat)

Jalankan di server Ubuntu/Debian:

```bash
# 1. Update paket & pasang dependensi
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

# 2. Clone repo & jalankan installer
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Script installer akan otomatis:
- Membuat user sistem `pantau`
- Menyiapkan database MariaDB
- Memasang service `pantau-server.service`
- Meminta password admin saat instalasi

Selesai install, akses dashboard via browser:
- **URL:** `http://<IP-SERVER>:8400`
- **Username:** `admin`
- **Password:** password yang dibuat saat instalasi

**Cek status service dashboard:**
```bash
sudo systemctl status pantau-server.service
```

**Lupa password admin? Reset langsung via CLI:**
```bash
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password 'password-baru'
```

---

## 2. Install Agent di Server Client

Agent tidak butuh port inbound (tidak perlu buka port SSH ke arah client). Agent aktif melapor keluar (*outbound pull*) ke dashboard setiap 5–10 detik via HTTP POST, sehingga aman di balik NAT, firewall ketat, atau jaringan private LAN/VPN.

1. Buka dashboard: Masuk ke menu **Servers → Tambah Server**, lalu salin **API Key** (64 hex).
2. Di server client yang ingin dimonitor, unduh dan jalankan script installer:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Installer akan meminta konfigurasi secara interaktif dan fleksibel:
- **URL Dashboard**: Masukkan alamat server Dashboard (misal via LAN/VPN: `http://172.30.1.40:8400` atau via reverse proxy `https://pantau.domain.com`).
- **API Key**: Masukkan 64 karakter hex API Key yang telah disalin.

Script secara otomatis:
- Memvalidasi keterjangkauan dan keabsahan API Key ke Dashboard sebelum menyimpan data.
- Menulis konfigurasi aman di `/etc/pantau/config.json` (permission `0640`, owner `root:pantau`).
- Mendaftarkan dan mengaktifkan service systemd `agent_pantau.service` di bawah user `pantau`.

*(Opsi non-interaktif untuk script otomasi/Ansible tetap didukung: `sudo bash /tmp/pantau-install.sh "http://<IP-DASHBOARD>:8400" "<API_KEY>"`)*

Dalam ±10 detik, server client otomatis muncul dengan status online di dashboard.

**Cek service dan log agent di client:**
```bash
sudo systemctl status agent_pantau.service
sudo journalctl -u agent_pantau -f
```

---

## Panduan Fitur & Tab

### Dashboard Utama
- Overview armada server: status Online / Offline, service down, dan rata-rata load.
- Tabel server live dengan tombol copy IP, search instan, dan sorting kolom.

### Detail Server
- **Tab Riwayat:** Grafik utilisasi CPU, RAM, Swap, Disk I/O, Load Average, dan Disk per mount point (1 jam s/d 30 hari).
- **Tab Service:** Kontrol service systemd (Start, Stop, Restart, Add Service). Status tombol responsif instan (*Optimistic UI*) dan sinkron cepat via *fast-polling*.
- **Tab Masalah:** Daftar alert & insiden realtime, tombol mitigasi cepat, opsi Mute/Silence (2 jam, 24 jam, permanen), dan konfirmasi penanganan (ack/resolve).
- **Tab ⚡ Top Process:** Snapshot 20 proses pemakan CPU & RAM tertinggi, lengkap dengan opsi kill process (*SIGTERM* / *SIGKILL*).
- **Tab Jaringan:** Interface network, IP address (IPv4/IPv6), link status, dan data throughput (KB/s / MB/s).
- **Tab User Host:** Daftar user lokal Linux, status lock/unlock, riwayat login SSH, dan log aktivitas sudo.
- **Tab Port & Firewall:** Daftar listening port (TCP/UDP), process owner, serta tombol block port/IP instan via UFW.
- **Tab SSL:** Masa aktif sertifikat SSL/TLS domain lokal dan alert sebelum expired.
- **Tab Cron Job:** Kelola crontab sistem (tambah, enable/disable, run now, delete).
- **Tab Log:** Log viewer terpadu (system log & journald) dengan filter teks dan download file log.
- **Web Terminal (`>_ Terminal`):** Buka terminal shell root interaktif langsung di browser.
- **File Manager (`📁 File Manager`):** Remote file explorer untuk edit file konfigurasi, upload, dan download.
- **Maintenance (`🔧 Pemeliharaan`):** Mute seluruh alert sementara saat server sedang maintenance/reboot.

### Profil & Keamanan (User Management)
- **Akun Pribadi:** Ganti password, aktifkan 2FA TOTP (Google/Microsoft Authenticator), simpan recovery code, dan regenerate backup code.
- **Manajemen User:** Tambah akun operator/viewer, atur checklist izin sudo granular, reset password user lain, lock/unlock user, dan review user activity audit trail.

---

## Role & Hak Akses (RBAC 3-Tier)

Sistem hak akses 3-tier dengan model delegasi seperti perintah `sudo` di Linux:

1. **Master Admin**: Otoritas tertinggi setara *root*. Akun kebal (tidak bisa dihapus, di-lock, atau diturunkan haknya). Memegang kendali penuh atas server, terminal, file manager, dan pengaturan izin operator.
2. **Operator (Wewenang Sudo)**: Akun operasional harian. Master Admin dapat mendelegasikan wewenang spesifik (misal: hanya boleh kelola service dan buka terminal, tapi dilarang menghapus server).
   - **Zero-Knowledge**: Operator sama sekali tidak bisa melihat keberadaan akun Master Admin (data dan counter Master Admin disembunyikan total).
3. **Viewer**: Akun pengawas baca-saja (*read-only*). Hanya bisa melihat metrik dan grafik tanpa tombol aksi apapun. Terisolasi total dari info akun admin dan tidak memiliki akses ke menu Profil.

| Fitur / Aksi | Master Admin | Operator (Sudo) | Viewer |
|---|:---:|:---:|:---:|
| View Dashboard, Metrik & Log | Ya | Ya | Ya |
| Kelola Server & Service (Start/Stop/Restart) | Ya | Sesuai Izin | Tidak |
| Buka Web Terminal & File Manager | Ya | Sesuai Izin | Tidak |
| Reboot, Power Off & Update OS (APT) | Ya | Sesuai Izin | Tidak |
| Firewall (UFW) & Block/Unblock IP | Ya | Sesuai Izin | Tidak |
| User Management (Tambah, Edit, Lock User) | Ya | Sesuai Izin | Tidak |
| Hapus / Edit Akun Master Admin | Ya (Personal) | Ditolak Mutlak | Tidak |
| Akses Profil Pribadi & Setup 2FA | Ya | Ya | Tidak |

---

## Cara Update Dashboard & Agent

### 1. Update Dashboard
Jalankan di server dashboard:
```bash
cd /opt/pantau/server/pantau-server   # sesuaikan direktori clone Anda
git pull
sudo bash install-server.sh
```
*Script aman dijalankan ulang: file `.env` dan database tidak akan tertimpa.*

### 2. Update Agent Otomatis (Fleet-Wide Self-Update OTA) [Bawaan & Otomatis ⭐]
Saat Dashboard diperbarui, seluruh armada agen di server client yang masih menjalankan versi lebih lama akan **otomatis melakukan self-update mandiri** pada siklus polling berikutnya (dalam ~10 detik) tanpa perlu campur tangan manual:
1. Server mendeteksi versi agen client lebih lama dari versi dashboard saat polling `/api/commands`.
2. Server secara otomatis mengantrekan instruksi pembaruan dengan URL binary dan hash SHA-256 resmi.
3. Agen client mengunduh pembaruan, memverifikasi integritas SHA-256, menguji sintaks via `py_compile`, memperbarui berkas `/opt/pantau/agent/agent_pantau.py` secara atomik (`chmod 0755`), dan me-restart dirinya sendiri via systemd watchdog.
4. Versi agen langsung sinkron ke versi dashboard terbaru.

### 3. Update Agent Manual (Opsional)
- **Via Dashboard**: Klik tombol **`⚡ Push Update (OTA)`** pada halaman detail server jika ingin memicu update manual seketika.
- **Via Terminal Client (One-Liner)**:
  ```bash
  sudo curl -fsSL -o /opt/pantau-update.sh https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh && sudo bash /opt/pantau-update.sh
  ```

---

## Web Terminal & Remote Command

Web Terminal menghubungkan browser langsung ke sesi Pseudo-Terminal (PTY) Linux `/bin/bash` di server client via WebSocket bridge.

- **Karakteristik Shell:** Mendukung pipeline (`|`), redirection (`>`), auto-completion tombol `Tab`, navigasi kursor, signal `Ctrl+C` asli, editor teks (`nano`/`vim`), serta viewer interaktif (`htop`).
- **Keamanan:** Berjalan sebagai user `root` melalui wrapper ketat `sudo /usr/local/sbin/pantau-shell` (dikonfigurasi via `/etc/sudoers.d/pantau-agent`).
- **Privasi:** Riwayat perintah tidak disimpan ke disk (`HISTFILE=/dev/null`). Sesi idle otomatis ditutup setelah 8 jam.
- **Audit Trail:** Pembukaan dan penutupan terminal dicatat lengkap dengan timestamp, username, dan IP di Audit Trail.
- **Update OS (APT):** Tombol *Update OS* di dashboard menjalankan `apt update` & `apt upgrade -y` dengan output yang dialirkan realtime ke jendela terminal.

---

## Setup Nginx & SSL (Production)

Secara default, dashboard berjalan di HTTP port 8400. Untuk production, gunakan reverse proxy Nginx dengan sertifikat SSL (HTTPS). File template konfigurasi tersedia di folder `deploy/`.

```bash
# 1. Pasang konfigurasi Nginx
sudo cp deploy/nginx/pantau-server.conf /etc/nginx/sites-available/pantau-server
sudo nano /etc/nginx/sites-available/pantau-server   # Ganti server_name dengan domain Anda

# 2. Aktifkan virtual host
sudo ln -s /etc/nginx/sites-available/pantau-server /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 3. Pasang sertifikat SSL Let's Encrypt
sudo certbot --nginx -d pantau.domainanda.com

# 4. Aktifkan secure session cookie di /opt/pantau/server/.env
# Ubah: SESSION_COOKIE_SECURE=True
sudo systemctl restart pantau-server.service
```

---

## Backup, Restore & Data Retention

### Backup & Restore Database
Data metrik dan konfigurasi tersimpan di MariaDB (`pantau_db`) dan file `/opt/pantau/server/.env`.

```bash
# Backup manual database & konfigurasi
sudo mysqldump -u root pantau_db | gzip > pantau_db_$(date +%F).sql.gz
sudo cp /opt/pantau/server/.env .env_$(date +%F)

# Restore database dari file backup
gunzip -c pantau_db_YYYY-MM-DD.sql.gz | sudo mysql -u root pantau_db
sudo systemctl restart pantau-server.service
```

### Policy Retensi Data Otomatis
Daemon background dashboard secara berkala membersihkan data log lama setiap jam agar storage disk tidak membengkak:
- **Raw Metric Snapshot:** 2 hari (agregasi hourly rollups disimpan 90 hari).
- **Log Request Selesai:** 30 hari.
- **Tiket Masalah Selesai (Resolved):** 90 hari.
- **Riwayat Perintah Remote:** 180 hari.
- **Audit Trail User:** 1 tahun (365 hari).

---

## Troubleshooting & FAQ

| Kendala | Penyebab & Solusi |
|---|---|
| Server client berstatus `Offline` | Cek service agent di client: `sudo systemctl status agent_pantau.service`. Pastikan client bisa reach alamat IP server dashboard pada port 8400. |
| Terminal error `403 Forbidden` | Akun Anda tidak memiliki izin terminal (`can_terminal`). Hubungi Master Admin untuk mengaktifkan izin terminal. |
| Terminal error `409 Conflict` | Ada sesi terminal lain yang sedang aktif di server tersebut (hanya 1 sesi aktif per server demi keamanan). |
| Update OS via web macet / lock error | Lock file APT sedang dipakai proses lain di client. Buka Web Terminal dan jalankan `sudo dpkg --configure -a`. |
| Tombol Push OTA tidak muncul | Versi agent di server client sudah sama atau lebih baru dari versi dashboard. |
| Validasi installer gagal / HTTP 403 | Jika server client dan dashboard berada di subnet lokal (LAN/VPN) yang sama, gunakan alamat IP LAN langsung (misal `http://172.30.1.40:8400`) saat installer meminta URL agar koneksi langsung dan bebas hambatan firewall/WAF. |
| Lupa kode 2FA / Handphone hilang | Buka terminal server dashboard dan jalankan perintah: `sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py --username <user> --reset-2fa`. |
