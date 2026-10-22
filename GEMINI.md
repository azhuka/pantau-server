# Workspace Rules: Pantau Server Development

File ini adalah aturan baku (*always-on project rule*) bagi asisten AI dalam memelihara dan mengembangkan proyek **Pantau Server**.

---

## 1. Esensi Sistem Pantau Server
- **Sistem Monitoring NOC Mandiri:** Berorientasi pada kemudahan observasi, stabilitas operasional, dan kepadatan data tinggi (*high density*).
- **Standar Bahasa:** Seluruh judul commit, rilis GitHub, dokumentasi (`README.md`, `DEVELOPMENT.md`), dan antarmuka web wajib menggunakan **Bahasa Indonesia yang baku, terstruktur, dan lugas**, dengan tetap mempertahankan istilah teknis komputer/sysadmin standar dunia (CPU, RAM, S.M.A.R.T., NVMe, Daemon, Systemd, Root, Sudo, dll.).

---

## 2. Alur Kerja Wajib (Workflow)

### A. Sebelum & Saat Men-generate Kode
- Pertahankan prinsip *zero external dependency* pada agen klien (hanya Python 3.10+ standard library).
- Hindari eksekusi shell tanpa sanitasi (`shell=False`, least-privilege).
- Desain antarmuka berprinsip kepadatan data NOC (padding sel rapat 3px-6px, tinggi baris ~30-34px, ukuran font badge proporsional 9.5px, hindari whitespace berlebihan).

### B. Setelah Men-generate Kode (Wajib Otomatis — Jangan Pernah Menunggu Diminta)
Setiap kali menyelesaikan pekerjaan (bugfix/fitur baru/refactor):
1. **Menaikkan Versi SemVer Secara Sinkron di 7 Berkas:**
   - `server/config.py` (`APP_VERSION`)
   - `server/templates/base.html` (`v{{ app_version ... }}`)
   - `package/opt/pantau/agent/agent_pantau.py` (`AGENT_VERSION`)
   - `agent/agent_pantau.py` (sinkron identik)
   - `package/install.sh` (User-Agent installer)
   - `README.md` (deskripsi & fitur utama)
   - `DEVELOPMENT.md` (blok changelog rilis baru dengan format terstruktur)
2. **Kompilasi & Uji Sintaksis:**
   - `python3 -m py_compile` seluruh berkas python terkait.
   - `bash -n` seluruh berkas skrip shell terkait.
3. **Penyebaran Agen & Restart Service:**
   - Salin agen ke `/opt/pantau/agent/agent_pantau.py`.
   - `sudo systemctl restart agent_pantau.service`
   - `sudo systemctl restart pantau-server.service` dan pastikan status `active`.
4. **Git, Tag & GitHub Release:**
   - `git add <berkas>`
   - `git commit -m "jenis(lingkup): deskripsi baku (vX.Y.Z)"`
   - `git push origin master`
   - `git tag -a vX.Y.Z -m "Release vX.Y.Z: Judul Baku"`
   - `git push origin vX.Y.Z`
   - `gh release create vX.Y.Z --title "vX.Y.Z - Judul Baku" --notes "..."`
