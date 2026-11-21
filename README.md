# Pantau Server

[![Version](https://img.shields.io/badge/version-v0.1.0-blue.svg)](file:///home/bos/pantau-server/server/config.py)
[![Backend](https://img.shields.io/badge/backend-FastAPI%20%7C%20Python%203.12-emerald.svg)](file:///home/bos/pantau-server/server/main.py)
[![Frontend](https://img.shields.io/badge/frontend-Vue%203%20%7C%20Tailwind%20CSS-cyan.svg)](file:///home/bos/pantau-server/frontend/src/App.vue)
[![Architecture](https://img.shields.io/badge/architecture-Clean%20Architecture-purple.svg)](file:///home/bos/pantau-server/DEVELOPMENT.md)
[![License](https://img.shields.io/badge/license-Proprietary-darkred.svg)](#lisensi)

**Pantau Server** adalah platform kendali operasional NOC (*Network Operations Center Control Plane*) terpusat yang dirancang khusus untuk memantau kesehatan infrastruktur, menyelidiki deviasi sistem, dan memitigasi insiden armada server Linux secara *real-time* dengan presisi tingkat kernel (*kernel-grade precision*).

Aplikasi ini mengusung estetika visual **Tactical Cyber Command Room** yang tenang, padat informasi, bebas kedipan (*zero-flicker*), serta dioptimalkan untuk keterbacaan tajam pada skala zoom normal 100%.

---

## 🌟 Fitur Utama Pengguna (User Features)

### 1. Dasbor Operasional Murni Pasif (*Passive Situational Dashboard*)
* **Pengawasan Makro 24/7/365:** Menampilkan banner KPI presisi 3 kartu: *Total Servers*, *Active Incidents* (dilengkapi 5 strip tingkat keparahan bergaya Zabbix: *Critical, High, Warning, Info, Ignored*), dan *System Clock* dengan sinkronisasi zona waktu WIB.
* **Proteksi Mutasi Tak Sengaja:** Area dasbor murni bersifat pasif untuk triase insiden dan pengamatan metrik global, bebas dari tombol eksekusi aktif yang berisiko tertekan secara tidak sengaja.
* **Tabel Insiden Terkini:** Daftar tiket anomali yang diperbarui otomatis lengkap dengan durasi kejadian, tingkat keparahan, dan navigasi langsung ke host terkait.

### 2. Inventaris Armada Berkepadatan Tinggi (*Fleet Inventory Table*)
* **Matriks 12 Kolom Komprehensif:** Menyajikan fakta fisik server secara transparan: Status Koneksi, Hostname & Grup, Alamat IP & Antarmuka, Platform & Arsitektur, OS & Versi Kernel, Beban CPU, Alokasi RAM & Swap, Utilisasi Disk Root, Uptime Aktif, Versi Agen/APT, serta Waktu Lapor Terakhir (*Last Seen*).
* **Pencarian & Filter Cepat:** Temukan server secara instan berdasarkan nama host, IP, atau status (*All, Online, Offline*).
* **Klaster Tombol Aksi Mandiri:** Setiap baris dilengkapi kontrol taktis langsung: `[ View ]` (Buka Jendela Kerja), `[ 📊 ]` (Metrik), `[ 🖥️ ]` (Terminal), `[ 🔄 ]` (Pindai Instan), dan `[ ⋮ ]` (Opsi Tambahan).

### 3. Jendela Kontrol Taktis Mengambang (*Floating Workspace Controller*)
* **Inspeksi & Mitigasi Tanpa Pindah Halaman:** Menekan tombol `[ View ]` pada baris server akan membuka modal taktis mengambang berdimensi luas (*85vw x 85vh*) di atas dasbor tanpa memutus konteks kerja armada.
* **Host Switcher Terintegrasi:** Berpindah antar server secara instan melalui pintasan keyboard `[` (Host Sebelumnya) dan `]` (Host Berikutnya) atau menu pencarian host di bilah atas modal.
* **Dukungan Minimalkan ke Rak Bawah (*Workspace Shelf*):** Jendela kerja dapat diminimalkan ke rak bawah saat operator ingin memeriksa armada lain, dan dipulihkan kembali kapan saja tanpa kehilangan status atau tab yang sedang dibuka.
* **8 Sub-Panel Investigasi Per Host:**
  - **Overview:** Gauge persentase utilisasi CPU, RAM, Swap, spesifikasi CPU, dan partisi disk.
  - **Incidents:** Tiket insiden aktif spesifik host serta tombol terminasi sesi SSH mencurigakan.
  - **Services:** Pengawasan unit layanan `systemd` dengan tombol *Restart* berkonfirmasi aman.
  - **Tasks:** Inventaris proses teratas pemakan CPU/RAM dengan tombol terminasi *Kill*.
  - **Ports:** Audit socket jaringan yang sedang mendengarkan (*listening sockets*).
  - **Firewall:** Status aturan UFW aktif (port, arah lalu lintas, dan aksi).
  - **Automation:** Tugas terjadwal pada cron user dan `systemd timers`.
  - **Users & SSH:** Daftar akun pengguna server serta sesi remote SSH aktif yang dapat diputus seketika.

### 4. Standar Multi-Bahasa Reaktif (*Dual-Language i18n*)
* Secara bawaan (*default*), antarmuka menggunakan **Bahasa Inggris (`en`)** baku sysadmin/NOC (*Overview, Incidents, Services, Tasks, Ports, Firewall, Total Servers, Active Incidents, System Clock*).
* Dilengkapi sakelar bahasa instan pada Navbar (`[ 🌐 EN | ID ]`) untuk beralih seketika ke **Bahasa Indonesia (`id`)** tanpa memuat ulang halaman (*zero-reload*).

### 5. Tata Kelola Akses & Kesetaraan Wewenang (*RBAC Parity*)
* Mendukung kesetaraan operasional penuh bagi akun *Operator* untuk mengelola armada tanpa diskriminasi teknis.
* Dilindungi aturan integritas akun mutlak: Akun operator dilarang menghapus akun dirinya sendiri dan dilarang menghapus akun `master-admin`.

---

## 📋 Persyaratan Sistem (Prerequisites)

* **Sistem Operasi:** Linux (Ubuntu 22.04 LTS / 24.04 LTS, Debian 12, Rocky Linux 9, atau distro setara).
* **Python:** Versi 3.10 atau lebih baru (disarankan Python 3.12).
* **Node.js:** Versi 18 LTS atau lebih baru dengan `npm` (diperlukan saat mengompilasi frontend).
* **Basis Data:** MariaDB 10.6+ / MySQL 8.0+ atau SQLite untuk instans lokal bersih.
* **Peramban Web:** Google Chrome, Mozilla Firefox, Microsoft Edge, atau Safari modern dengan dukungan CSS Grid dan Flexbox.

---

## 🚀 Panduan Instalasi & Menjalankan (Quick Start)

### 1. Kloning Repositori
```bash
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
```

### 2. Persiapan Lingkungan Python (Backend)
```bash
# Buat dan aktifkan virtual environment
python3 -m venv env
source env/bin/activate

# Pasang pustaka dependensi backend
pip install --upgrade pip
pip install -r server/requirements.txt
```

### 3. Kompilasi Aset Antarmuka (Frontend)
```bash
cd frontend
npm install
npm run build
cd ..
```
*Hasil kompilasi akan otomatis disimpan di `frontend/dist/` dan disajikan langsung oleh FastAPI.*

### 4. Konfigurasi Berkas Lingkungan
Salin berkas contoh konfigurasi:
```bash
cp server/.env.example server/.env
nano server/.env
```
Sesuaikan parameter koneksi basis data dan kunci rahasia (*secret key*).

### 5. Menjalankan Server
Jalankan daemon backend menggunakan Uvicorn:
```bash
source env/bin/activate
uvicorn main:app --app-dir server --host 0.0.0.0 --port 8401
```

Buka peramban Anda dan akses antarmuka pada:
```
http://<IP_SERVER>:8401
```

---

## ⚙️ Variabel Konfigurasi (`.env`)

| Variabel | Tipe | Nilai Bawaan | Deskripsi |
| :--- | :--- | :--- | :--- |
| `SERVER_HOST` | String | `0.0.0.0` | Alamat IP binding antarmuka server |
| `SERVER_PORT` | Integer | `8401` | Port HTTP tempat dasbor dan API melayani permintaan |
| `SECRET_KEY` | String | `default_secret_key` | Kunci rahasia untuk enkripsi token otentikasi JWT |
| `DB_HOST` | String | `127.0.0.1` | Hostname / IP server database MySQL |
| `DB_PORT` | Integer | `3306` | Port server database |
| `DB_USER` | String | `pantau_user` | Nama pengguna database |
| `DB_PASS` | String | `pantau_password` | Kata sandi database |
| `DB_NAME` | String | `pantau_clean_db` | Nama database mandiri yang bersih |

---

## ⌨️ Pintasan Papan Ketik (Keyboard Shortcuts)

Antarmuka Pantau Server dilengkapi tombol navigasi cepat untuk efisiensi NOC:

* <kbd>1</kbd> : Buka tampilan **Dashboard** (Dasbor Utama).
* <kbd>2</kbd> : Buka tampilan **Fleet Inventory** (Inventaris Armada).
* <kbd>3</kbd> : Buka tampilan **Audit Trail** (Log Akuntabilitas).
* <kbd>4</kbd> : Buka tampilan **Settings** (Pengaturan & RBAC).
* <kbd>[</kbd> : Pindah ke **Server Sebelumnya** di dalam jendela modal.
* <kbd>]</kbd> : Pindah ke **Server Berikutnya** di dalam jendela modal.
* <kbd>ESC</kbd> : Tutup jendela modal kerja yang sedang aktif.

---

## 🔒 Keamanan & Kebijakan Data
* **Kejujuran Data Mutlak (Zero-Fake Data):** Antarmuka hanya menampilkan fakta fisik yang terukur langsung dari kernel host Linux via agen telemetri resmi.
* **Proteksi Sistem Vital:** Perintah mitigasi dan kontrol daya dibatasi secara ketat oleh pengawal keselamatan (*safety guardrails*) untuk mencegah penghentian unit kritis sistem.

---

## 📄 Lisensi
Hak Cipta © 2026 **Pantau Server Project** (azhuka). Seluruh hak cipta dilindungi undang-undang.
