# Pantau Server

Dashboard pemantauan dan pengelolaan multi-server Linux berbasis web (FastAPI + MariaDB) dengan agen klien Python mandiri (*zero-dependency*). Memantau performa CPU, RAM, Disk, Jaringan, dan layanan sistem secara real-time tanpa memerlukan port masuk terbuka (*outbound-only*).

---

## 1. Pemasangan Dashboard (Server Pusat)

Dukungan sistem operasi: **Ubuntu 20.04 / 22.04 / 24.04 LTS** atau **Debian 11 / 12**.

```bash
# 1. Clone repositori dan masuk ke direktori
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server

# 2. Jalankan skrip instalasi
sudo bash install-server.sh
```

Setelah instalasi selesai, buka dashboard melalui peramban:
- **Alamat:** `http://<IP-SERVER>:8400`
- **Username:** `admin`
- **Password:** Kata sandi yang Anda tentukan saat instalasi

---

## 2. Pemasangan Agen (Server Klien yang Dipantau)

Agen klien berjalan murni menggunakan pustaka standar Python 3.10+ (mendukung Ubuntu, Debian, Proxmox, Rocky Linux, AlmaLinux, RHEL, CentOS, Fedora, openSUSE, dan Arch Linux).

### Langkah Pemasangan:
1. Buka dashboard web, masuk ke menu **Daftar Server → Tambah Server**, lalu salin **API Key**.
2. Jalankan perintah instalasi satu-langkah di server klien:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Masukkan **URL Dashboard** (contoh: `http://192.168.1.10:8400`) dan **API Key** saat diminta. Server akan otomatis terhubung dan berstatus online di dashboard dalam ~10 detik.

> **Mode Otomatis (Skrip / Non-Interaktif):**
> ```bash
> sudo bash /tmp/pantau-install.sh "http://<IP-DASHBOARD>:8400" "<API_KEY>"
> ```

---

## 3. Perintah Operasional Dasar

### Layanan Dashboard (Server Pusat)
```bash
# Memeriksa status service
sudo systemctl status pantau-server.service

# Restart service dashboard
sudo systemctl restart pantau-server.service

# Reset kata sandi administrator jika lupa
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password 'password-baru'

# Memperbarui dashboard ke versi terbaru
cd /opt/pantau/server/pantau-server
git pull && sudo bash install-server.sh
```

### Layanan Agen (Server Klien)
```bash
# Memeriksa status service agen
sudo systemctl status agent_pantau.service

# Melihat log aktivitas agen secara langsung
sudo journalctl -u agent_pantau -f

# Restart service agen
sudo systemctl restart agent_pantau.service
```
