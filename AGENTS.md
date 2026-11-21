# AGENTS.md — Pantau Server Operating Brief

Sumber kebenaran: [`DEVELOPMENT.md`](file:///home/bos/pantau-server/DEVELOPMENT.md) (Manifes Arsitektur) dan [`GEMINI.md`](file:///home/bos/pantau-server/GEMINI.md) (Aturan Teknis Permanen).
Berkas ini adalah **Operating Brief ringkas & baku** bagi seluruh asisten AI yang bekerja pada basis kode **Pantau Server** (`/home/bos/pantau-server`), mengadopsi standar rekayasa Rekanara Digital Labs.

---

## 1. Hakikat Sistem (What This Is)

**Pantau Server** adalah platform pusat kendali operasional NOC (*Network Operations Center Control Plane*) generasi baru untuk memantau performa, ketersediaan, dan keamanan armada server Linux multi-node mandiri secara *real-time* dengan akurasi fisik tingkat kernel (*kernel-grade precision*).

Tumpukan sistem:
- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, Pydantic, MySQL (`pantau_server_db`).
- **Frontend**: Vue 3.5 SPA, Vite 8, Tailwind CSS v4, Lucide Icons, xterm.js (Web Terminal Dock).
- **Klien Agen**: `agent/agent_pantau.py` — *zero external dependency* (pustaka standar Python murni).
- **Otomasi Rilis**: `tools/sop_release.py` — otomasi SemVer 7-berkas, uji sintaks, git/tag/GitHub Release.

---

## 2. Tata Letak Proyek (Layout)

```
server/                 # Backend FastAPI
  ├── config.py         # Pydantic Settings (DB_*, SERVER_*, APP_VERSION)
  ├── main.py           # Entry point FastAPI, mounting static & routers
  ├── models/           # SQLAlchemy ORM Models (server, problem, user, etc.)
  ├── schemas/          # Pydantic Schemas (validasi input & response envelope)
  ├── routers/          # HTTP & WebSocket endpoints (api_agent, servers, terminal, auth)
  ├── services/         # Domain business logic (telemetry_service, problem triaging)
  └── seed_admin.py     # Inisialisasi akun operator
frontend/               # Frontend Vue 3 SPA
  ├── src/
  │    ├── App.vue      # Root container, Global Terminal Dock, Workspace Modal
  │    ├── components/  # Komponen modular (<250 baris per file)
  │    │     ├── dashboard/   # Dasbor pasif makro
  │    │     ├── fleet/       # Tabel inventaris armada
  │    │     ├── workspace/   # Floating Workspace Modal & tab inspeksi host
  │    │     └── terminal/    # Global Multi-Tab xterm.js Dock
  │    └── i18n/        # Bilingual dictionary (EN default, ID selectable)
agent/                  # Klien telemetri node armada (agent_pantau.py)
tools/                  # Otomasi rilis (sop_release.py), test_terminal_dock.js, seed scripts
.agents/skills/         # Panduan per domain (sop-pantau, ponytail, moli-*)
```

---

## 3. Aturan Baku Mutlak (Hard Rules — Violations = Broken Protocol)

1. **Pemisahan Lapisan (Layering):**
   - `routers/`: Transport only. Validasi Pydantic, injeksi sesi DB, status HTTP. **Zero kueri rumit / logic telemetri**.
   - `services/`: Domain & business logic murni. Kalkulasi metrik, evaluasi alarm, triase insiden.
   - `models/`: Skema relasional InnoDB murni.
   - `frontend/components/`: Komponen kecil terfokus (<250 baris). Dilarang menyatukan ribuan baris template ke satu berkas monolitik.
2. **Batas Cakupan UI (Scope Boundary):**
   - **Dasbor Murni Pasif (`DashboardView.vue`):** Khusus pemantauan makro 24/7/365 (Banner KPI 3-kartu, tabel insiden pasif). **Dilarang keras menambah kolom atau tombol aksi/mutasi di dasbor.** Navigasi baris pasif via klik baris (`cursor-pointer`).
   - **Jendela Kontrol Taktis Mengambang (`ServerWorkspaceModal.vue`):** Seluruh investigasi mikro dan aksi kontrol (restart service, kill process, putus sesi, audit port, firewall) berada eksklusif di dalam modal mengambang `85vw x 85vh`.
3. **Web Terminal Dock Baku (xterm.js):**
   - Wajib menggunakan **Global Multi-Tab Terminal Dock** berbasis `xterm.js` + `xterm-addon-fit.js`.
   - Dilarang keras membuat terminal tiruan satu baris `<input>`.
   - Sesi terminal wajib *keep-alive* saat diminimalkan ke rak bawah, dan proses PTY wajib dibersihkan secara bersih (*kill*) saat WebSocket terputus untuk mencegah proses *zombie*.
4. **Higienitas Basis Data & Sesi SQLAlchemy:**
   - **DetachedInstanceError Prevention:** Dilarang mengakses atribut relasi lazy-loaded setelah sesi database (`db.close()` / yield dependency) ditutup. Selalu load data yang dibutuhkan secara *eager* (`joinedload`/`selectinload`) atau petakan ke Pydantic schema di dalam cakupan sesi aktif.
   - Multi-step writes wajib melalui transaksi atomik eksplisit (`db.commit()`, `db.rollback()`).
5. **Kejujuran Data Mutlak (Zero-Fake Data):**
   - Hanya simpan dan tampilkan data terukur fisik dari kernel Linux (`/proc`, `/sys`, socket, systemd). Dilarang memalsukan status atau mengarang metrik.
6. **Standar Ergonomi Tombol (4-Tier Standard):**
   - *Tier 1 (Ikon SVG Saja):* Aksi universal (minimize, close, sync/refresh, download).
   - *Tier 2 (Ikon + Label):* Tab navigasi & kontrol domain (`[ Performance ]`, `[ Services & Ports ]`).
   - *Tier 3 (Ikon Saja + Tooltip Informatif):* Aksi padat baris tabel demi *NOC Data Density*.
   - *Tier 4 (Ikon + Label + Tooltip Konsekuensi):* Aksi kritis sistemik (`Update OS`, `Reboot`, `Power Off`).
   - Dilarang keras menggunakan karakter emoji kartun bawaan OS. Gunakan SVG monokromatik.
7. **Paginasi Otomatis ($\le 10$ Baris Sembunyi):**
   - Jika baris data $\le 10$, bilah paginasi **wajib disembunyikan otomatis (`display: none !important`)**. Hanya tampil jika $> 10$ baris.
8. **Prinsip Ponytail (Anti-Bloat & Lazy Senior Dev Mode):**
   - Selesaikan masalah dengan **diff terkecil yang menuntaskan tugas secara utuh**.
   - Dilarang memperkenalkan abstraksi spekulatif, wrapper kosong, atau kode "untuk nanti".
   - Jika membuat simplifikasi teknis yang disengaja, beri anotasi:
     `# ponytail: <alasan simplifikasi>, <kapan harus di-upgrade>`
9. **Supremasi Konsep, Workflow & UX Aplikasi Lama (`~/rj45`):**
   - Konsep, alur kerja (*workflow*), dan UX dari aplikasi lama (`/home/bos/rj45`) adalah **konsep yang BENAR dan sudah matang**.
   - Hakikat repositori baru ini (`/home/bos/pantau-server`) murni adalah **penyempurnaan dan modernisasi dari sisi UI/Frontend** (mengganti frontend monolitik lama yang kacau dengan Vue 3 SPA bersih & rapi) **plus pembenahan/penguatan backend yang dibutuhkan**.
   - Dilarang keras mengarang alur kerja baru atau model interaksi asing. Setiap fitur wajib mencontoh alur kerja aplikasi lama di `~/rj45` sebagai sumber kebenaran fungsional dan visual.

---

## 4. Perintah Sehari-hari (Everyday Commands)

| Perintah | Lokasi Eksekusi | Tujuan |
|---|---|---|
| `source env/bin/activate && uvicorn main:app --app-dir server --host 0.0.0.0 --port 8401` | root | Menjalankan backend daemon FastAPI |
| `npm run dev` | `frontend/` | Menjalankan Vite dev server frontend |
| `npm run build` | `frontend/` | Kompilasi Vue 3 SPA ke aset produksi |
| `env/bin/python3 -m py_compile server/main.py server/config.py` | root | Uji sintaksis Python cepat |
| `node tools/test_terminal_dock.js` | root | Uji fungsionalitas xterm.js Terminal Dock |
| `tools/sop_release.py --patch --commit-msg "..." --title "..."` | root | Otomasi rilis SemVer 7-berkas & GitHub Release |

---

## 5. Protokol Verifikasi Mandiri (Wajib Sebelum Klaim Selesai)

Sebelum menyatakan tugas perbaikan bug atau fitur selesai:
1. **Verifikasi Sintaks Backend:**
   ```bash
   /home/bos/pantau-server/env/bin/python3 -m py_compile server/**/*.py
   ```
2. **Verifikasi Kompilasi Frontend:**
   ```bash
   npm run build --prefix /home/bos/pantau-server/frontend
   ```
3. **Verifikasi Lapangan Rilis (Jika Melakukan Rilis SemVer):**
   Wajib menjalankan kueri basis data untuk memastikan 100% armada aktif telah menerima pembaruan dan melapor pada versi baru:
   ```bash
   PYTHONPATH=/home/bos/pantau-server/server /home/bos/pantau-server/env/bin/python -c "
   from sqlalchemy import create_engine, text
   from config import settings
   engine = create_engine(settings.database_url)
   with engine.connect() as conn:
       res = conn.execute(text('SELECT s.id, s.hostname, e.agent_version, s.last_seen FROM servers s LEFT JOIN server_extras e ON s.id=e.server_id ORDER BY s.id'))
       for r in res:
           print(f'Server {r[0]} ({r[1]}): ver={r[2]} | last_seen={r[3]}')
   "
   ```
