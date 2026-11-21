---
name: sop-pantau
description: SOP baku alur kerja dan eksekusi rilis produksi Pantau Server. Panduan otomatisasi SemVer 7 berkas via tools/sop_release.py, uji sintaksis, restart daemon systemd, alur git/tag/GitHub Release, serta kueri verifikasi lapangan 100% armada klien di MySQL.
---

# SOP Alur Kerja & Eksekusi Rilis Produksi Pantau Server

Berkas ini adalah panduan kerja prosedural (*actionable runbook*) bagi pengembang/AI untuk menguji, membangun, merilis, dan memvalidasi penyebaran versi baru Pantau Server secara atomik dan terstandarisasi.

---

## 1. Protokol Pengujian Sintaksis & Integritas Sebelum Rilis
Sebelum memicu skrip rilis, seluruh berkas yang dimodifikasi wajib diuji secara mandiri:

```bash
# 1. Uji sintaksis seluruh skrip Python yang diubah
/home/bos/rj45/env/bin/python3 -m py_compile server/config.py agent/agent_pantau.py package/opt/pantau/agent/agent_pantau.py

# 2. Uji sintaksis seluruh skrip shell
bash -n package/install.sh

# 3. Validasi parsing Jinja template
/home/bos/rj45/env/bin/python3 -c "
import jinja2
env = jinja2.Environment(loader=jinja2.FileSystemLoader('/home/bos/rj45/server/templates'))
env.get_template('base.html')
env.get_template('services.html')
"
```

---

## 2. Eksekusi Otomasi Rilis Satu Perintah (`tools/sop_release.py`)
Setiap kali menyelesaikan perbaikan bug atau penambahan fitur, **wajib menggunakan skrip otomatisasi satu perintah [`tools/sop_release.py`](file:///home/bos/rj45/tools/sop_release.py)** agar seluruh rangkaian rilis selesai secara atomik dalam **15–30 detik**:

```bash
./tools/sop_release.py [versi_baru] \
  --commit-msg "jenis(lingkup): deskripsi bahasa baku (vX.Y.Z)" \
  --title "vX.Y.Z - Judul Baku Bahasa Indonesia" \
  --notes "Rincian rilis untuk GitHub Releases" \
  --changelog "Blok catatan teknis untuk dimasukkan ke DEVELOPMENT.md" \
  --extra-files <berkas_tambahan_yang_diubah>
```

### 7 Berkas SemVer yang Dinaikkan Sinkron Otomatis oleh Skrip:
1. `server/config.py` (`APP_VERSION`)
2. `server/templates/base.html` (`v{{ app_version ... }}`)
3. `package/opt/pantau/agent/agent_pantau.py` (`AGENT_VERSION`)
4. `agent/agent_pantau.py` (sinkron identik)
5. `package/install.sh` (User-Agent installer & meta-version)
6. `README.md` (deskripsi & fitur utama)
7. `DEVELOPMENT.md` (blok changelog rilis baru dengan format terstruktur)

---

## 3. Alur Penyebaran Lokal & Restart Daemon
Skrip rilis secara otomatis mengeksekusi penyebaran lokal:
1. Menyalin agen lokal:
   ```bash
   sudo cp agent/agent_pantau.py /opt/pantau/agent/agent_pantau.py
   ```
2. Me-restart layanan systemd lokal:
   ```bash
   sudo systemctl restart agent_pantau.service pantau-server.service
   ```
3. Memastikan status layanan aktif:
   ```bash
   sudo systemctl is-active agent_pantau.service pantau-server.service
   ```

---

## 4. Alur Git, Tag, & GitHub Release
Skrip rilis secara otomatis mempublikasikan rilis:
1. `git add <berkas>`
2. `git commit -m "jenis(lingkup): deskripsi baku (vX.Y.Z)"`
3. `git push origin master`
4. `git tag -a vX.Y.Z -m "Release vX.Y.Z: Judul Baku"`
5. `git push origin vX.Y.Z`
6. `gh release create vX.Y.Z --title "vX.Y.Z - Judul Baku" --notes "..."`

---

## 5. Verifikasi Lapangan Mutlak 100% Armada Klien di Basis Data (Wajib)
**Dilarang keras menyatakan tugas selesai hanya karena skrip build/rilis berhasil.** 

Pengembang/AI **WAJIB melakukan kueri verifikasi langsung ke basis data** untuk membuktikan bahwa 100% server klien aktif telah menerima perintah pembaruan OTA, me-restart agen, dan melaporkan versi baru ke server:

```bash
PYTHONPATH=/home/bos/rj45/server /home/bos/rj45/env/bin/python -c "
from sqlalchemy import create_engine, text
from config import settings

engine = create_engine(settings.database_url)
with engine.connect() as conn:
    res = conn.execute(text('''
        SELECT s.id, s.hostname, e.agent_version, s.last_seen 
        FROM servers s 
        LEFT JOIN server_extras e ON s.id=e.server_id 
        ORDER BY s.id
    '''))
    for r in res:
        print(f'Server {r[0]} ({r[1]}): ver={r[2]} | last_seen={r[3]}')
"
```

### Kriteria Kelulusan Verifikasi:
- 100% host klien aktif melaporkan versi SemVer baru yang sesuai.
- Kolom `last_seen` seluruh server klien aktif terbukti diperbarui dalam rentang waktu $\le 60$ detik terakhir.
- Tidak ada perintah pembaruan yang tersangkut (*stalled*) di status `executing`.
