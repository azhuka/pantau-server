# Pantau Server

Dashboard monitoring terpusat (FastAPI + MariaDB) untuk memantau layanan,
kinerja, log, dan keamanan banyak server dari satu halaman, memakai agen Python
di tiap server klien.

## 1) Instal Dashboard (mesin pusat)

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Installer membuat user, database (password acak), unit systemd, lalu meminta
password admin. Buka `http://<ip>:8400` dan login.

Cek: `systemctl status pantau-server.service`

## 2) Pasang Agent (tiap mesin klien)

1. Di dashboard: **Menu Server → Tambah Server** → salin **API key** (64 hex).
2. Di mesin klien, jalankan 2 baris ini (unduh installer lalu jalankan — tidak
   perlu git, tidak men-download seluruh repo):

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh http://<ip-dashboard>:8400 <APIKEY64hex>
```

Tanpa argumen URL/key, installer akan bertanya interaktif. Agent siap bila di
dashboard server klien tampil **online**.

Cek di klien: `systemctl status agent_pantau.service`

## Update

- **Dashboard:** `git pull && sudo bash install-server.sh`
- **Agent:** ulangi 2 baris installer di atas (kode agen diperbarui, config
  tidak ditimpa).

## Struktur

```
server/          web app dashboard (FastAPI + template) & unit systemd
package/         paket agen klien + installer satu-file install.sh
database/        skema SQL referensi
install-server.sh  pemasangan dashboard dalam 1 perintah
```

## Catatan keamanan

- API key disimpan hash sha256; password bcrypt; akses sudo agen dibatasi
  hanya ke wrapper tertentu (`/etc/sudoers.d/pantau-agent`).
- Jangan ekspos port 8400 ke internet terbuka tanpa reverse-proxy + HTTPS.