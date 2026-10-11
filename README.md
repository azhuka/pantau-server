# Pantau Server

Dashboard monitoring terpusat (FastAPI + MariaDB) untuk memantau kondisi,
kinerja, log, dan keamanan multi-server dari satu antarmuka web, dilengkapi
dengan **agent Pantau** (Python) ringan yang berjalan sebagai daemon di setiap server client.

## Daftar Isi

- [1. Install Dashboard](#1-install-dashboard-server-web-app-pantau-server)
- [2. Install Agent di Server Client](#2-install-agent-di-server-client)
- [Halaman & Fitur](#halaman--fitur)
- [Role User & Wewenang (Master Admin, Operator, Viewer)](#role-user--wewenang-master-admin-operator-viewer)
- [Update Dashboard](#update-dashboard)
- [Update Agent](#update-agent)
- [Kompatibilitas Versi Agent](#kompatibilitas-versi-agent)
- [Terminal Bawaan & Update OS](#terminal-bawaan--update-os-dari-dashboard)
- [Troubleshooting & Batasan Terminal](#troubleshooting--batasan-terminal)
- [HTTPS & Environment Production](#https--environment-production)
- [Backup, Restore & Retensi Data](#backup-restore--retensi-data)
- [Catatan Keamanan & Best Practices](#catatan-keamanan--best-practices)

---

## 1. Install Dashboard (Server Web App "Pantau Server")

Jalankan perintah berikut pada server yang akan dijadikan pusat monitoring:

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Script installer akan membuat system user, database MariaDB (dengan kredensial aman), file service systemd, serta meminta password untuk akun admin awal.

Setelah instalasi selesai, buka browser ke alamat `http://<ip-dashboard>:8400` dan login menggunakan:

- **Username:** `admin`
- **Password:** password yang Anda tentukan saat instalasi

Jika lupa password, Anda dapat me-reset langsung dari server dashboard via CLI:

```bash
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password '<password-baru>'
```

Cek status service dashboard:
```bash
systemctl status pantau-server.service
```

---

## 2. Install Agent di Server Client

1. Buka dashboard: masuk ke menu **Servers → Tambah Server**, lalu copy **API Key** yang digenerate.
2. Di server client (target monitoring), jalankan script installer:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Installer akan meminta URL dashboard dan API Key (64 karakter hex), memverifikasi kunci ke dashboard, memasang service agent, dan mengaktifkannya secara otomatis. Dalam ±10 detik, server client akan muncul dengan status online di dashboard.

Instalasi non-interaktif juga dapat dijalankan langsung dengan argumen:
```bash
sudo bash /tmp/pantau-install.sh "http://<ip-dashboard>:8400" "<API_KEY>"
# atau menggunakan environment variables:
sudo SETUP_SERVER_URL="http://<ip-dashboard>:8400" SETUP_API_KEY="<API_KEY>" bash /tmp/pantau-install.sh
```

Cek status service dan log agent:
```bash
systemctl status agent_pantau.service
journalctl -u agent_pantau -f
```

> **Catatan:** Instalasi via `curl | bash` hanya mengunduh file agent dan script wrapper tanpa meng-clone seluruh repositori git ke server client.

---

## Halaman & Fitur

| Halaman | Deskripsi & Fungsi |
|---|---|
| **Dashboard** | Overview status seluruh server secara terpusat: counter server online/offline, service down, utilisasi CPU & RAM, serta waktu report terakhir. Dilengkapi live polling, sorting kolom, instant search, dan tombol copy IP address. |
| **Servers** | Manajemen server client: status online/offline, registrasi server baru, edit server, delete, manajemen API key, dan tabel dinamis. |
| **Detail Server** | Pusat kontrol dan inspeksi per server: <br>• **Tab Riwayat:** Grafik historis CPU, Memory, Swap, Load Average, dan Disk per mount point dengan area gradient glow, statistik avg/max, dan filter time-range.<br>• **Tab Service:** Manajemen service systemd dan process (Start, Stop, Restart, Add Service baru) dengan Optimistic UI dan fast-polling cascade.<br>• **Tab Masalah:** List alert dan insiden aktif realtime, tombol mitigasi/restart cepat, opsi Mute/Ignore (durasi atau permanen), auto-unignore saat service pulih via SSH, serta tombol konfirmasi penanganan (ack/resolve) in-place.<br>• **Tab ⚡ Top Process:** Snapshot realtime proses pemakan CPU & RAM tertinggi (default 5 proses, expandable ke 20 proses).<br>• **Tab Jaringan:** Daftar interface network, IP address aktif (IPv4 & IPv6), link status, dan data throughput (KB/s / MB/s).<br>• **Tab User:** List local user Linux, status user terkunci, audit riwayat login SSH, dan log eksekusi sudo.<br>• **Tab Log:** Log viewer terintegrasi (system log & service journald), filter teks, penandaan severity error/warning, dan download log file.<br>• **Maintenance Mode:** Tombol `🔧 Pemeliharaan` untuk mute alert sementara saat server sedang maintenance/reboot.<br>• **Terminal Bawaan:** Akses shell remote interactive langsung dari browser via tombol `>_ Terminal`, lengkap dengan Full Screen.<br>• **File Manager:** Remote file explorer server client via tombol `📁 File Manager ↗`. |
| **File Manager** | *(Khusus Admin / Operator berizin)* Halaman terdedikasi (`/servers/{id}/files`) untuk browsing directory, edit file teks (auto backup `.bak`), buat file/folder baru, upload/download file, serta chmod/chown berpagar proteksi path sistem kritis. |
| **Masalah** | Rekapitulasi seluruh alert dan insiden aktif lintas server, filter per server, filter severity (Danger, Warning, Info, Diabaikan), opsi Mute/Silence, ack handling, dan petunjuk rekomendasi perbaikan. |
| **Log** | Centralized log inspection: resource usage log, riwayat proses, unit service log, dan application audit log. |
| **Audit** | Audit trail menyeluruh atas setiap aksi administratif: login/logout, buka sesi terminal, modifikasi konfigurasi server/service/user, remote command execution, dan OTA agent update. |
| **Profil & Keamanan** | Halaman terpadu untuk setting akun personal (ganti password, 2FA TOTP RFC 6238, regenerate backup code) serta User Management terpusat (khusus Master Admin & Operator berizin): add user, delegasi izin sudo granular, edit kredensial, lock/unlock user, audit aktivitas operator, dan force logout session aktif. |

Indikator warna status badge:
- **Hijau:** Normal / Sehat / Sukses.
- **Merah:** Critical alert / Service down / Error.
- **Kuning:** Warning / Mendekati threshold / Butuh perhatian.
- **Biru:** Info status.
- **Abu-abu:** Netral / Offline / Menunggu report data.

---

## Role User & Wewenang (Master Admin, Operator, Viewer)

Pantau Server menerapkan arsitektur otorisasi **RBAC 3-Tier** dengan prinsip isolasi hierarki ketat dan pendelegasian wewenang mirip model *sudo* di Linux:

1. **Master Admin**: Pemegang otoritas tertinggi sistem dengan proteksi akun mutlak. Operator manapun tidak dapat menghapus atau menurunkan hak akses Master Admin. Memiliki hak penuh untuk konfigurasi server, terminal, file manager, dan delegasi izin operator.
2. **Operator (Wewenang Terdelegasi / Sudo)**: Akun operasional harian tim sysadmin/SRE. Master Admin dapat mendelegasikan wewenang spesifik secara granular tanpa harus membagikan password Master Admin. Mematuhi prinsip zero-knowledge: Operator **tidak dapat melihat atau mengetahui keberadaan akun Master Admin**.
3. **Viewer**: Akun pengawas baca-saja (*read-only*). Terisolasi penuh: Viewer **tidak dapat melihat akun Master Admin maupun Operator**, serta **tidak memiliki akses ke menu Profil & Keamanan**. Seluruh kredensial akun Viewer dikelola oleh Master Admin atau Operator yang berwenang.

| Hak Akses / Tindakan | Master Admin | Operator (Sudo / Delegasi) | Viewer |
|---|:---:|:---:|:---:|
| Akses Dashboard, Servers, Detail, Masalah, dan Log | Ya | Ya | Ya |
| Tambah, edit, dan hapus server & service | Ya | Sesuai Izin Granular | Tidak |
| Start, Stop, dan Restart service | Ya | Sesuai Izin Granular | Tidak |
| Update OS, Upgrade Paket, Reboot, dan Power Off | Ya | Sesuai Izin Granular | Tidak |
| Membuka dan menggunakan Web Terminal | Ya | Sesuai Izin Granular | Tidak |
| Akses File Manager (baca, edit, download, upload) | Ya | Sesuai Izin Granular | Tidak |
| Block IP via UFW / Mitigasi insiden | Ya | Sesuai Izin Granular | Tidak |
| Akses halaman Audit Trail Sistem | Ya | Sesuai Izin Granular | Tidak |
| User Management (Tambah user, Edit izin, Lock user) | Ya | Sesuai Izin Granular | Tidak |
| Mengubah / Menghapus Akun Master Admin | Ya (Personal) | Ditolak Mutlak | Tidak |
| Akses Menu Profil & Keamanan (2FA & Ganti Password) | Ya | Ya | Tidak |

---

## Update Dashboard

Untuk mengupdate dashboard ke versi terbaru:

```bash
cd /path/ke/pantau-server
git pull
sudo bash install-server.sh
```

Script updater aman dijalankan ulang: file konfigurasi `.env` (termasuk kredensial database) tetap dipertahankan, dependensi Python diperbarui, dan migrasi schema database diterapkan secara otomatis.

---

## Update Agent

Pusat Dashboard tidak membutuhkan koneksi SSH inbound ke server client. Komunikasi berjalan melalui agent yang melapor secara periodik via HTTP POST. Update agent dapat dilakukan via dashboard atau manual di server client:

### 1. Update Otomatis via Dashboard (OTA - Over-The-Air) [Direkomendasikan]

Dashboard menyediakan fitur **Push Update (OTA)**:
- Ketika versi agent di server client lebih lama dibanding dashboard, banner kuning akan muncul otomatis dengan tombol **`⚡ Push Update (OTA)`**.
- Klik tombol tersebut, dashboard akan mengirimkan URL kode agent terbaru beserta hash **SHA-256** dan target versi ke agent.
- Agent memverifikasi hash SHA-256 secara ketat, menguji validasi sintaks Python (`py_compile`), mengganti file `/opt/pantau/agent/agent_pantau.py` secara atomik (`chmod 0755`), lalu me-restart service agent secara otomatis via systemd watchdog.
- Riwayat eksekusi dan log update dicatat ke **Audit Trail** dan tabel **Riwayat Tindakan** server.

### 2. Update Manual via Terminal Client

Jalankan perintah berikut di terminal server client:

```bash
sudo curl -fsSL -o /opt/pantau/agent/agent_pantau.py https://raw.githubusercontent.com/azhuka/pantau-server/master/package/opt/pantau/agent/agent_pantau.py && sudo systemctl restart agent_pantau.service
```

File konfigurasi di `/etc/pantau/config.json` tidak akan tertimpa.

### Update Agent pada Host Dashboard Sendiri

Jika server dashboard juga dimonitor oleh agent lokal:

```bash
cd pantau-server
sudo install -m 755 -o root -g root package/opt/pantau/agent/agent_pantau.py /opt/pantau/agent/agent_pantau.py
for wr in pantau-restart pantau-history pantau-firewall pantau-host pantau-apt pantau-shell pantau-file pantau-user pantau-cron pantau-ssl; do
  sudo install -m 750 -o root -g root package/usr/local/sbin/$wr /usr/local/sbin/$wr
done
sudo cp package/etc/sudoers.d/pantau-agent /etc/sudoers.d/pantau-agent
sudo chmod 440 /etc/sudoers.d/pantau-agent
sudo python3 -m py_compile /opt/pantau/agent/agent_pantau.py
sudo systemctl restart agent_pantau.service
```

### Verifikasi Setelah Update

Setelah service agent di-restart (metrik historis tidak akan hilang):
1. Label versi agent di halaman Detail Server akan terupdate menjadi `agen v4.1.1`.
2. Server kembali heartbeat dalam ±10 detik.
3. Tab **⚡ Top Process** menampilkan snapshot proses secara realtime.

---

## Kompatibilitas Versi Agent

Sangat disarankan menyelaraskan versi agent dengan versi dashboard (**v4.1.1**) agar seluruh kapabilitas beroperasi optimal:

| Fitur | Versi Agent Minimum |
|---|:---:|
| Monitoring metrik dasar, grafik riwayat, log, dan manajemen service | v3.6+ |
| Reboot OS dan Power Off remote | v3.6+ |
| Update OS & Upgrade paket (APT) | v3.7+ |
| Web Terminal Realtime (xterm.js + WebSocket Streaming) | v3.14+ |
| Snapshot Top 20 Proses & Mode Pemeliharaan (*Maintenance Mode*) | v3.15.0+ |
| Socket Activation (SSH safe shutdown) & Mute Service | v3.16.0+ |
| Disk I/O Throughput, Journal Error Tracking, Cron Jobs, Port Audit & SSL Expiry | v3.17.0+ |
| Manajemen Interaktif User Linux, Cron, Port (Kill/Block), Custom SSL Path | v3.23.0+ |
| Arsitektur RBAC 3-Tier, 2FA TOTP, Optimistic UI & Auto-Unignore Service Recovery | v4.1.1+ |

Query database untuk cek sebaran versi agent pada seluruh server client:

```sql
SELECT s.hostname, x.agent_version
FROM servers s
LEFT JOIN server_extras x ON x.server_id = s.id
ORDER BY x.agent_version, s.hostname;
```

---

## Terminal Bawaan & Update OS dari Dashboard

Halaman Detail Server menyediakan fasilitas **Web Terminal**: interactive Linux shell di server client, didukung emulator **xterm.js** pada sisi browser dan komunikasi streaming **WebSocket** dua arah ke agent client.

### Diagram Arsitektur Terminal

```
Browser Client (Detail Server)
   │  WebSocket: ws[s]://<host>/ws/servers/{id}/terminal (Autentikasi Session Admin)
   │  Render via xterm.js + FitAddon
   ▼
Dashboard FastAPI (TerminalBridgeDispatcher)
   │  Long-poll stream bridge (memory queue)
   ▼
Agent Pantau (Server Client)
   │  pty.openpty() + alokasi kontrol PTY asli Linux
   │  sudo -n /usr/local/sbin/pantau-shell
   ▼
/bin/bash --noprofile --rcfile <custom_rc> -i  →  root@<hostname>:~#
```

Fitur Web Terminal:
- **Dukungan Perintah Penuh:** Mendukung command interaktif (`htop`, `vim`, `nano`, `docker`, `systemctl`, `journalctl`), pipeline (`|`), dan redirection (`>`, `>>`).
- **Penyuntingan Baris Bash:** Navigasi panah, `Backspace`, `Home`, `End`, serta shortcut bash (`Ctrl+A`, `Ctrl+E`, `Ctrl+U`, `Ctrl+W`).
- **Sinyal Sistem Asli:** `Ctrl+C` mengirim sinyal `SIGINT` nyata ke proses yang sedang berjalan.
- **Auto-Completion:** Tombol `Tab` menjalankan auto-complete bawaan bash.
- **Clear Screen:** Tombol **Clear** atau perintah `clear` (`Ctrl+L`).
- **Full Screen Mode:** Tombol **Full Screen** dan shortcut `Esc` untuk tampilan 100% monitor dengan auto-fit kolom & baris.
- **Riwayat Perintah:** Menggunakan panah atas/bawah `↑` / `↓` dalam sesi aktif (riwayat sesi tidak disimpan ke disk demi privasi).

### Keamanan & Batasan Terminal

Sesi terminal berjalan sebagai user `root` melalui script wrapper khusus:

| Parameter | Ketentuan |
|---|---|
| Otorisasi | Khusus **Master Admin** atau Operator dengan izin `can_terminal`. Role Viewer ditolak (`403 Forbidden`). |
| Jumlah Sesi Aktif | Maksimal **satu** sesi aktif per server. Request sesi kedua akan ditolak (`409 Conflict`). |
| Wrapper Shell | Dijalankan via `sudo /usr/local/sbin/pantau-shell` berdasarkan konfigurasi `/etc/sudoers.d/pantau-agent`. |
| History File | Dinonaktifkan (`HISTFILE=/dev/null`) agar tidak meninggalkan jejak `.bash_history`. |
| Audit Trail | Seluruh event open/close terminal dicatat di menu **Audit** dashboard (`terminal_shell_open`) dan syslog server client (`pantau-shell`). |
| Timeout Sesi | Sesi idle terputus otomatis setelah 8 jam. |

### Operasi Update OS dan Upgrade Paket

Operasi maintenance paket APT via dashboard mengeksekusi operasi APT terisolasi (`apt update`, `apt upgrade`, `apt dist-upgrade`, `dpkg --configure -a`):
1. Output proses di-stream realtime ke jendela Terminal Bawaan.
2. Prompt interaktif (seperti konfirmasi `Y/n` atau pemilihan config file) dapat direspons langsung di terminal.
3. Setelah proses selesai, ringkasan hasil ditampilkan dan kontrol dikembalikan ke shell prompt.

---

## Troubleshooting & Batasan Terminal

| Gejala Kendala | Langkah Penanganan |
|---|---|
| Update menampilkan `Gagal — batas waktu habis` | Tunggu jeda proteksi 2 menit, lalu refresh browser. Dashboard otomatis mengecek proses background yang masih berjalan. |
| Operasi `apt update` memakan waktu > 5 menit | Cek konektivitas internet atau mirror repository APT pada server client. |
| Operasi `upgrade` berjalan lama | Upgrade paket kernel/distro membutuhkan waktu lebih lama. Buka Terminal Bawaan untuk melihat kompilasi/instalasi realtime. |
| Proses interaktif menunggu input | Buka Terminal Bawaan, lalu berikan input teks atau tekan `Enter`. |
| Lock file `dpkg` terkunci atau proses interrupt | Jalankan repair `dpkg --configure -a` via terminal atau tombol perbaikan dashboard. |
| Terminal error `403` atau `409` | Kode `403`: akun Anda tidak memiliki hak terminal. Kode `409`: terdapat sesi terminal lain yang aktif di server tersebut. |

### Kapan Membutuhkan SSH Langsung?

Sebagian besar routine task dapat diselesaikan lewat dashboard. Namun, akses SSH langsung tetap diwajibkan untuk:
1. **Major Distribution Upgrade:** Migrasi OS besar (misalnya Debian 11 ke Debian 12, atau Ubuntu 22.04 ke 24.04) yang merestart interface network atau core system.
2. **Dialog Menu TUI Kompleks (ncurses):** Menu debconf layar biru kompleks yang memerlukan kursor grafis khusus atau input mouse.
3. **Network Failure Total:** Kondisi ketika server client offline atau kehilangan koneksi jaringan keluar sehingga agent tidak dapat menghubungi dashboard.

---

## HTTPS & Environment Production

Secara default, dashboard berjalan menggunakan HTTP pada port 8400. Untuk production environment, disarankan menggunakan reverse proxy Nginx dengan SSL (HTTPS).

File template konfigurasi yang tersedia di repository:
- **Konfigurasi Nginx:** `deploy/nginx/pantau-server.conf` (TLS 1.3, Let's Encrypt, buffer upload 50MB untuk File Manager, dan **WebSocket Upgrade** untuk terminal realtime).
- **Konfigurasi Logrotate:** `deploy/logrotate/pantau-server` (rotasi log harian Uvicorn).

### Langkah Setup Nginx & SSL:

1. Pasang konfigurasi Nginx:
   ```bash
   sudo cp deploy/nginx/pantau-server.conf /etc/nginx/sites-available/pantau-server
   sudo nano /etc/nginx/sites-available/pantau-server
   # Sesuaikan server_name dengan domain Anda

   sudo ln -s /etc/nginx/sites-available/pantau-server /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```

2. Pasang sertifikat SSL via Certbot:
   ```bash
   sudo certbot --nginx -d pantau.example.com
   ```

3. Aktifkan secure cookie pada `/opt/pantau/server/.env`:
   ```env
   SESSION_COOKIE_SECURE=True
   ```
   Lalu restart service dashboard:
   ```bash
   sudo systemctl restart pantau-server
   ```

4. Pasang konfigurasi logrotate:
   ```bash
   sudo cp deploy/logrotate/pantau-server /etc/logrotate.d/pantau-server
   ```

---

## Backup, Restore & Retensi Data

Data tersimpan di database MariaDB (`pantau_db`) dan file konfigurasi `/opt/pantau/server/.env`.

### Prosedur Backup & Restore:

```bash
# Backup Database & Konfigurasi
sudo mysqldump -u root pantau_db | gzip > pantau_db-$(date +%F).sql.gz
sudo cp /opt/pantau/server/.env ".env-$(date +%F)"

# Restore Database
gunzip -c pantau_db-YYYY-MM-DD.sql.gz | sudo mysql -u root pantau_db
sudo systemctl restart pantau-server
```

### Policy Retensi Data Otomatis:

Daemon background dashboard secara berkala setiap jam melakukan pruning data historis untuk menghemat disk storage:
- **Login attempts & rate limit:** 1 hari.
- **Raw system snapshots:** 2 hari (hourly rollup disimpan 90 hari).
- **Completed request log:** 30 hari.
- **Resolved problems (tiket selesai):** 90 hari.
- **Command execution history:** 180 hari.
- **Audit trail logs:** 1 tahun (365 hari).

---

## Catatan Keamanan & Best Practices

- **CSRF Protection:** Seluruh form POST dan request AJAX dilindungi token CSRF berbasis HMAC-SHA256 yang divalidasi ketat pada backend.
- **Data Sanitization:** Semua payload dari agent (disk, network, process list, output terminal, dan log) disanitasi sebelum disimpan atau dirender ke browser guna mencegah XSS (*Cross-Site Scripting*).
- **Credential Storage:** API Key disimpan dalam bentuk hash SHA-256; password user di-hash menggunakan algoritma bcrypt.
- **Principle of Least Privilege:** Izin `sudo` agent dibatasi presisi hanya pada script wrapper di `/etc/sudoers.d/pantau-agent`. Operasi service dilindungi deny-list untuk mencegah restart service kritis yang tidak disengaja.
- **Konfirmasi Tindakan Berisiko:** Operasi destruktif (delete server, reboot, shutdown, block port/IP) selalu mewajibkan konfirmasi eksplisit dari user.
- **HTTP Security Headers:** Sistem mengaktifkan CSP, X-Frame-Options (DENY), X-Content-Type-Options (nosniff), Referrer-Policy, dan penanganan IP reverse proxy terpercaya.
- **Standar Waktu UTC:** Seluruh timestamp dicatat dan disajikan dalam format UTC agar konsisten lintas timezone server yang dimonitor.
- **Isolasi Jaringan:** Jangan mengekspos port 8400 langsung ke internet publik tanpa proteksi reverse proxy Nginx dan sertifikat SSL.
