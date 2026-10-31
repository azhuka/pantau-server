# Pantau-Server

**Pantau-Server** adalah platform pemantauan (*monitoring*) dan manajemen armada server Linux berbasis web yang dirancang khusus untuk Sysadmin, DevOps, dan tim operasional NOC. Menggabungkan telemetri performa berdensitas tinggi secara *real-time* dengan kemampuan eksekusi kontrol sistem langsung (*actionable dashboard*) dari satu antarmuka terpusat.

Arsitektur sistem dibangun menggunakan backend **FastAPI + MariaDB** pada server pusat serta **Daemon Agent Python mandiri (*Zero-Dependency*)** pada setiap server klien.

---

## Alasan Pengembangan Aplikasi Pantau-Server?

Mengelola puluhan hingga ratusan server Linux di berbagai lingkungan (baremetal, VPS, cloud, atau on-premise) seringkali menghadapi tantangan umum:

1. **Stack Monitoring Terlalu Berat & Rumit:** Solusi pada alat monitoring konvensional lain membutuhkan konfigurasi yang kompleks, *resource footprint* yang besar di klien, serta waktu setup yang lama dan rumit hanya untuk memantau metrik dasar.
2. **Dashboard Pasif (Hanya Melihat):** Sebagian besar dashboard monitoring hanya menyajikan grafik metrik. Ketika ada *service* down atau CPU *spike* di tengah malam, Tim IT tetap harus membuka terminal, login SSH manual ke server terkait, dan mencari penyebabnya satu per satu.
3. **Kekurangan Port Inbound & SSH:** Membuka port SSH atau listening port monitoring ke internet pada setiap mesin klien menimbulkan celah keamanan (*attack surface*) yang luas dan rumit dikonfigurasi di balik NAT atau firewall korporat.

**Pantau-Server menyelesaikan masalah tersebut:** Memberikan pemantauan ringan, aman, dan langsung menyertakan alat kendali operasional (Web Terminal, manajemen service, kill process, edit config, kontrol firewall) dalam satu browser.

---

## Topologi Jaringan & Alur Kerja

Pantau-Server mengadopsi model **Outbound-Only Pull**. Agen klien yang aktif mengontak server pusat, sehingga server klien dapat berada di jaringan manapun tanpa perlu membuka port masuk:

```text
[ Server Klien A (AWS Cloud)     ] ----\
[ Server Klien B (Proxmox / LAN) ] -----> [ HTTP/HTTPS POST ] -----> [ Pantau-Server (Pusat) ] <==== Browser Tim IT
[ Server Klien C (Baremetal VPS) ] ----/      (Port 8400)             (FastAPI + MariaDB)        (NOC Dashboard)
```

---

## Apa Perbedaan Pantau-Server dengan Solusi Lain?

| Aspek | Pantau-Server | Monitoring Konvensional | Script SSH Monitoring Ad-Hoc |
| :--- | :--- | :--- | :--- |
| **Koneksi Jaringan** | **Outbound-Only Pull:** Agent mengontak server pusat via HTTP/HTTPS POST. Tidak butuh port masuk terbuka, aman di balik NAT/firewall. | Perlu membuka port inbound agent (misal 9100 / 10050) atau konfigurasi proxy rumit. | Memerlukan port SSH inbound terbuka di seluruh server klien. |
| **Dependensi Agent** | **Zero-Dependency:** Murni pustaka standar Python 3.10+. Tanpa `pip`, tanpa `psutil`, tanpa kompilasi C (`gcc`). | Memerlukan instalasi binary berat, package repository eksternal, atau Node Exporter. | Memerlukan setup SSH key exchange terpusat dengan risiko kredensial bocor. |
| **Aksi Kontrol Sistem** | **Actionable:** Restart service systemd, kill process, edit berkas config, hingga Web Terminal interaktif langsung dari dashboard. | **Read-Only:** Hanya menyajikan metrik dan grafik. Penanganan insiden harus dilakukan di luar aplikasi. | Terbatas pada eksekusi script remote satu arah tanpa UI interaktif. |
| **Resource Footprint** | **Super Ringan:** Agent mengonsumsi RAM < 20 MB dan CPU < 0.5%. Tidak membebani server produksi. | Bervariasi, seringkali memakan resource signifikan pada mesin berspesifikasi kecil. | Ringan, tetapi minim fitur observabilitas dan tidak memiliki histori time-series. |
| **Pembaruan Agent** | **Fleet-Wide OTA Self-Update:** Agent memperbarui dirinya sendiri otomatis saat server pusat di-upgrade (tervalidasi SHA-256). | Memerlukan update manual via package manager atau playbook Ansible di setiap server. | Memerlukan penyalinan script manual ke seluruh server. |
| **Kedaulatan Data** | **100% Self-Hosted:** Seluruh data metrik dan konfigurasi tersimpan lokal. Bebas telemetri pihak ketiga (*zero cloud tracking*). | Berbayar untuk cloud provider, atau butuh cluster database khusus yang berat. | Tersebar di log lokal tanpa enkripsi database terpadu. |

---

## Fitur Utama & Unggulan

### 1. Observabilitas & Telemetri Real-Time
- **Metrik Sistem Real-Time:** Monitoring utilisasi CPU, RAM, Swap, Disk per partisi, Network I/O throughput, Load Average, dan sesi login SSH seketika (detak 5–10 detik tanpa perlu reload halaman).
- **Kesehatan Media Penyimpanan (S.M.A.R.T. & NVMe):** Audit fisik hard drive dan SSD via `smartctl` dan `nvme-cli` (status PASSED/FAILED, estimasi sisa umur/wearout percentage, suhu drive, bad sectors, dan laju pertumbuhan *Storage Runway*).
- **Deteksi Hardware & Virtualisasi Otomatis:** Mengidentifikasi tipe prosesor, core, clock speed, interface jaringan, MAC address, serta platform hypervisor (KVM, Proxmox LXC/QEMU, VMware, AWS, Baremetal).
- **Audit Pembaruan Paket Sistem:** Deteksi otomatis pembaruan sistem dan keamanan yang tertunda di klien (mendukung `apt`, `dnf`/`yum`, dan `pacman`).
- **Pengecekan Integritas Cadangan (Database Backup Watcher):** Audit otomatis berkas dump database (MySQL, MariaDB, PostgreSQL), verifikasi file 0-byte, dan penandaan usia cadangan kadaluwarsa.
- **Pemeriksaan Sertifikat SSL/TLS:** Pemantauan otomatis sisa hari masa aktif sertifikat SSL lokal dan sertifikat web server sebelum kedaluwarsa.
- **Probing Jaringan & Endpoint Terjadwal:** Pengujian berkala konektivitas HTTP/HTTPS (status code & latensi), TCP Port listening, DNS lookup, dan ICMP Ping dari server pusat.

### 2. Tindakan Operasional Langsung (*Actionable NOC*)
- **Manajemen Layanan Systemd:** Mulai (*start*), hentikan (*stop*), restart unit service, dan pantau log journald langsung dari antarmuka web.
- **Task Manager & Manajemen Proses:** Inspeksi proses sistem teratas berdasarkan CPU/RAM dengan opsi terminasi cepat (*SIGTERM* atau *SIGKILL*) yang dilengkapi guardrail proteksi PID sistem kritis.
- **Web Terminal Interaktif (`>_ Terminal`):** Akses shell Linux yang interaktif langsung di browser via WebSocket dan pseudo-terminal (PTY) dengan dukungan penuh warna ANSI, auto-completion, tombol shortcut Bash, htop, serta editor nano/vim.
- **Web File Manager:** Eksplorasi direktori remote, unggah/unduh berkas, ubah permission (*chmod/chown*), serta penyuntingan berkas konfigurasi dengan mekanisme *auto-backup* (`.bak`).
- **Audit Port Listening & Firewall:** Monitoring socket port TCP/UDP yang sedang terbuka beserta proses pemiliknya, serta manajemen blokir/buka blokir IP pada kernel firewall (UFW / iptables).
- **Jendela Pemeliharaan Terjadwal (*Maintenance Windows*):** Fitur penjadwalan pemeliharaan armada server untuk menekan alarm darurat dan banner merah saat tim sedang melakukan pekerjaan terjadwal.

### 3. Keamanan, RBAC & Siklus Hidup Insiden
- **Klasifikasi Insiden Multi-Tier (Tier 1 Utama, Tier 2 Pendukung, Tier 3 Pengujian):** Alarm darurat dan banner merah hanya bereskalasi pada server misi kritis (Tier 1), mencegah kejenuhan alarm (*alert fatigue*).
- **Kontrol Hak Akses 3-Tier (RBAC):** Hak akses terbagi atas *Master Admin*, *Operator* (dengan batasan hak sudo selektif), dan *Viewer* (hanya-baca).
- **Autentikasi Dua Langkah (2FA TOTP):** Proteksi login menggunakan aplikasi autentikator standar (Google Authenticator, Bitwarden, 2FAS).
- **Notifikasi Insiden Terpusat:** Integrasi notifikasi bot Telegram seketika saat terjadi insiden pada server penting.
- **Audit Trail Forensik:** Pencatatan otomatis setiap tindakan administratif (siapa operatornya, aksi yang dijalankan, target server, parameter, dan status output).

---

## Persiapan & Prasyarat Sistem

### Sisi Server Pusat (Dashboard)
- **Sistem Operasi:** Ubuntu 20.04 / 22.04 / 24.04 LTS atau Debian 11 / 12 (arsitektur x86_64 / amd64).
- **Spesifikasi Minimum:** 1 vCPU, RAM 1 GB, Disk kosong 5 GB.
- **Dependensi Sistem:** Python 3.10+, MariaDB Server, Git, Curl.
- **Port Jaringan:** Port `8400` TCP terbuka untuk akses dashboard dan komunikasi masuk dari agent klien (bisa dialihkan ke port `80`/`443` via reverse proxy Nginx).

### Sisi Server Klien (Agent)
- **Sistem Operasi:** Seluruh distribusi Linux modern berbasis systemd:
  - **Debian / Ubuntu:** Ubuntu 20.04+, Debian 10+, Proxmox VE.
  - **RHEL / RPM:** Rocky Linux 8/9, AlmaLinux 8/9, RHEL 8/9, CentOS Stream, Fedora.
  - **SUSE:** openSUSE Leap / Tumbleweed.
  - **Arch:** Arch Linux, Manjaro.
- **Spesifikasi Minimum:** RAM < 20 MB, CPU overhead < 0.5%.
- **Dependensi Software:** Python 3.10+ (standard library bawaan OS), `curl`, `iproute2` / `iproute` (utilitas `ss`), `sudo`, dan `systemd`.
- **Koneksi Jaringan:** Akses keluar (*egress outbound*) HTTP/HTTPS ke IP atau domain Server Pusat. **Sama sekali tidak memerlukan port masuk (inbound) terbuka.**

---

## Panduan Instalasi

### 1. Pemasangan Dashboard (Server Pusat)

Jalankan di server pusat yang akan dijadikan dashboard monitoring:

```bash
# 1. Clone repositori Pantau-Server
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server

# 2. Jalankan skrip installer interaktif
sudo bash install-server.sh
```

Skrip installer akan secara otomatis:
- Menyiapkan user sistem `pantau` dan virtual environment Python.
- Memasang dependensi backend dan menginisialisasi database MariaDB.
- Memasang serta mengaktifkan service systemd `pantau-server.service`.
- Meminta kata sandi awal untuk akun `admin`.
- Akun ini akan menjadi satu-satunya akun yang aktif dan berperan sebagai akun utama (root/master-admin).

Setelah instalasi selesai, buka dashboard melalui peramban:
- **URL Dashboard:** `http://<IP-SERVER-PUSAT>:8400`
- **Username:** `admin`
- **Password:** Kata sandi yang Anda tentukan saat instalasi

---

### 2. Pemasangan Agen (Server Klien yang Dipantau)

Setelah dashboard aktif, daftarkan server klien dengan langkah berikut:

1. Buka dashboard web, masuk ke menu **Daftar Server → Tambah Server**.
2. Masukkan nama server dan pilih kelompok (*group*), lalu klik tombol "Tambah Server" untuk mendapatkan **API Key** (token hex 64 karakter).
3. Salin **API Key** di tempat aman dan sementara untuk disalin kembali pada saat proses instalasi agent pada server klien.
4. Login ke server klien via SSH, lalu jalankan perintah instalasi satu-langkah:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Installer akan meminta input secara interaktif:
- **URL Dashboard:** Masukkan alamat server pusat (contoh: `http://192.168.1.10:8400`).
- **API Key:** Tempelkan API Key yang didapatkan saat proses tambah server pada aplikasi Pantau-Server.

> **Tips Automasi (Mode Non-Interaktif / Ansible / Cloud-Init):**
> Anda dapat langsung memasukkan parameter URL dan API Key dalam satu baris perintah:
> ```bash
> sudo bash /tmp/pantau-install.sh "http://<IP-SERVER-PUSAT>:8400" "<API_KEY>"
> ```

Dalam waktu ±10 detik setelah instalasi selesai, server klien akan otomatis melapor dan berstatus **Online** di dashboard.

---

## Perintah Operasional & Manajemen Layanan

### Server Pusat (Dashboard)
```bash
# Memeriksa status service dashboard
sudo systemctl status pantau-server.service

# Memulai ulang (restart) dashboard
sudo systemctl restart pantau-server.service

# Memantau log aplikasi secara langsung (live log)
sudo journalctl -u pantau-server -f

# Reset kata sandi admin jika lupa
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password 'password-baru'

# Memperbarui aplikasi dashboard ke versi terbaru
cd /opt/pantau/server/pantau-server
git pull && sudo bash install-server.sh
```

### Server Klien (Agent)
```bash
# Memeriksa status service agent
sudo systemctl status agent_pantau.service

# Memantau log aktivitas agent dan heartbeat
sudo journalctl -u agent_pantau -f

# Memulai ulang service agent
sudo systemctl restart agent_pantau.service

# Lokasi berkas konfigurasi agent
sudo cat /etc/pantau/config.json
```

---

## Lokasi Berkas & Direktori Penting

### Pada Server Pusat:
- **Aplikasi & Lingkungan Python:** `/opt/pantau/server/`
- **Berkas Konfigurasi Rahasia (`.env`):** `/opt/pantau/server/.env`
- **Unit Service Systemd:** `/etc/systemd/system/pantau-server.service`

### Pada Server Klien:
- **Daemon Agen:** `/opt/pantau/agent/agent_pantau.py`
- **Berkas Konfigurasi Klien:** `/etc/pantau/config.json`
- **Sudo Wrappers Khusus:** `/usr/local/sbin/pantau-*`
- **Izin Sudo Terbatas:** `/etc/sudoers.d/pantau`
- **Unit Service Systemd:** `/etc/systemd/system/agent_pantau.service`

---

## Hal-Hal Penting yang Perlu Diketahui

### Dari Sisi Server Pusat (Dashboard)
1. **Rekomendasi Lingkungan Produksi (Reverse Proxy Nginx + SSL):**
   Secara bawaan dashboard melayani lalu lintas HTTP pada port 8400. Untuk penggunaan produksi di jaringan publik, sangat disarankan menggunakan Nginx sebagai reverse proxy dengan sertifikat SSL/TLS (Let's Encrypt). Berkas konfigurasi contoh tersedia di `deploy/nginx/pantau-server.conf`.
2. **Keamanan Kredensial Agent:**
   API Key server klien tidak pernah disimpan dalam bentuk teks polos (*plaintext*) pada database server, melainkan di-hash menggunakan algoritma SHA-256 (`sha256:<hash>`).
3. **Pembersihan Data Berkala (Retention Policy):**
   Database MariaDB dilengkapi mekanisme retensi otomatis yang berjalan setiap jam. Data telemetri mentah disimpan selama 24 jam sebelum diagregasi menjadi rata-rata per jam (disimpan 90 hari), sehingga kapasitas media penyimpanan server monitoring tetap terjaga stabil.

### Dari Sisi Server Klien (Agent)
1. **Ketahanan Klien & Nol Dampak (*Fault Tolerance*):**
   Jika server pusat sedang mati, restart, atau mengalami gangguan jaringan, daemon agen di klien akan beralih ke mode *silent retry* di latar belakang tanpa menimbun memori dan tanpa membebani CPU host. Layanan produksi di server klien dijamin tidak akan terganggu.
2. **Prinsip Hak Akses Minimal (*Least Privilege*):**
   Daemon agent berjalan di bawah akun pengguna sistem non-root (`pantau`). Tindakan administratif khusus dieksekusi melalui *sudo wrapper scripts* terisolasi pada `/usr/local/sbin/pantau-*` dengan pembatasan hak akses ketat di `/etc/sudoers.d/pantau`.
3. **Guardrail Pengaman Sistem:**
   Task Manager secara otomatis melarang penghentian (*SIGTERM/SIGKILL*) terhadap PID kritis sistem (PID 1 / systemd) dan thread kernel. File Manager otomatis membuat cadangan `.bak` sebelum berkas konfigurasi diubah.
4. **Pembaruan Tanpa Hambatan (Fleet-Wide OTA):**
   Saat Anda memperbarui server pusat ke versi baru, seluruh agent klien akan mendeteksi perbedaan versi pada siklus pelaporan berikutnya. Klien akan mengunduh berkas pembaruan, memeriksa validitas hash SHA-256, menguji sintaks Python lokal, lalu melakukan restart service secara mandiri tanpa memerlukan intervensi manual dari Tim IT.

---

## Prosedur Pencopotan Pemasangan (Uninstall)

Bila Anda ingin menghapus instalasi agen dari server klien secara bersih:

```bash
# Hentikan dan nonaktifkan service agent
sudo systemctl stop agent_pantau.service
sudo systemctl disable agent_pantau.service

# Bersihkan berkas agent, konfigurasi, wrapper, dan sudoers
sudo rm -rf /opt/pantau/agent /etc/pantau /etc/systemd/system/agent_pantau.service /etc/sudoers.d/pantau /usr/local/sbin/pantau-*
sudo userdel pantau 2>/dev/null || true
sudo systemctl daemon-reload
```
