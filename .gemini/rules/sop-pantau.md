# Standar Operasional Prosedur (SOP) Proyek Pantau Server

File ini merupakan aturan baku (rule) otomatis bagi asisten AI dalam mengelola repositori dan pengembangan **Pantau Server**.

---

## 1. Standar Bahasa & Nomenklatur Rilis
- **Bahasa Resmi:** Seluruh judul commit, judul GitHub Release, catatan rilis (*release notes*), serta dokumentasi (`README.md` & `DEVELOPMENT.md`) **wajib menggunakan Bahasa Indonesia yang baku, terstruktur, dan lugas**.
- **Istilah Teknis:** Pertahankan istilah teknis standar dunia komputer, sysadmin, jaringan, dan programmer (misalnya: *CPU, RAM, Swap, Service, Daemon, Systemd, Process, Root, Sudo, Terminal, Watchdog, Egress, Reverse Proxy, Cloudflare WAF, SHA-256, Cron Job, Firewall, Listening Port, Socket*). Jangan diterjemahkan secara kaku atau dibuat bercampur bahasa Inggris jika ada padanan baku yang natural.

---

## 2. Siklus Kenaikan Versi SemVer (Wajib Otomatis)
Setiap kali menyelesaikan perbaikan bug (*patch*), penambahan kapabilitas (*minor*), atau perombakan arsitektur (*major*):
1. **Wajib Menaikkan Versi**: Jangan pernah menunggu diminta. Naikkan versi Pantau Server dan Agen Pantau secara bertahap:
   - `server/config.py` (`APP_VERSION`)
   - `server/templates/base.html` (`v{{ app_version ... }}`)
   - `package/opt/pantau/agent/agent_pantau.py` (`AGENT_VERSION`)
   - `agent/agent_pantau.py` (sinkron identik)
   - `package/install.sh` (User-Agent installer)
   - `README.md` (header & deskripsi)
   - `DEVELOPMENT.md` (blok changelog rilis baru)
2. **Kompilasi & Uji Sintaksis**: Pastikan seluruh berkas lulus `python3 -m py_compile` dan `bash -n`.
3. **Restart Service Pusat**: Jalankan `sudo systemctl restart pantau-server.service` dan pastikan berstatus `active`.

---

## 3. Alur Git, Tag & GitHub Releases (Satu Rangkaian Kerja)
Setiap kali perubahan selesai diuji:
1. **Commit & Push**:
   ```bash
   git add <berkas>
   git commit -m "jenis(lingkup): deskripsi bahasa baku"
   git push origin master
   ```
2. **Git Tag**:
   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z: Judul Bahasa Indonesia Baku"
   git push origin vX.Y.Z
   ```
3. **GitHub Release (Wajib Diterbitkan Langsung)**:
   Gunakan GitHub CLI (`gh`) untuk membuat rilis di halaman releases dengan judul Bahasa Indonesia baku dan catatan terstruktur:
   ```bash
   gh release create vX.Y.Z \
     --title "vX.Y.Z - Judul Baku Bahasa Indonesia dengan Istilah Teknis" \
     --notes "..."
   ```

---

## 4. Keamanan & Integritas Agen Klien
- Setiap perubahan pada berkas agen harus kompatibel dengan Python 3.10+ tanpa dependensi pustaka luar (*zero-dependency*).
- Setiap instruksi atau wrapper sudo harus berprinsip hak akses terkecil (*least privilege*) dan aman dari *shell injection* (`shell=False`).
