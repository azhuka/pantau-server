# Pantau Server

Dashboard monitoring terpusat (FastAPI + MariaDB) untuk memantau kondisi,
kinerja, log, dan keamanan banyak server dari satu antarmuka web, serta dilengkapi
dengan **agen Pantau** (Python) ringan yang berjalan di setiap server klien.

## Daftar Isi

- [1. Install Dashboard](#1-install-dashboard-server-web-app-pantau-server)
- [2. Install Agen di Server Klien](#2-install-agen-di-server-klien)
- [Halaman & Fitur](#halaman--fitur)
- [Peran Pengguna (Admin vs Viewer)](#peran-pengguna-admin-vs-viewer)
- [Update Dashboard](#update-dashboard)
- [Update Agen](#update-agen)
- [Kompatibilitas Versi Agen](#kompatibilitas-versi-agen)
- [Terminal Bawaan & Update OS](#terminal-bawaan--update-os-dari-dashboard)
- [Troubleshooting & Batasan Terminal](#troubleshooting--batasan-terminal)
- [HTTPS & Lingkungan Produksi](#https--lingkungan-produksi)
- [Backup, Restore & Retensi Data](#backup-restore--retensi-data)
- [Catatan Keamanan & Praktik Terbaik](#catatan-keamanan--praktik-terbaik)

---

## 1. Install Dashboard (Server Web App "Pantau Server")

Jalankan perintah berikut pada server yang akan dijadikan pusat pemantauan:

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Skrip instalasi akan membuat pengguna sistem, basis data MariaDB (dengan kredensial aman), berkas layanan systemd, serta meminta kata sandi untuk akun administrator awal.

Setelah instalasi selesai, buka peramban web pada alamat `http://<ip-dashboard>:8400` dan masuk menggunakan:

- **Username:** `admin`
- **Password:** kata sandi yang Anda tentukan saat proses instalasi

Jika lupa kata sandi, Anda dapat meresetnya langsung dari server dashboard:

```bash
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password '<password-baru>'
```

Pemeriksaan status layanan dashboard:
```bash
systemctl status pantau-server.service
```

---

## 2. Install Agen di Server Klien

1. Masuk ke dashboard: buka menu **Servers → Tambah Server**, lalu salin **Kunci API** yang dihasilkan.
2. Di server klien (target pemantauan), jalankan skrip penginstal:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Penginstal akan meminta URL dashboard dan Kunci API (64 karakter heksadesimal), memverifikasi validitas kunci ke dashboard, memasang layanan agen, dan mengaktifkannya secara otomatis. Dalam ±10 detik, server klien akan muncul dan berstatus online di dashboard.

Instalasi non-interaktif juga dapat dijalankan dengan parameter:
```bash
sudo bash /tmp/pantau-install.sh "http://<ip-dashboard>:8400" "<KUNCI_API>"
# atau menggunakan environment variables:
sudo SETUP_SERVER_URL="http://<ip-dashboard>:8400" SETUP_API_KEY="<KUNCI_API>" bash /tmp/pantau-install.sh
```

Pemeriksaan status dan log agen jika terjadi kendala:
```bash
systemctl status agent_pantau.service
journalctl -u agent_pantau -f
```

> **Catatan:** Apabila menjalankan instalasi via `curl | bash`, hanya berkas agen dan skrip pendukung yang diunduh langsung dari GitHub tanpa mengkloning seluruh repositori ke server klien. Jika menghendaki instalasi dari salinan lokal, jalankan installer dari dalam folder repositori hasil klon git.

---

## Halaman & Fitur

| Halaman | Deskripsi & Fungsi |
|---|---|
| **Dashboard** | Ringkasan kondisi seluruh server secara terpusat: jumlah server online/offline, layanan terganggu (*down*), utilisasi CPU & RAM, serta waktu laporan terakhir. Dilengkapi pembaruan data langsung (*live polling*), pengurutan kolom, pencarian instan, dan tombol salin alamat IP. |
| **Servers** | Manajemen server klien: indikator status (online/offline), pendaftaran server baru, penyuntingan data, penghapusan, pengelolaan kunci API, tabel dinamis, serta pencarian instan. |
| **Rincian Server** | Pusat kendali dan inspeksi per server: <br>• **Tab Riwayat:** Grafik historis utilisasi CPU, Memori, Swap, System Load, dan Disk per *mount point* dengan visual modern *area gradient glow*, kartu metrik terstruktur, statistik rata-rata & tertinggi, serta pemilih rentang waktu terpadu.<br>• **Tab Layanan:** Manajemen layanan dan proses (Start, Stop, Restart, dan Tambah Layanan baru) yang mendukung baik unit systemd standar maupun biner/scope mandiri.<br>• **Tab Masalah:** Daftar alarm dan insiden aktif yang diperbarui secara langsung (*live reactivity* tanpa reload peramban), dilengkapi tombol aksi mitigasi/restart cepat, opsi pembungkaman masalah (*Mute/Silence* dengan pilihan durasi atau permanen), serta aksi konfirmasi & penyelesaian masalah in-place.<br>• **Tab ⚡ Proses Teratas:** Snapshot langsung proses pemakan CPU & Memori (tampilan default 5 proses teratas dengan opsi ekspansi ke 20 proses).<br>• **Tab Jaringan:** Daftar antarmuka jaringan lengkap dengan IP address aktif (IPv4 & IPv6), status *link*, dan laju data (*throughput*).<br>• **Tab Akun:** Daftar pengguna lokal yang terdaftar pada sistem beserta penelusuran riwayat aktivitas login dan eksekusi sudo.<br>• **Tab Log:** Penelusuran log sistem, filter teks, penandaan warna tingkat keparahan (*error*, *warning*, *critical*), serta tombol unduh berkas log.<br>• **Mode Pemeliharaan (Maintenance Mode):** Tombol `🔧 Pemeliharaan` untuk menjadwalkan henti pantau sementara agar tidak memicu alarm ketika server sedang diservis atau di-reboot.<br>• **Terminal Bawaan:** Akses shell remote interaktif langsung dari peramban via tombol `>_ Terminal`, lengkap dengan opsi **Layar Penuh (Full Screen)**.<br>• **File Manager:** Pintasan ke manajer berkas server klien melalui tombol `📁 File Manager ↗`. |
| **File Manager** | *(Khusus Admin)* Halaman terdedikasi (`/servers/{id}/files`) untuk menjelajahi direktori, menyunting berkas teks (dengan pencadangan otomatis `.bak`), membuat berkas/folder baru, mengunggah/mengunduh berkas, serta mengatur hak akses berkas (`chmod`/`chown`) yang dibentengi dengan proteksi direktori sistem penting. |
| **Masalah** | Rekapitulasi seluruh peringatan dan insiden aktif lintas server, dilengkapi filter server, filter tingkat keparahan (*Danger*, *Warning*, *Info*, dan *Diabaikan*), tombol pembungkaman masalah (*Mute/Silence*), konfirmasi penanganan (*ack*), durasi aktif kejadian, serta petunjuk mitigasi. |
| **Log** | Penelusuran log terpusat: log penggunaan sumber daya sistem, riwayat proses, log unit layanan tertentu, dan log aktivitas aplikasi dashboard. |
| **Audit** | Catatan jejak audit (*audit trail*) atas setiap tindakan administratif: autentikasi masuk/keluar, pembukaan sesi terminal, modifikasi konfigurasi server/layanan/pengguna, eksekusi perintah remote, dan restart agen. |
| **Users** | *(Khusus Admin)* Pengelolaan pengguna dashboard: penambahan akun, penetapan peran (*Role*), reset kata sandi, dan pencabutan sesi aktif. |

Seluruh angka dan metrik status bersumber dari data tunggal yang sinkron, memastikan konsistensi visual di seluruh halaman.

Indikator warna badge status:
- **Hijau:** Kondisi normal / sehat / operasi berhasil.
- **Merah:** Terdapat gangguan kritis / *service down* / kegagalan.
- **Kuning:** Memerlukan perhatian / peringatan tingkat sedang.
- **Biru:** Status informatif.
- **Abu-abu:** Netral / belum ada laporan data / tidak berlaku.

---

## Peran Pengguna (Admin vs Viewer)

| Hak Akses / Tindakan | Admin | Viewer |
|---|:---:|:---:|
| Meninjau Dashboard, Servers, Rincian, Masalah, dan Log | Ya | Ya |
| Menambah, menyunting, dan menghapus server & layanan | Ya | Tidak |
| Update OS, Upgrade Paket, Reboot OS, dan Power Off | Ya | Tidak |
| Membuka dan menggunakan Terminal Bawaan | Ya | Tidak |
| Mengakses File Manager (baca, sunting, unduh, unggah) | Ya | Tidak |
| Memulai, menghentikan, atau me-restart layanan remote | Ya | Tidak |
| Memblokir IP penyerang / melakukan mitigasi masalah | Ya | Tidak |
| Mengakses halaman Audit dan manajemen Users | Ya | Tidak |

Pengguna dengan peran **Viewer** yang membuka halaman Rincian Server hanya dapat melihat informasi dan metrik tanpa tombol kendali administratif.

---

## Update Dashboard

Untuk memperbarui dashboard ke versi terbaru:

```bash
cd /path/ke/pantau-server
git pull
sudo bash install-server.sh
```

Skrip pembaruan aman dijalankan ulang: konfigurasi pada berkas `.env` (termasuk kredensial basis data) akan dipertahankan, dependensi Python diperbarui, dan skema migrasi basis data diterapkan secara otomatis.

---

## Update Agen

Pusat Dashboard tidak menggunakan koneksi SSH inbound ke server klien. Komunikasi dilakukan melalui agen yang melapor secara periodik ke dashboard. Pembaruan agen dilakukan langsung pada server klien.

### Memperbarui Server Klien

Jalankan perintah berikut pada terminal server klien (perintah ini juga dapat disalin langsung dari tombol **📋 Salin Perintah Update** pada banner dasbor jika versi agen usang terdeteksi):

```bash
sudo curl -fsSL -o /opt/pantau/agent/agent_pantau.py https://raw.githubusercontent.com/azhuka/pantau-server/v4.0.0/package/opt/pantau/agent/agent_pantau.py && sudo systemctl restart agent_pantau.service
```

Atau jalankan ulang skrip installer agen. Konfigurasi yang sudah ada di `/etc/pantau/config.json` tidak akan ditimpa.

### Memperbarui Agen pada Host Dashboard Sendiri

Jika server tempat dashboard berjalan juga dipantau oleh agen lokal:

```bash
cd pantau-server
sudo install -m 755 -o root -g root package/opt/pantau/agent/agent_pantau.py /opt/pantau/agent/agent_pantau.py
sudo install -m 750 -o root -g root package/usr/local/sbin/pantau-apt /usr/local/sbin/pantau-apt
sudo install -m 750 -o root -g root package/usr/local/sbin/pantau-file /usr/local/sbin/pantau-file
sudo cp package/etc/sudoers.d/pantau-agent /etc/sudoers.d/pantau-agent
sudo chmod 440 /etc/sudoers.d/pantau-agent
sudo python3 -m py_compile /opt/pantau/agent/agent_pantau.py
sudo systemctl restart agent_pantau.service
```

### Verifikasi Setelah Pembaruan

Setelah me-restart agen (proses restart tidak menghapus riwayat metrik):
1. Label versi agen di halaman Rincian Server akan terbarui menjadi `agen v4.0.0`.
2. Server kembali terhubung dalam ±10 detik.
3. Tab **⚡ Proses Teratas** menampilkan snapshot proses sistem secara aktif.

---

## Kompatibilitas Versi Agen

Sangat dianjurkan untuk selalu menggunakan versi agen yang selaras dengan versi dashboard (**v4.0.0**) agar seluruh kapabilitas dapat beroperasi optimal.

| Kelompok Fitur | Versi Agen Minimum |
|---|:---:|
| Pemantauan metrik dasar, grafik riwayat, log, dan manajemen layanan | v3.6+ |
| Reboot OS dan Power Off remote | v3.6+ |
| Operasi Update OS & Upgrade paket (APT) | v3.7+ |
| Terminal Bawaan Realtime (xterm.js + WebSocket Streaming) | v3.14+ |
| Snapshot 20 Proses Teratas & Mode Pemeliharaan (*Maintenance Mode*) | v3.15.0+ |
| Dukungan Socket Activation (SSH shutdown aman) & Mute Layanan Fleksibel | v3.16.0+ |
| Throughput Disk I/O, Journal Error Tracking, Cron Jobs, Port Audit & SSL Expiry | v3.17.0+ |
| Interaktif Manajemen User, Cron, Port (Kill/Block), Custom SSL Path | v4.0.0+ |

Agen dengan versi sebelum persyaratan di atas tetap dapat menjalankan fungsi monitoring dasar, namun fitur baru yang tidak didukung akan menampilkan pemberitahuan yang jelas pada dashboard.

Untuk memeriksa sebaran versi agen pada seluruh server klien yang terdaftar, jalankan query berikut pada database:

```sql
SELECT s.hostname, x.agent_version
FROM servers s
LEFT JOIN server_extras x ON x.server_id = s.id
ORDER BY x.agent_version, s.hostname;
```

---

## Terminal Bawaan & Update OS dari Dashboard

Halaman Rincian Server menyediakan fasilitas **Terminal Bawaan**: terminal shell Linux interaktif di server klien, ditenagai oleh emulator terminal **xterm.js** pada sisi peramban dan komunikasi streaming dua arah (**WebSocket**) ke agen server klien. Terminal ini tertanam langsung di antarmuka web dan dapat diakses melalui tombol **`>_ Terminal`**.

### Mekanisme Kerja

```
Browser (Halaman Rincian)
   │  WebSocket: ws[s]://<host>/ws/servers/{id}/terminal (Autentikasi Sesi Admin)
   │  Render via xterm.js + FitAddon
   ▼
Dashboard FastAPI (TerminalBridgeDispatcher)
   │  Long-poll stream bridge (antrean memori)
   ▼
Agen Pantau (Server Klien)
   │  pty.openpty() + alokasi kontrol PTY asli
   │  sudo -n /usr/local/sbin/pantau-shell
   ▼
/bin/bash --noprofile --rcfile <rc_khusus> -i  →  root@<hostname>:~#
```

Karakteristik Terminal Bawaan:
- **Dukungan Perintah Penuh:** Mendukung *pipeline*, pengalihan (*redirection*), dan perintah interaktif apa pun (`htop`, `vim`, `nano`, `docker`, `systemctl`, `journalctl`, dll.).
- **Penyuntingan Baris Bash:** Tombol navigasi kursor, `Backspace`, `Delete`, `Home`, `End`, serta kombinasi shortcut bash (`Ctrl+A`, `Ctrl+E`, `Ctrl+U`, `Ctrl+W`).
- **Sinyal Sistem Asli:** Kombinasi `Ctrl+C` mengirimkan sinyal `SIGINT` nyata ke proses yang berjalan.
- **Penyelesaian Otomatis:** Tombol `Tab` melakukan *bash autocompletion* secara native.
- **Pembersihan Layar:** Tombol **Clear** atau perintah `clear` (`Ctrl+L`) membersihkan tampilan tanpa kehilangan konteks sesi.
- **Tampilan Interaktif:** Mendukung rendering warna ANSI, bilah kemajuan (*progress bar*), dan kursor aktif berkedip (*blinking cursor*).
- **Mode Layar Penuh (Full Screen):** Tombol **Full Screen** dan shortcut `Esc` untuk memperluas antarmuka terminal ke 100% layar monitor dengan auto-fit kolom & baris.
- **Riwayat Perintah:** Menggunakan panah atas/bawah `↑` / `↓` dalam sesi aktif (riwayat sesi tidak disimpan ke berkas disk demi privasi).

### Batasan Akses & Keamanan

Terminal Bawaan menjalankan sesi dengan hak akses administratif (`root`) melalui wrapper khusus:

| Parameter | Ketentuan |
|---|---|
| Otorisasi | Khusus peran **Admin**. Akses peran Viewer akan ditolak (`403 Forbidden`). |
| Jumlah Sesi Aktif | Maksimal **satu** sesi aktif per server. Permintaan pembukaan sesi kedua secara paralel akan ditolak (`409 Conflict`). |
| Wrapper Shell | Dijalankan ketat melalui `sudo /usr/local/sbin/pantau-shell` via konfigurasi `/etc/sudoers.d/pantau-agent`. |
| Berkas Riwayat | Dinonaktifkan (`HISTFILE=/dev/null`) sehingga tidak meninggalkan jejak `.bash_history` lokal. |
| Jejak Audit | Seluruh pembukaan dan penutupan sesi dicatat pada menu **Audit** Dashboard (`terminal_shell_open`) serta syslog server klien (`pantau-shell`). |
| Batas Waktu (*Timeout*) | Sesi idle ditutup otomatis setelah 8 jam demi keamanan. |

> **Peringatan Keamanan:** Akses shell root via web browser mensyaratkan pengelolaan kredensial admin yang sangat ketat. Pastikan dashboard diakses melalui koneksi aman HTTPS dan batasi jumlah pengguna dengan hak admin.

### Tombol Update OS dan Upgrade

Operasi pemeliharaan paket pada dashboard mengeksekusi operasi APT terisolasi (`apt update`, `apt upgrade`, `apt dist-upgrade`, `dpkg --configure -a`):
1. Keluaran proses dialirkan langsung ke jendela Terminal Bawaan dengan garis pemisah yang jelas.
2. Pertanyaan interaktif (seperti konfirmasi `Y/n` atau pemilihan berkas konfigurasi bawaan) dapat dijawab langsung melalui terminal.
3. Setelah proses pembaruan selesai, ringkasan hasil ditampilkan dan kontrol dikembalikan ke shell.

---

## Troubleshooting & Batasan Terminal

### Panduan Penanganan Kendala Operasi APT & Terminal

| Gejala Kendala | Langkah Penanganan |
|---|---|
| Status pembaruan menampilkan `Gagal — batas waktu habis` | Tunggu jeda proteksi 2 menit, lalu muat ulang halaman. Dashboard akan otomatis memeriksa proses yang masih berjalan di latar belakang. |
| Operasi `apt update` memakan waktu lebih dari 5 menit | Periksa stabilitas konektivitas internet atau mirror repositori paket pada server klien. |
| Operasi `upgrade` berjalan sangat lama | Pembaruan paket besar (seperti kernel Linux) membutuhkan waktu proses lebih lama. Buka Terminal Bawaan untuk mengamati proses kompilasi atau pemasangan secara langsung. |
| Proses interaktif berhenti menunggu respon | Masuk ke Terminal Bawaan, lalu berikan masukan teks atau tekan `Enter`. |
| Galat `dpkg` terkunci (*lock*) atau proses terhenti | Jalankan perintah perbaikan `dpkg --configure -a` atau gunakan tombol reparasi di dashboard. |
| Pembukaan terminal menampilkan galat `403` atau `409` | Kode `403`: akun Anda tidak memiliki hak Admin. Kode `409`: terdapat sesi terminal lain yang sedang aktif pada server tersebut. |

### Kondisi yang Memerlukan Akses SSH Langsung

Sebagian besar tugas pemeliharaan rutin, perbaikan dependensi, dan pemeriksaan server dapat diselesaikan secara efisien melalui dashboard. Namun, akses remote langsung melalui protokol SSH tetap diwajibkan pada kondisi khusus berikut:
1. **Upgrade Versi Distribusi Mayor:** Misalnya migrasi dari Debian 11 ke Debian 12, atau Ubuntu 22.04 ke 24.04, yang dapat merestart antarmuka jaringan atau komponen dasar sistem di tengah jalan.
2. **Antarmuka Konfigurasi Berbasis Dialog Penuh (ncurses TUI):** Menu layar biru debconf kompleks yang memerlukan manipulasi kursor grafis khusus atau dukungan mouse.
3. **Kegagalan Total Jaringan Server Klien:** Kondisi ketika sistem operasi klien hang total atau konektivitas jaringan terputus, sehingga agen tidak dapat menjangkau server dashboard.

---

## HTTPS & Lingkungan Produksi

Secara bawaan, Pantau Server berjalan menggunakan protokol HTTP pada port 8400. Untuk penggunaan pada lingkungan produksi atau akses melalui jaringan publik, wajib mengonfigurasi reverse proxy Nginx dengan sertifikat SSL (HTTPS).

Repositori ini telah menyediakan templat konfigurasi siap pakai:
- **Konfigurasi Nginx:** `deploy/nginx/pantau-server.conf` (mendukung TLS 1.3, Let's Encrypt, buffer unggah 50M untuk File Manager, dan **WebSocket Upgrade** untuk terminal realtime).
- **Konfigurasi Logrotate:** `deploy/logrotate/pantau-server` (rotasi log harian Uvicorn).

### Langkah Penerapan:

1. Pasang konfigurasi Nginx:
   ```bash
   sudo cp deploy/nginx/pantau-server.conf /etc/nginx/sites-available/pantau-server
   # Buka berkas dan sesuaikan server_name dengan domain Anda:
   sudo nano /etc/nginx/sites-available/pantau-server

   # Aktifkan situs:
   sudo ln -s /etc/nginx/sites-available/pantau-server /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```

2. Pasang sertifikat SSL gratis via Certbot:
   ```bash
   sudo certbot --nginx -d pantau.example.com
   ```

3. Aktifkan proteksi cookie aman pada `/opt/pantau/server/.env`:
   ```env
   SESSION_COOKIE_SECURE=True
   ```
   Lalu restart layanan dashboard:
   ```bash
   sudo systemctl restart pantau-server
   ```

4. Pasang konfigurasi rotasi berkas log:
   ```bash
   sudo cp deploy/logrotate/pantau-server /etc/logrotate.d/pantau-server
   ```

---

## Backup, Restore & Retensi Data

Seluruh data pemantauan tersimpan di basis data MariaDB (`pantau_db`) dan berkas konfigurasi `/opt/pantau/server/.env`.

### Prosedur Pencadangan & Pemulihan:

```bash
# Membuat Cadangan (Backup)
sudo mysqldump -u root pantau_db | gzip > pantau_db-$(date +%F).sql.gz
sudo cp /opt/pantau/server/.env ".env-$(date +%F)"

# Memulihkan Cadangan (Restore)
gunzip -c pantau_db-YYYY-MM-DD.sql.gz | sudo mysql -u root pantau_db
sudo systemctl restart pantau-server
```

Skema struktur basis data bersih tersedia pada berkas `database/schema.sql` (sinkron dengan `server/models.py` v3.15.0).

### Kebijakan Retensi Data Otomatis:

Dashboard secara otomatis melakukan pembersihan berkala setiap jam pada data historis untuk menghemat penggunaan media penyimpanan:
- **Percobaan login:** 1 hari.
- **Snapshot mentah kinerja sistem:** 2 hari (agregasi otomatis per jam disimpan dengan retensi 90 hari).
- **Log permintaan selesai:** 30 hari.
- **Tiket masalah terselesaikan (*resolved problems*):** 90 hari.
- **Riwayat eksekusi perintah:** 180 hari.
- **Jejak audit administratif:** 1 tahun (365 hari).

---

## Catatan Keamanan & Praktik Terbaik

- **Proteksi CSRF:** Seluruh formulir HTTP POST dan permintaan AJAX dilindungi token CSRF berbasis HMAC-SHA256 yang divalidasi ketat pada backend.
- **Sanitasi Data Ketat:** Seluruh payload dari agen (disk, jaringan, daftar proses, keluaran terminal, dan log) disanitasi sebelum disimpan ke basis data atau dirender ke peramban guna mencegah serangan XSS (*Cross-Site Scripting*).
- **Penyimpanan Kredensial Aman:** Kunci API disimpan dalam bentuk hash SHA-256; kata sandi pengguna dienkripsi menggunakan algoritma bcrypt.
- **Prinsip Hak Akses Terkecil (*Least Privilege*):** Izin `sudo` agen dibatasi secara presisi hanya pada skrip wrapper tertentu di `/etc/sudoers.d/pantau-agent`. Operasi service dilindungi daftar terlarang (*deny-list*) untuk mencegah restart layanan kritis secara tidak sengaja.
- **Konfirmasi Tindakan Berisiko:** Operasi destruktif (penghapusan server, pematian sistem, reboot, pemblokiran IP) selalu meminta dialog konfirmasi eksplisit dari pengguna.
- **Header Keamanan HTTP:** Sistem secara bawaan mengaktifkan header Content Security Policy (CSP), X-Frame-Options (DENY), X-Content-Type-Options (nosniff), Referrer-Policy, dan penanganan IP proxy terpercaya.
- **Standar Waktu UTC:** Seluruh pencatatan waktu ditampilkan dalam format UTC agar konsisten lintas zona waktu server yang dipantau.
- **Isolasi Jaringan:** Jangan mengekspos port internal aplikasi (port 8400) langsung ke internet publik tanpa perlindungan reverse proxy dan sertifikat SSL.
