# Pantau Server (v4.1.1)

**Pantau Server** adalah web dashboard monitoring & server management (FastAPI + MariaDB) untuk mengelola banyak server Linux dari satu layar. Dilengkapi dengan **Agent Pantau** (Python) ringan yang berjalan sebagai background daemon service di setiap server client.

Dirancang untuk **Sysadmin, DevOps, dan tim SRE** yang butuh monitoring resource, web terminal root, manajemen service systemd, firewall UFW, cron job, dan audit log tanpa perlu repot membuka banyak terminal SSH.

---

## Daftar Isi
- [Fitur Utama](#fitur-utama)
- [1. Install Dashboard (Server Pusat)](#1-install-dashboard-server-pusat)
- [2. Install Agent (Server Client)](#2-install-agent-server-client)
- [Panduan Menu & Fitur](#panduan-menu--fitur)
- [Role & Hak Akses (RBAC 3-Tier)](#role--hak-akses-rbac-3-tier)
- [Update Dashboard & Agent](#update-dashboard--agent)
- [Web Terminal & Remote Command](#web-terminal--remote-command)
- [Setup Nginx & SSL (Production)](#setup-nginx--ssl-production)
- [Backup, Restore & Data Retention](#backup-restore--data-retention)
- [Troubleshooting & FAQ](#troubleshooting--faq)

---

## Fitur Utama

- **Realtime Server Monitoring**: Pantau CPU, RAM, Swap, Disk I/O, Load Average, dan bandwidth network tanpa reload browser (live polling).
- **Service & Process Control**: Start, Stop, Restart service systemd, kill process pemakan resource, dan auto-unignore saat service pulih via SSH.
- **Web Terminal Terintegrasi (xterm.js)**: Terminal shell root interaktif langsung di browser. Mendukung full ANSI color, shortcut bash, nano, htop, dan mode full screen.
- **Web File Manager**: Browse directory, edit file config (auto-backup `.bak`), upload, download, serta chmod/chown dengan proteksi path sistem kritis.
- **Alert & Incident Tracking**: Notifikasi otomatis saat CPU/RAM spike, disk penuh, atau service down, lengkap dengan opsi Mute/Silence dan ack handling.
- **Security & User Management (RBAC)**: Pembagian hak akses 3-tier (Master Admin, Operator dengan wewenang sudo, Viewer), 2FA TOTP (Google Authenticator), recovery code, dan audit trail per operator.
- **Host Management Suite**: Manajemen user Linux (add, lock, unlock), cron job, listening port (kill/block via UFW), dan tracking expired sertifikat SSL.
- **One-Click OTA Agent Update**: Push update agent ke seluruh client langsung dari dashboard dengan verifikasi hash SHA-256 dan auto-restart systemd.

---

## 1. Install Dashboard (Server Pusat)

Jalankan perintah ini di server Linux (Ubuntu/Debian) yang akan dijadikan pusat dashboard:

```bash
# Update paket & pasang dependensi
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

# Clone repository & jalankan installer
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Installer otomatis membuat system user `pantau`, database MariaDB, file service systemd (`pantau-server.service`), dan meminta input password untuk admin awal.

Setelah selesai, buka di browser: `http://<IP-SERVER>:8400`
- **Username:** `admin`
- **Password:** password yang dibuat saat instalasi

**Reset password admin via terminal (jika lupa):**
```bash
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password '<password-baru>'
```

**Cek status service dashboard:**
```bash
sudo systemctl status pantau-server.service
```

---

## 2. Install Agent (Server Client)

Agent tidak membutuhkan port inbound (tidak perlu buka port SSH ke arah client). Agent aktif melapor keluar (*outbound pull*) ke dashboard setiap 5–10 detik via HTTP POST, sehingga aman di balik NAT atau firewall ketat.

1. Buka dashboard: Masuk ke menu **Servers → Tambah Server**, lalu copy **API Key** yang muncul.
2. Di server client yang mau dimonitor, jalankan script installer:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh "http://<IP-DASHBOARD>:8400" "<API_KEY>"
```

*Jika dijalankan tanpa parameter, script akan meminta input URL dashboard dan API Key secara interaktif.*

Dalam ±10 detik, server client otomatis muncul dengan status online di dashboard.

**Cek status service dan log agent di client:**
```bash
sudo systemctl status agent_pantau.service
sudo journalctl -u agent_pantau -f
```

---

## Panduan Menu & Fitur

### 1. Dashboard Utama
Halaman ringkasan status armada server:
- Counter server (Online / Offline), total service down, dan rata-rata load.
- Tabel daftar server dengan status metrik live, tombol copy IP, search instan, dan sorting kolom.

### 2. Servers
Manajemen pendaftaran server client:
- Tambah server baru (generate API key).
- Edit metadata server (hostname, IP, ambang batas alert CPU/RAM/Disk).
- Hapus server dari pemantauan.

### 3. Detail Server
Panel kontrol lengkap untuk satu server client:
- **Tab Riwayat**: Grafik visual CPU, RAM, Swap, Disk I/O, Load Average, dan Disk per mount point dengan rentang waktu 1 jam s/d 30 hari.
- **Tab Service**: Manajemen service systemd (Start, Stop, Restart, Add Service). Menggunakan *Optimistic UI* dan *fast-polling* sehingga status tombol langsung sinkron tanpa delay.
- **Tab Masalah**: Daftar insiden dan alert aktif realtime. Tersedia tombol mitigasi cepat, opsi Mute (2 jam, 24 jam, atau permanen), tombol Ack/Resolve, dan *auto-unignore* cerdas saat service dihidupkan manual via SSH.
- **Tab ⚡ Top Process**: Snapshot realtime 20 proses pemakan CPU & RAM tertinggi dengan opsi kill process (*SIGTERM* / *SIGKILL*).
- **Tab Jaringan**: Daftar interface network (eth0, ens3, dll.), IP address (IPv4/IPv6), status link, dan traffic throughput (KB/s / MB/s).
- **Tab User Host**: Daftar user lokal sistem Linux, status locked/unlocked, riwayat login SSH, dan log aktivitas sudo.
- **Tab Port & Firewall**: Daftar port listening (TCP/UDP), process owner, serta tombol block IP/port instan via UFW.
- **Tab SSL**: Pantau masa aktif sertifikat SSL/TLS domain lokal beserta peringatan dini sebelum kedaluwarsa.
- **Tab Cron Job**: Monitor dan kelola crontab sistem (tambah, enable/disable, run now, delete).
- **Tab Log**: Log viewer gabungan (system log dan service journald) dengan filter teks dan download file log.
- **Tombol >_ Terminal**: Buka web terminal shell root interaktif.
- **Tombol 📁 File Manager**: Buka remote file explorer untuk edit file konfigurasi, upload, dan download.
- **Tombol 🔧 Maintenance**: Mute semua alert sementara saat server sedang diperbaiki atau di-reboot.

### 4. Profil & Keamanan (User Management)
Pusat pengaturan akun dan hak akses:
- **Pengaturan Akun**: Ganti password pribadi, aktifkan 2FA TOTP (Google Authenticator), simpan recovery code, dan regenerate backup code baru.
- **Manajemen User (Master Admin / Operator Sudo)**: Tambah akun operator/viewer baru, atur matriks izin granular, reset password user lain, lock/unlock user, dan intip riwayat aktivitas (*user activity audit trail*).

---

## Role & Hak Akses (RBAC 3-Tier)

Pantau Server menerapkan sistem hak akses 3 tingkatan dengan konsep delegasi mirip perintah `sudo` di Linux:

1. **Master Admin**: Pemegang wewenang tertinggi setara *root*. Akun kebal (tidak bisa dihapus, di-lock, atau diturunkan haknya). Memiliki akses penuh ke seluruh server, terminal, file manager, dan pengaturan izin user lain.
2. **Operator (Wewenang Sudo)**: Akun teknisi/sysadmin harian. Master Admin dapat memberikan hak akses spesifik secara fleksibel (misal: hanya boleh kelola service dan buka terminal, tapi dilarang menghapus server).
   - **Zero-Knowledge**: Operator sama sekali tidak bisa melihat keberadaan akun Master Admin (informasi dan counter Master Admin disembunyikan).
3. **Viewer**: Akun pengawas baca-saja (*read-only*). Hanya bisa memantau metrik tanpa tombol aksi apapun. Terisolasi total dari info akun admin dan tidak punya akses ke menu Profil.

| Fitur / Tindakan | Master Admin | Operator (Sudo) | Viewer |
|---|:---:|:---:|:---:|
| Akses Dashboard, Metrik & Log | Ya | Ya | Ya |
| Kelola Server & Service (Start/Stop/Restart) | Ya | Sesuai Izin | Tidak |
| Buka Web Terminal & File Manager | Ya | Sesuai Izin | Tidak |
| Reboot, Power Off & Update OS (APT) | Ya | Sesuai Izin | Tidak |
| Atur Firewall (UFW) & Block/Unblock IP | Ya | Sesuai Izin | Tidak |
| User Management (Tambah, Edit, Lock User) | Ya | Sesuai Izin | Tidak |
| Hapus / Edit Akun Master Admin | Ya (Personal) | Ditolak Mutlak | Tidak |
| Akses Profil Pribadi & Setup 2FA | Ya | Ya | Tidak |

---

## Update Dashboard & Agent

### 1. Update Dashboard
Jalankan di server dashboard:
```bash
cd /opt/pantau/server/pantau-server   # sesuaikan dengan path clone Anda
git pull
sudo bash install-server.sh
```
*Script updater aman dijalankan ulang: konfigurasi `.env` dan database MariaDB tidak akan terhapus.*

### 2. Update Agent via Dashboard (Push OTA) [Direkomendasikan]
Jika ada server client yang versi agent-nya lebih lama dari dashboard, banner kuning akan otomatis muncul di halaman detail server:
1. Klik tombol **`⚡ Push Update (OTA)`**.
2. Dashboard mengirim perintah update beserta URL file dan hash SHA-256 resmi.
3. Agent memverifikasi hash SHA-256, menguji sintaks script (`py_compile`), menimpa file `/opt/pantau/agent/agent_pantau.py` secara aman (`chmod 0755`), dan me-restart dirinya sendiri via systemd watchdog.
4. Status update langsung tercatat di Audit Trail.

### 3. Update Agent Manual di Client (One-Liner)
Jalankan di server client via terminal/SSH:
```bash
sudo curl -fsSL -o /opt/pantau/agent/agent_pantau.py \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/opt/pantau/agent/agent_pantau.py && \
sudo systemctl restart agent_pantau.service
```

---

## Web Terminal & Remote Command

Web Terminal menghubungkan browser langsung ke sesi Pseudo-Terminal (PTY) Linux `/bin/bash` di server client via WebSocket bridge.

- **Karakteristik Shell:** Mendukung pipeline (`|`), redirection (`>`), auto-completion tombol `Tab`, navigasi kursor, signal `Ctrl+C` asli, editor teks (`nano`/`vim`), serta viewer interaktif (`htop`).
- **Keamanan:** Berjalan sebagai user `root` melalui wrapper ketat `sudo /usr/local/sbin/pantau-shell` (dikonfigurasi via `/etc/sudoers.d/pantau-agent`).
- **Privasi:** Riwayat perintah tidak disimpan ke disk (`HISTFILE=/dev/null`). Sesi idle otomatis ditutup setelah 8 jam.
- **Audit Trail:** Setiap aktivitas pembukaan dan penutupan terminal dicatat lengkap dengan timestamp, username, dan IP di Audit Trail.
- **Update OS (APT):** Tombol *Update OS* di dashboard menjalankan `apt update` & `apt upgrade -y` dengan output yang dialirkan realtime ke jendela terminal.

---

## Setup Nginx & SSL (Production)

Secara default, dashboard berjalan di HTTP port 8400. Untuk production, gunakan reverse proxy Nginx dengan sertifikat SSL (HTTPS). File konfigurasi siap pakai tersedia di folder `deploy/`.

```bash
# 1. Salin konfigurasi Nginx
sudo cp deploy/nginx/pantau-server.conf /etc/nginx/sites-available/pantau-server
sudo nano /etc/nginx/sites-available/pantau-server   # Ganti server_name dengan domain Anda

# 2. Aktifkan virtual host
sudo ln -s /etc/nginx/sites-available/pantau-server /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 3. Pasang SSL gratis Let's Encrypt
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
- **Raw Metric Snapshot**: Disimpan 2 hari (agregasi hourly rollups disimpan 90 hari).
- **Log Request Selesai**: 30 hari.
- **Tiket Masalah Selesai (Resolved)**: 90 hari.
- **Riwayat Perintah Remote**: 180 hari.
- **Audit Trail User**: 1 tahun (365 hari).

---

## Troubleshooting & FAQ

| Kendala | Penyebab & Solusi |
|---|---|
| Server client berstatus `Offline` | Cek apakah service agent berjalan di client: `sudo systemctl status agent_pantau.service`. Pastikan client bisa ping/curl ke alamat IP server dashboard pada port 8400. |
| Terminal error `403 Forbidden` | Akun login Anda tidak memiliki izin terminal (`can_terminal`). Minta Master Admin mengaktifkan izin terminal untuk user Anda. |
| Terminal error `409 Conflict` | Ada sesi terminal lain yang sedang aktif di server tersebut (hanya 1 sesi aktif per server untuk alasan keamanan). |
| Update OS via web macet / lock error | Lock file APT sedang dipakai proses lain di client. Buka Web Terminal dan jalankan `sudo dpkg --configure -a`. |
| Tombol Push OTA tidak muncul | Versi agent di server client sudah sama atau lebih baru dari versi dashboard saat ini. |
| Lupa kode 2FA / Handphone hilang | Buka terminal server dashboard dan jalankan perintah: `sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py --username <user> --reset-2fa`. |
