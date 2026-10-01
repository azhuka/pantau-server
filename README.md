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
- [Update OS dari Dashboard](#update-os-dari-dashboard)
- [Kalau Update OS Menggantung](#kalau-update-os-menggantung--terputus)
- [HTTPS untuk Produksi](#https-untuk-produksi)
- [Backup & Restore](#backup--restore)
- [Catatan Keamanan](#catatan-keamanan)

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
| **Rincian server** | Halaman utama tiap server. Tab **Riwayat**, **Layanan** (restart dan hapus service instan via AJAX tanpa reload halaman), **Masalah**, **Jaringan**, **Akun**, **Log**. Terminal Update/Upgrade OS live ala konsol. |
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
(`agen v3.10.0`), dan `server_extras.agent_version` ikut terisi.

> **Installer menarik dari branch `master`, bukan tag.** Isinya bisa berubah
> setiap kali ada commit baru, termasuk commit Anda sendiri. Kalau butuh versi
> yang pasti, jalankan installer dari clone lokal repo Anda (mode `local`).

### Setelah update apa pun

Restart agen **tidak menghapus data**. Yang perlu dicek:

1. Badge versi di Rincian sudah versi baru (`v3.10.0`).
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

## Update OS dari Dashboard

Kotak terminal di halaman Rincian adalah **terminal sungguhan**: output
di-stream dari server — termasuk warna dan karakter `\r` yang menimpa baris,
sama seperti SSH — dan pada mode interaktif Anda **mengetik jawaban langsung di
dalam kotak itu**, tepat setelah prompt, lalu `Enter`.

### Tombol **Update OS**

- Hanya menyegarkan daftar paket (`apt update`) — selalu aman, tanpa pertanyaan.
- Setelah selesai, baris status tepat di bawah tombol langsung menampilkan
  berapa paket yang bisa di-upgrade beserta namanya.

### Tombol **Upgrade** — interaktif

- **Tombol ini aktif setelah Update OS selesai** dan ada paket yang bisa
  di-upgrade. Sebelum itu tombolnya disable, bukan bisa diklik lalu gagal.
- Berjalan di pty, jadi `dpkg` boleh berhenti dan bertanya:
  `zabbix_agent2.conf (Y/I/N/O/D/Z) [default=N] ?`
- Kursor muncul tepat setelah tanda tanya. Ketik jawabannya lalu `Enter`.
- **Agen tidak menebak**: tidak ada auto-answer, dan terminal tidak disisipkan
  catatan tambahan — karakternya digema pty seperti di SSH. Timeout 1 jam.
- Semua yang diketik disalin ke proses di server apa adanya (kontrol/ESC
  dibuang, maks 200 karakter per kiriman).

### Catatan

- Kalau ada proses `apt`/`dpkg` lain sedang jalan, update **ditolak** dengan
  pesan jelas — bukan merusak paket. Tunggu proses itu selesai lalu ulangi.
- Halaman boleh di-refresh di tengah jalan; terminal & kursor ikut tersambung.

## Kalau Update OS Menggantung / Terputus

1. Hentikan prosesnya dari server klien:
   `sudo systemctl restart agent_pantau.service`
2. Rapikan paket yang mungkin terpotong:
   `sudo dpkg --configure -a` lalu `sudo apt-get -f install`.
3. Tekan **Update OS** lagi.

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
