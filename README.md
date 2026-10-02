# Pantau Server

Dashboard monitoring terpusat (FastAPI + MariaDB) untuk memantau kondisi,
kinerja, log, dan keamanan banyak server dari satu halaman, ditambah **agen
Pantau** (Python) yang jalan di tiap server klien.

## Daftar isi

- [1. Install Dashboard](#1-install-dashboard-server-web-app-pantau-server)
- [2. Install Agen di Server Klien](#2-install-agen-di-server-klien)
- [Halaman & Fitur](#halaman--fitur)
- [Peran Admin vs Viewer](#peran-admin-vs-viewer)
- [Update Dashboard](#update-dashboard)
- [Update Agen](#update-agen)
- [Kebutuhan Versi Agen](#kebutuhan-versi-agen)
- [Konsol Terminal & Update OS](#konsol-terminal--update-os-dari-dashboard)
- [Kalau Update OS Menggantung / Terputus](#kalau-update-os-menggantung--terputus)
- [HTTPS untuk Produksi](#https-untuk-produksi)
- [Backup & Restore](#backup--restore)
- [Catatan Keamanan & Praktik Terbaik](#catatan-keamanan--praktik-terbaik)

## 1. Install Dashboard (Server Web App "Pantau Server")

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Installer membuat user, database (password acak), unit systemd, lalu meminta
password untuk user admin. Selesai instalasi, buka `http://<ip-dashboard>:8400`
dan login:

- **Username:** `admin`
- **Password:** password yang Anda masukkan saat installer bertanya
  "Password untuk user 'admin':"

Lupa password? Atur ulang dari mesin dashboard:

```bash
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password '<password-baru>'
```

Cek: `systemctl status pantau-server.service`

## 2. Install Agen di Server Klien

1. Di dashboard: menu **Servers → Tambah Server** → salin **Kunci API**
   (disimpan di tempat sementara).
2. Di server klien, unduh lalu jalankan installer:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Installer bertanya interaktif: URL dashboard lalu Kunci API (64 hex), menguji
key-nya dulu ke dashboard, lalu memasang agen dan menghidupkan layanannya.
Verifikasi di dashboard — daftar server berubah dari "belum ada data" jadi
online dalam ±10 detik.

Kalau ada masalah:

```bash
systemctl status agent_pantau.service
journalctl -u agent_pantau -f
```

Installer aman dijalankan ulang: kalau `/etc/pantau/config.json` sudah ada dan
isinya valid, URL + Kunci API diambil dari sana sehingga **tidak ditanya lagi**.
Kalau belum ada, installer memintanya (dan bisa dilewati dengan
`sudo bash install.sh <URL> <KUNCI_API>`, atau non-interaktif lewat
`SETUP_SERVER_URL=... SETUP_API_KEY=...`).

> Kalau Anda menjalankan `curl | bash`, ONLY THE AGENT FILE yang diunduh per-file
> dari GitHub, bukan satu repo penuh. Kalau Anda menjalankan installer dari dalam
> clone lokal, semua file diambil dari folder lokal — pakai mode ini kalau
> butuh versi yang pasti.

## Halaman & Fitur

| Halaman | Isi |
|---|---|
| **Dashboard** | Ringkasan semua server: jumlah online/offline, layanan down, laporan terakhir. Kotak pencarian instan (*real-time* server/IP/OS) dan shortcut satu-klik salin IP ke clipboard. |
| **Servers** | Kelola server: tambah, edit, hapus, lihat kunci API, kotak pencarian instan, dan shortcut salin IP. |
| **Rincian server** | Halaman utama tiap server. Tab **Riwayat**, **Layanan** (restart dan hapus service instan via AJAX tanpa reload halaman), **Masalah**, **Jaringan**, **Akun**, **Log**. Terminal bawaan Linux tertanam di halaman (tombol `>_ Terminal`) yang juga menampilkan proses Update/Upgrade OS secara live. |
| **Masalah** | Semua masalah terbuka lintas server dengan level (Danger / Warning / Info), durasi, dan tips penanganan. |
| **Log** | Log server pusat: CPU/memori/beban/swap, proses teratas, disk, log service (pilih unit), dan log aplikasi. |
| **Audit** | Jejak aksi admin: login, kelola server/service/user, perintah remote (restart, blokir IP, update paket, restart agen). |
| **Users** | *(Admin)* Kelola user dashboard: tambah, ubah peran, reset password, cabut sesi. |

Semua angka pada Dashboard, Rincian, dan Masalah berasal dari satu sumber
status yang sama, jadi satu server tidak pernah tampil berbeda di dua halaman.

Warna badge punya arti yang konsisten: **hijau** sehat/berhasil, **merah**
bermasalah, **kuning** perlu perhatian, **biru** informasi, **abu-abu** netral
(menunggu / belum ada data / tidak berlaku).

> Halaman Metrik tidak lagi ada. Semua metrik per-service (status, connection,
> response time) kini berada di tab **Layanan** pada halaman Rincian. Tautan lama
> `/servers/<id>/metrics` otomatis dialihkan ke sana.

## Peran Admin vs Viewer

| | Admin | Viewer |
|---|---|---|
| Lihat Dashboard, Servers, Rincian, Masalah, Log | Ya | Ya |
| Tambah / edit / hapus server & service | Ya | Tidak |
| Update OS, Upgrade, Reboot OS, Power Off | Ya | Tidak |
| Restart / hapus service | Ya | Tidak |
| Blokir IP (& mitigasi lain) / restart agen | Ya | Tidak |
| Halaman Audit & Users | Ya | Tidak |

Viewer yang membuka Rincian akan melihat badge "Update OS aktif untuk Admin"
di tempat tombol, bukan tombol mati yang tidak melakukan apa pun.

## Update Dashboard

```bash
git pull
sudo bash install-server.sh
```

Aman dijalankan ulang: `.env` (termasuk password database) dipertahankan,
dependensi di-*pip install* ulang, tabel baru dibuat otomatis.

## Update Agen

**Dashboard tidak punya akses ke server klien** — tidak ada SSH, tidak ada
mekanisme push. Dashboard hanya mengirim perintah lewat agen yang sudah
melapor. Jadi **upgrade agen selalu manual, di shell server tersebut**.

### Server klien

Jalankan ulang installer yang sama (lihat
[Install Agen](#2-install-agen-di-server-klien)). Konfigurasi tidak ditimpa.
Untuk banyak server, jalankan dari Ansible, parallel SSH, atau tools konfigurasi
yang Anda pakai.

### Host dashboard sendiri

Kalau dashboard juga dipantau oleh agennya sendiri, update agen di sana
dengan cara yang sama persis — salin file dari repo:

```bash
cd pantau-server
sudo install -m 755 -o root -g root package/opt/pantau/agent/agent_pantau.py \
  /opt/pantau/agent/agent_pantau.py
sudo install -m 750 -o root -g root package/usr/local/sbin/pantau-apt \
  /usr/local/sbin/pantau-apt
sudo python3 -m py_compile /opt/pantau/agent/agent_pantau.py
sudo systemctl restart agent_pantau.service
```

Verifikasi: badge di Rincian host tersebut harus berubah ke versi baru
(`agen v3.11.0`), dan `server_extras.agent_version` ikut terisi.

> **Installer menarik dari branch `master`, bukan tag.** Isinya bisa berubah
> setiap kali ada commit baru, termasuk commit Anda sendiri. Kalau butuh versi
> yang pasti, jalankan installer dari clone lokal repo Anda (mode `local`).

### Setelah update apa pun

Restart agen **tidak menghapus data**. Yang perlu dicek:

1. Badge versi di Rincian sudah versi baru (`v3.11.0`).
2. Server kembali online dalam ±10 detik.
3. Kalau agen upgrade OS, tekan **Update OS** sekali — jawabannya langsung
   tampil tanpa perlu polling ulang dan tombol Upgrade seketika aktif jika ada paket.

## Kebutuhan Versi Agen

Badge versi agen ada di bagian atas halaman Rincian tiap server.

| Fitur | Agen minimum |
|---|---|
| Monitoring, log, service, restart service | v3.6 |
| Reboot OS / Power Off dari dashboard | v3.6 |
| Terminal Update/Upgrade OS (warna + `\r` seperti SSH) | v3.7 |
| Terminal Upgrade **interaktif** (jawab prompt dpkg) | v3.9 |
| Proteksi sanitasi ketat, mitigasi loop retry, & aktivasi instan upgrade | v3.10 |
| Konsol Terminal Bawaan (shell prompt `root@host:~#`, riwayat perintah, reparasi mandiri `dpkg --configure -a`) | v3.11 |

Agen lebih lama dari requirements **tetap jalan untuk fitur lain** — hanya
fitur terkait yang menolak dengan pesan jelas, bukan gagal diam-diam. Contoh:
agen v3.7 yang menerima perintah Upgrade interaktif akan menampilkan "Aksi tidak
dikenal".

Untuk mengecek versi semua server sekaligus:

```sql
SELECT s.hostname, x.agent_version
FROM servers s
LEFT JOIN server_extras x ON x.server_id = s.id
ORDER BY x.agent_version, s.hostname;
```

`NULL` atau versi kosong artinya agen belum pernah mengirim laporan extras.

## Konsol Terminal & Update OS dari Dashboard

Jendela terminal di halaman Rincian dirancang layaknya **konsol terminal Linux/SSH sungguhan** yang bersih dan bebas distraksi. Terminal tertanam langsung di halaman (bukan jendela browser terpisah) dan bisa dibuka kapan saja lewat tombol **`>_ Terminal`** di baris hero.
- **Tampilan Konsol Autentik**: Titlebar lengkap dengan tombol window, label `root@<hostname>:~ (Terminal Bawaan)`, tombol Clear/Tutup, status proses berjalan, dan kursor blok berkedip (`█`) yang berganti warna saat shell menganggur.
- **Emulasi Output**: Kode warna ANSI, efek tebal, serta carriage-return (`\r`) progress bar digambar seperti terminal asli. Baris kosong ekor tidak menumpuk, layar dibatasi 4000 baris agar tetap ringan.
- **Input Universal**: Menerima **semua** jenis input interaktif saat proses berjalan (angka pilihan konfigurasi seperti `1`, `2`, `35`, huruf `Y`/`n`/`I`/`O`, maupun `Enter`).
- **Riwayat Perintah**: `↑` / `↓` menelusuri perintah yang pernah diketik di konsol.
- **Pintasan Keyboard**: `Enter` kirim, `Backspace` hapus, `Tab` spasi (fokus tidak berpindah), `Ctrl+C` batal, `Ctrl+L` bersihkan layar, `Esc` kosongkan baris input.
- **Mode Shell Langsung**: Saat idle, prompt `root@<hostname>:~#` siap menerima perintah langsung:
  - `update` atau `apt update`: Sinkronisasi daftar paket.
  - `upgrade` atau `apt upgrade`: Upgrade paket OS tertunda (interaktif).
  - `dist-upgrade` atau `full-upgrade`: Upgrade penuh termasuk dependensi dan kernel baru.
  - `dpkg --configure -a` atau `fix`: Reparasi mandiri paket terhenti & dependensi rusak.
  - `clear`: Bersihkan isi layar terminal.
  - `help`: Panduan ringkas perintah di konsol.
  - Awalan `sudo` dan flag umum (`-y`, `--assume-yes`) otomatis diabaikan karena unit yang dijalankan sudah dikunci server.
- **Perilaku seperti SSH**: Saat proses non-interaktif berjalan (mis. `apt update`), baris input disembunyikan — persis seperti shell foreground yang tidak menampilkan prompt. Baris input baru muncul lagi setelah proses selesai atau saat proses interaktif menunggu jawaban.

### Tombol **Update OS**

- Menyegarkan daftar paket (`apt update`) — aman dan non-interaktif.
- Baris status tepat di bawah tombol langsung menampilkan jumlah dan nama paket yang siap di-upgrade.

### Tombol **Upgrade** — interaktif

- Aktif otomatis seketika setelah Update OS menemukan paket tertunda.
- Berjalan di pty: dpkg dapat berinteraksi penuh dengan admin melalui konsol terminal. Jawaban (angka/huruf/Enter) dikirim langsung ke proses di server klien.
- Proses bisa dijemput kembali: kalau halaman sempat di-reload atau ditutup, Dashboard otomatis menyambung lagi ke proses yang masih berjalan di server klien dan menampilkan sisa output-nya.

### Kalau Update OS Menggantung / Terputus

| Gejala | Penanganan |
|---|---|
| Status macet di `berjalan` lalu menjadi `Gagal — batas waktu habis` | Tunggu 2 menit (jeda anti-resume), lalu buka lagi halaman Rincian. Dashboard akan menyambung otomatis ke proses yang masih ada di server klien. |
| `apt update` tidak selesai dalam ±5 menit (wajar) | Periksa konektivitas server klien ke repositori paket, lalu ulangi. |
| `upgrade` tidak selesai dalam ±15 menit | Upgrade besar (kernel/dependensi) memang bisa lama. Biarkan, atau periksa status dari Tab **Log**. |
| Proses interaktif (`upgrade`, `dist-upgrade`, `fix`) tidak selesai dalam ±60 menit | Kemungkinan menunggu jawaban yang belum dikirim. Buka terminal, ketik jawaban atau `Enter` pada baris `›`. |
| `dpkg` terkunci / paket terhenti setelah proses mati mendadak | Jalankan `fix` (atau `dpkg --configure -a`) di terminal konsol, atau gunakan tombol **Restart Agen** di tab **Masalah**. |

Batas waktu di atas hanya batas tunggu *tampilan di Dashboard* — proses di server klien tidak dibunuh. Kill proses yang benar-benar macet harus dilakukan lewat SSH atau tombol **Reboot OS**.

## Kapan Memerlukan Remote Langsung (SSH)?

Dengan konsol terminal interaktif dan fitur reparasi `dpkg --configure -a` di Dashboard:
1. **90% pemeliharaan rutin** (update patch keamanan, upgrade paket, konfirmasi Y/n, penanganan paket terhenti) **cukup dan efisien diselesaikan langsung dari web Dashboard** tanpa perlu membuka terminal SSH satu per satu.
2. **Kondisi darurat yang tetap mewajibkan remote langsung (SSH)**:
   - **Upgrade Versi Distro Mayor** (misal Debian 11 ke 12, atau Ubuntu 22.04 ke 24.04) yang berpotensi memutus network stack/service di tengah instalasi kernel baru.
   - **Dialog Konfigurasi Layar Penuh (TUI/ncurses)**: Prompt debconf layar biru yang membutuhkan tombol navigasi Panah/Tab/Spasi.
   - **Gangguan Jaringan / Mesin Crash**: Kondisi saat Agen Pantau tidak dapat terhubung ke Dashboard.

## HTTPS untuk Produksi

Dashboard memakai HTTP biasa secara bawaan. Untuk akses lewat internet, pasang
reverse-proxy TLS (contoh Nginx + Let's Encrypt) di depan port 8400, lalu:

1. Set `SESSION_COOKIE_SECURE=True` di `/opt/pantau/server/.env` (agar cookie
   sesi hanya dikirim lewat koneksi terenkripsi), lalu
   `sudo systemctl restart pantau-server`.
2. Blokir akses langsung ke port 8400 dari luar (listen hanya di `127.0.0.1`
   pada sisi proxy).

Contoh petak Nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name pantau.example.com;
    ssl_certificate     /etc/letsencrypt/live/pantau.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pantau.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8400;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Backup & Restore

Semua data ada di database MariaDB (`pantau_db`) dan konfigurasi
`/opt/pantau/server/.env`. Keduanya perlu di-backup.

```bash
# Backup
sudo mysqldump -u root pantau_db | gzip > pantau_db-$(date +%F).sql.gz
sudo cp /opt/pantau/server/.env ".env-$(date +%F)"

# Restore
gunzip -c pantau_db-2026-01-01.sql.gz | sudo mysql -u root pantau_db
sudo systemctl restart pantau-server
```

Untuk instalasi dari nol tanpa `install-server.sh`, gunakan
`database/schema.sql` (13 tabel, sudah sinkron dengan `server/models.py`).

Data historis dibersihkan otomatis agar tabel tidak tumbuh tanpa batas:
percobaan login 1 hari, log request 30 hari, perintah 180 hari, audit 1 tahun.

## Catatan Keamanan & Praktik Terbaik

- **Proteksi CSRF**: Seluruh form POST dan request AJAX dilindungi token CSRF berbasis HMAC-SHA256 yang divalidasi ketat pada backend.
- **Penanganan Error Terpadu**: Halaman kendala kustom (`error.html`) untuk status HTTP 404, 500, dan 403 dengan pesan berbahasa Indonesia yang jelas serta tombol navigasi mandiri.
- **Sanitasi Data Ketat**: Seluruh laporan agen (disk, net, proses, log stream) disanitasi dari karakter berbahaya sebelum disimpan ke database atau dirender ke DOM (pencegahan injeksi XSS).
- API key disimpan hash sha256; password bcrypt; akses sudo agen dibatasi hanya ke wrapper tertentu (`/etc/sudoers.d/pantau-agent`).
- Semua aksi service dari dashboard **selalu** lewat wrapper `pantau-restart` yang menerapkan deny-list unit kritis — termasuk saat agen berjalan sebagai root. Aksi reboot/poweroff lewat wrapper `pantau-host`, dengan preflight yang menolak perintah bila wrapper/sudoers belum terpasang.
- Aksi berisiko (hapus server, reboot, poweroff, blokir IP, tandai semua ditangani) selalu meminta konfirmasi pengguna.
- Sesi login disimpan di database (bertahan restart server) dan bisa dicabut; rate-limit login juga persisten.
- Header keamanan aktif (CSP, X-Frame-Options, nosniff, Referrer-Policy, IP proxy filtering).
- Waktu ditampilkan dalam **UTC** (terlihat di sidebar) supaya tidak ambigu di semua server.
- Jangan ekspos port 8400 ke internet terbuka tanpa reverse-proxy + HTTPS.
