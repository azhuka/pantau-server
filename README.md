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

Installer membuat user, database (dengan password acak), unit systemd, lalu meminta
password admin. Buka `http://<ip-dashboard>:8400` dan login.

Cek: `systemctl status pantau-server.service`

## 2) Install Agent-pantau (tiap server klien)

1. Di dashboard: **Menu Server → Tambah Server** → salin **API key** (simpan di tempat sementara).
2. Di server klien, jalankan 2 baris di bawah ini (unduh installer, lalu jalankan installer):

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh http://<ip-dashboard>:8400 <APIKEY64hex>
```

URL dashboard dan API key di atas dikirim langsung ke installer (tidak ada
pertanyaan). Tanpa kedua argumen itu, installer akan bertanya interaktif.

Cek dashboard web app Pantau Server untuk memvalidasi server klien yang sudah
dipasang agen. Jika ada masalah, cek status layanan agen:

```bash
systemctl status agent_pantau.service
journalctl -u agent_pantau -f
```

## Update

- **Dashboard:** `git pull && sudo bash install-server.sh`
- **Agent:** ulangi 2 baris installer di atas (kode agen akan diperbarui, tanpa menimpa konfigurasi agent pantau).

## Struktur

```
server/          web app dashboard (FastAPI + template) Pantau Server & unit systemd
package/         paket agen pantau klien + file installer (install.sh)
database/        skema SQL referensi
install-server.sh  instalasi dashboard dalam 1 perintah
```

## Catatan keamanan

- API key disimpan hash sha256; password bcrypt; akses sudo agen dibatasi
  hanya ke wrapper tertentu (`/etc/sudoers.d/pantau-agent`).
- Jangan ekspos port 8400 ke internet terbuka tanpa reverse-proxy + HTTPS.