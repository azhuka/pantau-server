---
name: sop-pantau
description: SOP baku alur kerja pengembangan Pantau Server. Meliputi esensi sistem NOC, alur sebelum/saat/sesudah men-generate kode, otomatisasi kenaikan versi SemVer (7 berkas), kompilasi & uji sintaksis, restart service, serta alur Git commit, push, git tag, dan GitHub Release berbahasa Indonesia baku.
---

# Standar Operasional Prosedur (SOP) Proyek Pantau Server

Prosedur ini merupakan keharusan baku bagi AI/developer dalam mengelola repositori dan pengembangan **Pantau Server**.

---

## 1. Esensi Sistem Pantau Server
- **Tujuan Sistem:** Sistem pemantauan infrastruktur dan manajemen armada server Linux internal NOC/Sysadmin yang ringan, andal, dan minim dependensi.
- **Karakteristik Desain:**
  - **Kepadatan Informasi NOC (NOC-Density):** Tampilan tabel rapat, ringkas, tinggi baris efisien (~30–34px), teks proporsional, hemat ruang vertikal tanpa padding berlebihan.
  - **Bahasa & Label Baku:** Menggunakan Bahasa Indonesia baku untuk antarmuka dan rilis dengan tetap mempertahankan istilah teknis standar (CPU, RAM, S.M.A.R.T., NVMe, Daemon, Systemd, Root, Sudo, dll.).
  - **Akurasi Diagnosa & Tanpa Alarm Palsu:** Deteksi platform (Virtual/Host) untuk mencegah false alarm pada drive virtual, pemisahan severity yang akurat (Tier 1/2/3).

---

## 2. Alur Kerja (Workflow) Pengembangan

### A. Sebelum Men-generate Kode (Before)
1. Pahami esensi masalah dan kebutuhan operasional NOC tanpa menambah kerumitan yang tidak diminta.
2. Periksa arsitektur eksisting, struktur database, dan kompatibilitas sistem.
3. Pastikan agen klien tetap berprinsip *zero external dependency* (Python 3.10+ standard library saja) dan keamanan eksekusi perintah shell (`shell=False`, least-privilege).

### B. Saat Men-generate Kode (During)
1. Terapkan perubahan secara presisi baik di backend (FastAPI/Jinja/SQLite) maupun agen klien.
2. Jaga integritas sinkronisasi antara agen live (`/opt/pantau/agent/agent_pantau.py`), paket repositori (`package/opt/pantau/agent/agent_pantau.py`), dan `agent/agent_pantau.py`.
3. Jaga penanganan error yang kuat (*fail-safe*) dan jangan biarkan proses background macet (*hung*).

### C. Setelah Men-generate Kode (After — WAJIB OTOMATIS)
Setiap kali menyelesaikan perbaikan bug (*patch*), penambahan fitur (*minor*), atau perombakan (*major*):
1. **Menaikkan Versi SemVer Secara Sinkron di 7 Berkas:**
   - `server/config.py` (`APP_VERSION`)
   - `server/templates/base.html` (`v{{ app_version ... }}`)
   - `package/opt/pantau/agent/agent_pantau.py` (`AGENT_VERSION`)
   - `agent/agent_pantau.py` (sinkron identik)
   - `package/install.sh` (User-Agent installer)
   - `README.md` (header & fitur utama)
   - `DEVELOPMENT.md` (blok changelog rilis baru dengan tanggal dan detail lengkap)
2. **Kompilasi & Uji Sintaksis:**
   - Jalankan `python3 -m py_compile` pada seluruh berkas Python yang diubah.
   - Jalankan `bash -n` pada seluruh berkas skrip shell yang diubah.
3. **Penyebaran Agen & Restart Service Pusat:**
   - Salin agen yang diperbarui ke `/opt/pantau/agent/agent_pantau.py`.
   - Restart service agen: `sudo systemctl restart agent_pantau.service`.
   - Restart server pusat: `sudo systemctl restart pantau-server.service` dan pastikan status `active`.
4. **Alur Git, Tag & GitHub Releases (Satu Rangkaian Kerja Tanpa Menunggu Diminta):**
   - Stage semua berkas terkait: `git add <berkas>`
   - Commit dengan pesan deskriptif Bahasa Indonesia baku:
     `git commit -m "jenis(lingkup): deskripsi bahasa baku (vX.Y.Z)"`
   - Dorong commit ke repositori utama:
     `git push origin master`
   - Buat tag beranotasi:
     `git tag -a vX.Y.Z -m "Release vX.Y.Z: Judul Bahasa Indonesia Baku"`
   - Dorong tag ke remote:
     `git push origin vX.Y.Z`
   - Terbitkan GitHub Release melalui GitHub CLI (`gh`):
     `gh release create vX.Y.Z --title "vX.Y.Z - Judul Baku Bahasa Indonesia" --notes "..."`

---

## 3. Kebijakan Khusus Proxmox HA & Proteksi Mesin
- VM atau LXC dengan `is_proxmox_ha = 1` dilarang dimatikan dari dalam via tombol *Power OFF*.
- Tombol *Power OFF* dinonaktifkan (`disabled`, kursor `not-allowed`) dan backend menolak request dengan pesan peringatan resmi.
