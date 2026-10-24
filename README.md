# Pantau Server

Dashboard pemantauan dan pengelolaan multi-server Linux berbasis web (FastAPI + MariaDB) dengan daemon agen Python ringan tanpa dependensi eksternal. Dirancang untuk memudahkan sysadmin dan tim operasional mengawasi metrik performa, mengelola layanan, dan menangani insiden secara terpusat.

---

## Fitur Utama

- **Pemantauan Performa & Alur Kerja Real-Time:** Monitoring utilisasi CPU, RAM, Swap, Disk per partisi, Load Average, bandwidth, status layanan sistem, dan sesi login SSH secara seketika (detak 5 detik, pelaporan instan pasca-tindakan zero-delay, deteksi kejadian eksternal langsung) via polling background tanpa reload halaman.
- **Telemetri Perangkat Keras & Virtualisasi:** Deteksi otomatis model prosesor, jumlah core, clock speed, platform hypervisor (KVM, Proxmox LXC/VM, VMware, Baremetal), tipe media penyimpanan (SSD/HDD), default gateway, DNS, interface jaringan, MAC address, serta waktu aktif sistem (*uptime*).
- **Kesehatan Media Penyimpanan (S.M.A.R.T. & NVMe):** Pemantauan kesehatan drive fisik secara komprehensif via `smartctl` dan `nvme-cli` (status PASSED/FAILED, suhu operasional, persentase keausan SSD/NVMe, *reallocated sectors*, jam terbang kerja), disertai deteksi drive virtual pada hypervisor/cloud agar tidak memicu alarm palsu.
- **Pengujian Endpoint & Jaringan Terjadwal (Probing Engine):** Pengujian konektivitas HTTP/HTTPS, TCP Port, DNS, dan ICMP Ping dengan riwayat latensi, pencatatan kegagalan, dan audit trail otomatis.
- **Klasifikasi Level Operasional Server (3-Tier) & Banner Peringatan Multi-Level:**
  - **Tier 1 (Layanan Utama):** Server dengan prioritas tinggi. Gangguan memulai tahap keparahan Gawat selama 1 menit untuk tindakan mitigasi awal, kemudian bereskalasi ke Kritis serta mengaktifkan banner merah (`banner-danger`) dan alarm audio jika belum pulih.
  - **Tier 2 (Layanan Pendukung):** Server operasional sekunder. Gangguan memulai tahap Peringatan selama 1 menit sebelum bereskalasi ke Gawat. Banner peringatan multi-level (`banner-average` oranye & `banner-warning` kuning) memastikan operator selalu mengetahui insiden pada seluruh armada server tanpa terkecuali.
  - **Tier 3 (Layanan Non-Kritis / Pengujian):** Server tahap uji coba atau sementara. Gangguan dibatasi pada tingkat Peringatan.
  - **Tindakan Pemeliharaan Operator:** Penghentian layanan (*Stop Service*) atau pemadaman server (*Power Off*) yang dilakukan oleh operator dicatat sebagai Peringatan tanpa memicu alarm darurat.
- **Pembaruan Agen Otomatis (Fleet-Wide OTA Self-Update):** Pembaruan agen klien secara otomatis saat server pusat diperbarui. Dilengkapi verifikasi integritas hash SHA-256 dan restart otomatis via systemd watchdog.
- **Manajemen Layanan Systemd & Proses:** Memulai (*start*), menghentikan (*stop*), memulai ulang (*restart*), memantau log service, serta menghentikan proses sistem (*kill* via SIGTERM/SIGKILL) langsung dari antarmuka web dengan pengaman sistem (*guardrail*).
- **Terminal Web Terintegrasi (xterm.js):** Sesi shell Linux interaktif langsung di browser dengan dukungan warna ANSI, tombol shortcut Bash, nano/vim, htop, dan mode layar penuh.
- **File Manager Web:** Eksplorasi direktori remote, penyuntingan berkas konfigurasi dengan cadangan otomatis (`.bak`), upload, download, serta pengaturan izin (*chmod/chown*) dengan proteksi path sistem kritis.
- **Kontrol Hak Akses 3-Tier (RBAC):**
  - **Master Admin:** Otoritas penuh sistem (pengaturan pengguna, audit log, konfigurasi global). Akun terlindungi dari penghapusan atau penonaktifan.
  - **Operator:** Hak operasional harian yang dapat didelegasikan secara granular (layanan, terminal, file manager, firewall) dengan wewenang setara sudo.
  - **Viewer:** Hak observasi baca-saja (*read-only*) tanpa tombol aksi eksekusi.
- **Autentikasi Dua Langkah (2FA TOTP):** Dukungan Google Authenticator, Microsoft Authenticator, dan kode pemulihan cadangan (*recovery codes*).
- **Audit Trail Terpusat:** Pencatatan log seluruh aktivitas pengguna (siapa, kapan, perintah/tindakan, target, dan hasil eksekusi).
- **Sinkronisasi Antarmuka & Pembaruan Reaktif Tanpa Reload (Universal Zero-Reload NOC UI):** Pengawas telemetri otomatis di browser dan modul reaktif yang memperbarui insiden, kartu insiden terkini, tabel armada, kartu grid, siklus hidup pendaftaran/penghapusan server (*dynamic fleet add/remove*), status layanan, port listening, status firewall, tugas cron, sertifikat SSL, akun login SSH remote, serta metrik server secara seketika tanpa jeda dan tanpa mengharuskan operator me-reload halaman manapun. Dilengkapi mekanisme sliding session window 24/7 agar layar monitor NOC tidak pernah terputus atau kedaluwarsa secara sepihak. Seluruh aksi dan konfirmasi operator dieksekusi secara asinkron (AJAX).
- **Standarisasi Kontrol Interaksi Universal & Efisiensi Resource Browser:** Seluruh modal dialog pada antarmuka Pantau Server mendukung 3 metode penutupan standar (tombol Close 'X' yang konsisten, penekanan tombol Escape keyboard global, dan klik di luar area modal/backdrop). Polling asinkron (seperti streaming live log dan telemetri) dilengkapi proteksi kebocoran memori dengan suspensi otomatis saat tab tidak aktif (*visibilitychange* & tab switching).
- **Alur Kerja Pengabaian Cerdas Insiden Terkendali (Universal Incident Silencing & Triage):** Filosofi penanganan insiden operasional terpadu untuk segala tingkat keparahan (*danger, average, warning, info*). Ketika suatu insiden telah dikenali atau disengaja oleh operator (misalnya layanan *on-demand* yang hanya aktif saat digunakan user klien secara manual, sesi remote SSH resmi, atau jadwal pembaruan APT), operator dapat mengabaikannya (*Abaikan / Silence*). Sistem secara otomatis menyembunyikan insiden tersebut dari daftar tabel *Insiden Terkini* pada layar utama monitor NOC agar tidak mengaburkan fokus pengawasan, sementara indikator "Diabaikan 🔕" pada kartu *Insiden Aktif* tetap mencatatnya secara terstruktur sehingga operator dapat meninjau atau memulihkannya kapan saja melalui modal rincian *Diabaikan (Silenced / Ignored 🔕)*.
- **Standarisasi Terminologi & Ergonomi Antarmuka Baku:** Label status kolom masalah berstatus aman dikunci pada badge **Nihil**, tab navigasi rincian server menggunakan nomenklatur standar teknis (*Performa, Insiden, Services, Tasks, Users, Ports, Firewall, SSL/TLS, Cron Jobs, Logs*), dan seluruh kolom interaksi kontrol diekspresikan secara seragam dengan judul **Tindakan**.

---

## 1. Pemasangan Dashboard (Server Pusat)

Dukungan sistem operasi: Ubuntu 20.04/22.04/24.04 LTS atau Debian 11/12.

```bash
# 1. Perbarui paket dan pasang dependensi dasar
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

# 2. Clone repositori dan jalankan installer
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Skrip installer otomatis melakukan konfigurasi:
- Membuat pengguna sistem `pantau`
- Menyiapkan database MariaDB
- Memasang dan mengaktifkan service systemd `pantau-server.service`
- Meminta kata sandi awal untuk akun administrator

Setelah instalasi selesai, akses dashboard melalui browser:
- **Alamat:** `http://<IP-SERVER>:8400`
- **Username:** `admin`
- **Password:** kata sandi yang ditentukan saat instalasi

**Memeriksa Status Service Dashboard:**
```bash
sudo systemctl status pantau-server.service
```

**Reset Kata Sandi Admin via CLI:**
```bash
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password 'password-baru'
```

---

## 2. Pemasangan Agen pada Server Klien

Agen Pantau beroperasi dengan metode **Outbound Pull** (koneksi keluar dari klien ke server pusat setiap 5–10 detik via HTTP/HTTPS POST). Klien tidak memerlukan port inbound terbuka dan dapat berjalan di balik NAT, firewall, atau jaringan privat (LAN/VPN).

1. Buka dashboard: Masuk ke menu **Daftar Server → Tambah Server**, kemudian salin **API Key** (64 karakter hex).
2. Di server klien yang akan dipantau, unduh dan jalankan installer agen:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Installer akan meminta konfigurasi interaktif:
- **URL Dashboard:** Masukkan URL server pusat (contoh LAN/VPN: `http://172.30.1.40:8400` atau domain `https://pantau.domainanda.com`).
- **API Key:** Masukkan API Key yang telah disalin dari dashboard.

Skrip installer klien otomatis melakukan:
- Validasi konektivitas dan autentikasi token ke Dashboard.
- Menulis konfigurasi aman pada `/etc/pantau/config.json` (izin `0640`, owner `root:pantau`).
- Memasang dan mengaktifkan service systemd `agent_pantau.service` di bawah pengguna `pantau`.

*(Mode non-interaktif untuk skrip automasi/Ansible: `sudo bash /tmp/pantau-install.sh "http://<IP-DASHBOARD>:8400" "<API_KEY>"`)*

Server klien akan terdeteksi dan berstatus online di dashboard dalam ±10 detik.

**Pemeriksaan Service dan Log Agen Klien:**
```bash
sudo systemctl status agent_pantau.service
sudo journalctl -u agent_pantau -f
```

---

## Panduan Antarmuka & Navigasi

### Dashboard Utama
- **Ringkasan Armada:** Jumlah server aktif, server offline, layanan bermasalah, dan beban rata-rata sistem.
- **Tabel Status & Kinerja:** Tampilan ringkas status koneksi, CPU, RAM, Storage, dan layanan per server, dilengkapi pencarian dan filter grup.
- **Insiden Terkini:** Daftar insiden aktif terpusat yang diurutkan berdasarkan tingkat keparahan (*Kritis*, *Gawat*, *Peringatan*).

### Rincian Server
- **Tab Kinerja & Spesifikasi:** Utilisasi CPU, memori, swap, partisi storage, throughput interface jaringan, serta grafik riwayat beban sistem (1 jam hingga 30 hari).
- **Tab Riwayat & Masalah:** Riwayat insiden pada server, rekomendasi penanganan teknis, opsi abaikan sementara (*mute/silence*), dan konfirmasi penanganan (*acknowledge*).
- **Tab Layanan:** Kontrol unit systemd (Mulai, Hentikan, Restart, Tambah Layanan), penandaan layanan utama (*core*) vs sekunder, serta akses log service.
- **Tab Manajer Tugas:** Daftar proses sistem teratas berdasarkan pemakaian CPU dan RAM, dilengkapi opsi terminasi proses (*SIGTERM* atau *SIGKILL*).
- **Tab Akun Pengguna:** Daftar akun lokal Linux, status kunci (*lock/unlock*), dan pembuatan akun baru.
- **Tab Port Listening:** Audit socket jaringan TCP dan UDP yang sedang terbuka beserta proses pemiliknya.
- **Tab Firewall:** Status UFW, aturan firewall, daftar alamat IP yang diblokir pada tingkat kernel via iptables, serta tombol blokir/buka blokir IP.
- **Tab Sertifikat SSL:** Pemantauan tanggal kedaluwarsa berkas sertifikat SSL lokal dan sertifikat web server.
- **Tab Tugas Terjadwal:** Manajemen entri cron sistem pada `/etc/cron.d/`.
- **Tab Logging:** Log viewer terpadu untuk berkas log sistem dan journald.
- **Terminal Web (`>_ Terminal`):** Akses shell root interaktif langsung di browser.
- **File Manager (`📁 File Manager`):** Remote file explorer untuk membaca, mengunggah, mengunduh, dan menyunting berkas konfigurasi.

---

## Model Kontrol Akses (RBAC 3-Tier)

| Fitur / Tindakan | Master Admin | Operator (Sudo) | Viewer |
|:---|:---:|:---:|:---:|
| Melihat Dashboard, Metrik & Log | Ya | Ya | Ya |
| Kelola Server & Layanan (Start/Stop/Restart) | Ya | Sesuai Izin | Tidak |
| Akses Terminal Web & File Manager | Ya | Sesuai Izin | Tidak |
| Restart Sistem (Reboot) & Update OS | Ya | Sesuai Izin | Tidak |
| Kelola Firewall (UFW) & Blokir IP | Ya | Sesuai Izin | Tidak |
| Manajemen Pengguna (Tambah, Edit, Kunci) | Ya | Sesuai Izin | Tidak |
| Audit Trail Aktivitas Pengguna | Ya | Sesuai Izin | Tidak |
| Menghapus / Mengubah Akun Master Admin | Ya (Pribadi) | Ditolak | Tidak |
| Profil Akun Pribadi & Konfigurasi 2FA | Ya | Ya | Tidak |

---

## Klasifikasi Level Operasional & Keparahan Insiden

Pantau Server menerapkan hierarki evaluasi insiden berdasarkan tingkat kepentingan operasional server:

### 1. Klasifikasi Level Operasional
- **Tier 1 (Layanan Utama):** Server dengan beban kerja vital yang memerlukan ketersediaan tinggi. Gangguan sistem bereskalasi hingga tingkat **KRITIS**, memicu banner merah global dan alarm audio.
- **Tier 2 (Layanan Pendukung):** Server pendukung operasional yang memiliki toleransi pemulihan. Gangguan sistem bereskalasi maksimal hingga tingkat **GAWAT**, tanpa memicu banner global atau alarm audio.
- **Tier 3 (Layanan Sementara / Uji Coba):** Server pengembangan, staging, atau pengujian. Gangguan sistem dibatasi pada tingkat **PERINGATAN**.

### 2. Matriks Keparahan Insiden

| Kondisi / Insiden Sistem | Tier 1 (Utama) | Tier 2 (Pendukung) | Tier 3 (Sementara) | Catatan Operasional |
|:---|:---:|:---:|:---:|:---|
| **Server Klien Offline (Tidak Melapor)** | 🔴 **KRITIS** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Banner merah & alarm audio hanya aktif untuk Tier 1 |
| **Partisi Disk Read-Only** | 🔴 **KRITIS** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Menandakan proteksi kernel akibat kegagalan I/O |
| **Penyimpanan Disk Penuh (100%)** | 🔴 **KRITIS** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Menghambat penulisan data dan transaksi database |
| **Layanan Utama (*Core Service*) Down** | 🔴 **KRITIS** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Berlaku untuk layanan berstatus Utama |
| **Layanan Sekunder Down** | 🟡 **PERINGATAN** | 🟡 **PERINGATAN** | 🟡 **PERINGATAN** | Layanan pendukung (misal cache/worker) |
| **Tindakan Pemeliharaan Operator** | 🟡 **PERINGATAN** | 🟡 **PERINGATAN** | 🟡 **PERINGATAN** | Server shutdown atau service stop yang disengaja |
| **Penggunaan RAM / CPU $\ge 90\%$** | 🟠 **GAWAT** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Utilisasi sumber daya mendekati batas kapasitas |
| **Pembaruan Paket Sistem Tersedia** | 🔵 **INFO** | 🔵 **INFO** | 🔵 **INFO** | Pembaruan paket keamanan atau rilis distro Linux |

---

## Pembaruan Sistem (Update)

### 1. Pembaruan Server Pusat
Jalankan di server dashboard:
```bash
cd /opt/pantau/server/pantau-server   # sesuaikan path repositori lokal
git pull
sudo bash install-server.sh
```
*Berkas konfigurasi `.env` dan database MariaDB tidak akan terhapus saat pembaruan dijalankan.*

### 2. Pembaruan Otomatis Armada Agen (Fleet-Wide OTA)
Saat server pusat diperbarui ke versi baru, seluruh agen klien secara otomatis mengunduh pembaruan pada siklus pelaporan berikutnya (dalam ~5 detik):
1. Server mendeteksi versi agen klien lebih lama daripada versi dashboard.
2. Server mengirimkan instruksi pembaruan beserta URL berkas agen dan hash SHA-256 resmi.
3. Agen klien mengunduh berkas pembaruan, memeriksa validitas hash SHA-256, menguji sintaks via `py_compile`, memperbarui berkas `/opt/pantau/agent/agent_pantau.py`, lalu me-restart service secara mandiri.

### 3. Pembaruan Agen Manual
- **Melalui Dashboard:** Klik tombol **`⚡ Push Update (OTA)`** pada halaman rincian server.
- **Melalui Terminal Klien:**
  ```bash
  sudo curl -fsSL -o /tmp/pantau-install.sh https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh && sudo bash /tmp/pantau-install.sh
  ```

---

## Konfigurasi Reverse Proxy Nginx & SSL (Produksi)

Secara bawaan dashboard berjalan pada port HTTP 8400. Untuk lingkungan produksi, disarankan menggunakan reverse proxy Nginx dengan enkripsi HTTPS (SSL/TLS). Berkas template konfigurasi tersedia di direktori `deploy/`.

```bash
# 1. Pasang konfigurasi Nginx
sudo cp deploy/nginx/pantau-server.conf /etc/nginx/sites-available/pantau-server
sudo nano /etc/nginx/sites-available/pantau-server   # Sesuaikan server_name dengan domain Anda

# 2. Aktifkan konfigurasi
sudo ln -s /etc/nginx/sites-available/pantau-server /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 3. Pasang sertifikat SSL Let's Encrypt
sudo certbot --nginx -d pantau.domainanda.com

# 4. Aktifkan flag cookie aman pada /opt/pantau/server/.env
# Ubah: SESSION_COOKIE_SECURE=True
sudo systemctl restart pantau-server.service
```

---

## Pencadangan, Pemulihan & Retensi Data

### Cadangan dan Pemulihan Database
Data metrik dan konfigurasi tersimpan di MariaDB (`pantau_db`) dan berkas `/opt/pantau/server/.env`.

```bash
# Backup database & environment
sudo mysqldump -u root pantau_db | gzip > pantau_db_$(date +%F).sql.gz
sudo cp /opt/pantau/server/.env .env_$(date +%F)

# Restore database dari file backup
gunzip -c pantau_db_YYYY-MM-DD.sql.gz | sudo mysql -u root pantau_db
sudo systemctl restart pantau-server.service
```

### Kebijakan Retensi Data Otomatis
Sistem secara berkala membersihkan data lama setiap jam agar kapasitas penyimpanan tetap terjaga:
- **Snapshot Metrik Mentah (5-10 detik):** 24 jam (agregasi rata-rata per jam disimpan selama 90 hari).
- **Log Permintaan Selesai:** 30 hari.
- **Insiden yang Terselesaikan (*Resolved*):** 90 hari.
- **Riwayat Perintah Remote:** 180 hari.
- **Audit Trail Pengguna:** 365 hari (1 tahun).

---

## Panduan Penyelesaian Masalah (Troubleshooting)

| Gejala Masalah | Kemungkinan Penyebab & Solusi |
|:---|:---|
| Server klien berstatus `Offline` | Periksa service agen: `sudo systemctl status agent_pantau.service`. Pastikan klien dapat menjangkau port 8400 server pusat (uji via `curl -Iv http://<IP-SERVER>:8400`). |
| Akses terminal ditolak (`403 Forbidden`) | Akun pengguna belum memiliki izin terminal (`can_terminal`). Hubungi Master Admin untuk memperbarui hak akses. |
| Terminal menampilkan error `409 Conflict` | Terdapat sesi terminal lain yang sedang aktif pada server tersebut (dibatasi 1 sesi aktif per server demi keamanan). |
| Pembaruan OS (APT) terkunci | Terdapat proses APT/dpkg lain yang sedang berjalan di klien. Buka terminal web dan jalankan `sudo dpkg --configure -a`. |
| Tombol Push OTA tidak muncul | Versi agen pada klien sudah mutakhir atau identik dengan versi dashboard server. |
| Gagal autentikasi 2FA / Kehilangan perangkat | Buka terminal server pusat dan jalankan: `sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py --username <user> --reset-2fa`. |
