# Pantau Server

Dashboard monitoring terpusat (FastAPI + MariaDB) untuk memantau layanan,
kinerja, log, dan keamanan pada multi-server dari satu halaman + agen pantau dari Python
di tiap server klien.

## 1) Install Dashboard (Server Web App "Pantau Server")

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Installer membuat user, database (dengan password acak), unit systemd, lalu
meminta password untuk user admin (username default: `admin`). Selesai
instalasi, buka `http://<ip-dashboard>:8400` dan login dengan:

- **Username:** `admin`
- **Password:** password yang Anda masukkan saat installer bertanya
  "Password untuk user 'admin':"

Lupa password? Atur ulang dari mesin dashboard:

```bash
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password '<password-baru>'
```

Cek: `systemctl status pantau-server.service`

## 2) Install Agen Pantau (tiap server klien)

1. Di dashboard: **Menu Server → Tambah Server** → salin **API key** (simpan di tempat sementara).
2. Di server klien, jalankan 2 baris di bawah ini (unduh installer, lalu jalankan installer):

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Installer akan **bertanya interaktif**: URL dashboard lalu API key (64 hex),
menguji key-nya dulu ke dashboard, lalu memasang agen pantau serta menghidupkan
layanan agen pantau. Cek dashboard web app Pantau Server untuk memvalidasi
server klien yang sudah dipasang agen. Jika ada masalah, cek status layanan agen:

```bash
systemctl status agent_pantau.service
journalctl -u agent_pantau -f
```

## Update

- **Dashboard:** unduh versi terbaru repo, lalu jalankan ulang `sudo bash install-server.sh`.
  Aman dijalankan ulang: `.env` (termasuk password database) dipertahankan, dependensi
  di-*pip install* ulang dari `requirements.txt`, tabel baru dibuat otomatis.
- **Agen pantau:** jalankan ulang 2 baris installer di atas (kode agen diperbarui, konfigurasi tidak ditimpa).

> Tombol **Reboot OS / Power Off** di halaman Rincian memerlukan agen pantau **v3.7+**
> (upgrade interaktif memerlukan **v3.8+**)
> (badge di halaman Rincian menampilkan versi agen setelah update). Kode agen lama
> menolak perintah itu dan menampilkan hasil "Aksi tidak dikenal".

## Update OS dari Dashboard (tombol Update / Upgrade di halaman Rincian)

Ada dua cara menjalankan upgrade paket, keduanya lewat wrapper `pantau-apt`:

### 1. Tombol **Upgrade** — interaktif (default)

- `apt-get upgrade` berjalan di pty sungguhan, jadi kalau `dpkg` bertanya
  (mis. `Configuration file '/etc/zabbix/zabbix_agent2.conf' ... [default=N] ?`),
  pertanyaannya **muncul di kotak terminal** di halaman Rincian.
- Anda menjawab lewat **kotak jawaban** di bawah terminal (tombol cepat
  `Y` / `N` / `⏎ bawaan` / `D` / `Z`, atau ketik bebas lalu Enter). Karakter
  kontrol dibuang; satu jawaban hanya terkirim sekali.
- **Agen tidak menebak jawaban Anda** — kalau proses diam, terminal hanya menampilkan
  pengingat "Menunggu jawaban Anda". Timeout 1 jam, lalu proses dihentikan paksa.
- Paket yang perlu-an perlu keputusan Anda (mis. paket vendor) bisa ditolak
  dengan `N`; konfigurasi lokal Anda tidak ditimpa diam-diam.
- Jangan menutup halaman/proses sebelum selesai; halaman boleh di-refresh —
  kotak jawaban ikut tersambung kembali.

### 2. Tombol **otomatis** — non-interaktif

- Tanpa pertanyaan sama sekali: konfigurasi yang sudah Anda ubah sendiri
  **tidak ditimpa** (setara menjawab "N" pada prompt `dpkg`), file konfigurasi
  baru memakai bawaan paket, dan `needrestart` merestart tanpa bertanya.
- Cocok untuk update terjadwal/massal di banyak server.

### Keduanya

- **Update OS** hanya menyegarkan daftar paket — selalu aman, tanpa pertanyaan.
- Kalau ada proses `apt`/`dpkg` lain yang sedang jalan, update **ditolak** dengan
  pesan jelas — bukan merusak paket. Tunggu proses itu selesai lalu ulangi.
- Bila proses menggantung tanpa prompt yang dikenali, selesaikan manual:
  `sudo dpkg --configure -a` lalu `sudo apt-get -f install`.

Butuh agen **v3.8+** untuk kotak jawaban interaktif.

### Kalau update sempat menggantung / terputus

1. Tunggu atau hentikan proses: `sudo systemctl restart agent_pantau.service`
   (membunuh proses `apt` yang menggantung).
2. Rapikan paket yang mungkin terpotong: `sudo dpkg --configure -a` lalu
   `sudo apt-get -f install`.
3. Update ulang agen: jalankan ulang 2 baris installer, lalu tekan **Update OS**
   lagi.

## HTTPS (disarankan untuk produksi)

Dashboard memakai HTTP biasa secara bawaan. Untuk akses lewat internet, pasang
reverse-proxy TLS (contoh Nginx + Let's Encrypt) di depan port 8400, lalu:

1. Set `SESSION_COOKIE_SECURE=True` di `/opt/pantau/server/.env` (agar cookie sesi
   hanya terkirim lewat koneksi terenkripsi), lalu `sudo systemctl restart pantau-server`.
2. Blokir akses langsung ke port 8400 dari luar (listen hanya di `127.0.0.1` pada
   sisi proxy).

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

## Backup & restore

Semua data ada di database MariaDB (`pantau_db`) dan konfigurasi `/opt/pantau/server/.env`.

```bash
# Backup
sudo mysqldump -u root pantau_db | gzip > pantau_db-$(date +%F).sql.gz

# Restore
gunzip -c pantau_db-2026-01-01.sql.gz | sudo mysql -u root pantau_db
sudo systemctl restart pantau-server
```

> Untuk instalasi dari nol tanpa `install-server.sh`, gunakan `database/schema.sql`
> (13 tabel, sudah sinkron dengan `server/models.py`).

## Catatan keamanan

- API key disimpan hash sha256; password bcrypt; akses sudo agen dibatasi
  hanya ke wrapper tertentu (`/etc/sudoers.d/pantau-agent`).
- Semua aksi service dari dashboard (restart/start/stop) SELALU lewat wrapper
  `pantau-restart` yang menerapkan deny-list unit kritis — termasuk saat agen
  berjalan sebagai root.
- Sesi login disimpan di database (bertahan restart server) dan bisa dicabut;
  rate-limit login juga persisten.
- Header keamanan aktif (CSP, X-Frame-Options, nosniff, Referrer-Policy).
- Jangan ekspos port 8400 ke internet terbuka tanpa reverse-proxy + HTTPS.