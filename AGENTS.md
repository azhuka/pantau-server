# AGENTS.md — Pantau Server Operating Brief

Sumber kebenaran: [`DEVELOPMENT.md`](file:///home/bos/pantau-server/DEVELOPMENT.md) (Manifes Arsitektur) dan [`GEMINI.md`](file:///home/bos/pantau-server/GEMINI.md) (Aturan Teknis Permanen).
Berkas ini adalah **Operating Brief ringkas & baku** bagi seluruh asisten AI yang bekerja pada basis kode **Pantau Server** (`/home/bos/pantau-server`), mengadopsi standar rekayasa Rekanara Digital Labs.

---

## 1. Hakikat Sistem (What This Is)

**Pantau Server** adalah platform pusat kendali operasional NOC (*Network Operations Center Control Plane*) generasi baru untuk memantau performa, ketersediaan, dan keamanan aset Linux multi-node mandiri secara *real-time* dengan akurasi fisik tingkat kernel (*kernel-grade precision*).

Tumpukan sistem:
- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, Pydantic, MySQL (`pantau_db`).
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
  │    │     ├── assets/      # Tabel inventaris aset
  │    │     ├── workspace/   # Floating Workspace Modal & tab inspeksi host
  │    │     └── terminal/    # Global Multi-Tab xterm.js Dock
  │    └── i18n/        # Bilingual dictionary (EN default, ID selectable)
agent/                  # Klien telemetri node aset (agent_pantau.py)
tools/                  # Otomasi rilis (sop_release.py), test_terminal_dock.js, seed scripts
.agents/skills/         # Panduan per domain (sop-pantau, ponytail, moli-*, antislop-*, security-audit)
```

---

## 3. Aturan Baku Mutlak (Hard Rules — Violations = Broken Protocol)

1. **Pemisahan Lapisan (Layering):**
   - `routers/`: Transport only. Validasi Pydantic, injeksi sesi DB, status HTTP. **Zero kueri rumit / logic telemetri**.
   - `services/`: Domain & business logic murni. Kalkulasi metrik, evaluasi alarm, triase insiden.
   - `models/`: Skema relasional InnoDB murni.
   - `frontend/components/`: Komponen kecil terfokus (<250 baris). Dilarang menyatukan ribuan baris template ke satu berkas monolitik.
2. **Batas Cakupan UI (Scope Boundary):**
   - **Dasbor Murni Pasif & Zero-Hidden (`DashboardView.vue`):** Khusus pemantauan makro 24/7/365 (Banner KPI 3-kartu, tabel insiden pasif, tabel armada utuh). **Dilarang keras menambah kolom atau tombol aksi/mutasi di dasbor.** Navigasi baris pasif via klik baris (`cursor-pointer`). **Paginasi mutlak dilarang di dasbor**: seluruh node wajib tampil langsung tanpa disembunyikan di balik halaman berikutnya demi kecepatan baca situasi (*zero-hidden situational awareness*).
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
6. **Standar Ergonomi Tombol & Tipologi 4-Tier (4-Tier Button Ergonomics Standard):**
   - *Tipologi 4-Tier Baku:*
     - *Tier 1 (Ikon SVG Saja):* Aksi universal (minimize, maximize/restore, close, clear screen, sync/refresh, chevrons nav, download). Wajib ikon SVG vektor tipis monokromatik tanpa label teks panjang yang memboroskan ruang.
     - *Tier 2 (Ikon + Label):* Tab navigasi & kontrol domain (`[ Maintenance Mode ]`, `[ Performance ]`, `[ Services & Ports ]`). Dilarang keras menggunakan kata fiktif/dramatis seperti *Investigate* atau emoji petir.
     - *Tier 3 (Ikon Saja + Tooltip Informatif):* Aksi padat baris tabel demi *NOC Data Density*. Wajib ukuran fisik baku **26x26px** (`width: 26px; height: 26px; min-width: 26px`), `border-radius: 4px`, ukuran ikon SVG **13–14px**, dengan atribut `title="..."` presisi yang menyebutkan target objek secara akurat.
     - *Tier 4 (Ikon + Label + Tooltip Konsekuensi):* Aksi kritis sistemik (`Update OS`, `Upgrade OS`, `Reboot`, `Power Off`). Wajib memiliki label teks tegas dan tooltip informatif yang merinci konsekuensi aksi.
   - *Keseragaman Tingkat Tabel (Bukan Campur Aduk Per Baris):*
     - Tabel dengan > 2 jenis aksi: 100% baris secara seragam wajib menggunakan menu dropdown **`Actions ▾`** (`<details class="noc-act-dropdown">`, tinggi 24px, min-width 58px, `z-index: 9999` saat terbuka). Dilarang keras mencampuradukkan tombol inline dan dropdown dalam satu tabel yang sama.
     - Tabel dengan 1–2 jenis aksi: Seluruh baris menampilkan tombol aksi langsung secara sejajar (*inline*) ukuran baku 26x26px.
     - Peran Viewer (Read-Only): Selalu menggunakan 1 tombol ikon bersih `[ 👁 ]` (26x26px) tanpa menu mutasi.
   - *Aturan Tombol Non-Aktif (*Disabled States*):* Tombol yang tidak dapat dieksekusi (misal layanan sudah aktif/running, host terproteksi Proxmox HA, daemon agen dilindungi sistem) wajib memiliki `opacity: 0.38 !important`, `cursor: not-allowed !important`, event klik diblokir (`pointer-events: none` atau `event.stopPropagation()`), dan **wajib memiliki atribut `title="..."` yang menjelaskan alasan spesifik** mengapa tombol tersebut non-aktif.
   - *Larangan Tombol Melayang (*Floating Overlays*):* Dilarang menempatkan tombol mengambang di atas teks konsol/log/tabel yang menghalangi keterbacaan data; kontrol wajib diletakkan pada toolbar atas atau statusbar footer terstruktur.
   - *Keseragaman Kontrol Jendela (*Window Chrome*):* Kontrol bilah judul jendela konsol/modal (Pop-out, Clear Screen, Full Window, Fullscreen, Close) wajib seragam berupa tombol ikon SVG tanpa label teks horizontal memanjang, dengan tooltip informatif sebagai penjelas.
   - *Larangan Mutlak Emoji Kartun (Zero-Emoji Mandate):* Seluruh tombol dan antarmuka wajib menggunakan vektor SVG inline monokromatik/semantik (stroke 1.5–2px, adaptif terhadap warna tema NOC). Dilarang keras menggunakan karakter emoji bergambar bawaan OS.
7. **Paginasi Otomatis ($\le 10$ Baris Sembunyi pada Tabel Sekunder):**
   - Pada tabel sekunder (`AssetTableView`, `AuditView`, modal keparahan): jika baris data $\le 10$, bilah paginasi **wajib disembunyikan otomatis (`display: none !important`)**. Hanya tampil jika $> 10$ baris. (Paginasi mutlak tidak berlaku di halaman dasbor).
8. **Prinsip Ponytail (Anti-Bloat & Lazy Senior Dev Mode):**
   - Selesaikan masalah dengan **diff terkecil yang menuntaskan tugas secara utuh**.
   - Dilarang memperkenalkan abstraksi spekulatif, wrapper kosong, atau kode "untuk nanti".
   - Jika membuat simplifikasi teknis yang disengaja, beri anotasi:
     `# ponytail: <alasan simplifikasi>, <kapan harus di-upgrade>`
9. **Supremasi Blueprint Matang & Anti-Solusi Spekulatif:**
   - Blueprint sistem, alur kerja (*workflow*), dan UX taktis selalu mengacu pada fondasi perancangan asli yang sudah teruji matang.
   - Hakikat repositori ini (`/home/bos/pantau-server`) murni adalah **penyempurnaan dan modernisasi dari sisi UI/Frontend** (Vue 3 SPA, komponen terisolasi `<250` baris, Tailwind CSS v4, xterm.js) **plus penguatan backend yang diperlukan**.
   - Dilarang keras mengarang alur kerja baru, model interaksi asing, atau opsi spekulatif (seperti dual-reporting agent tiruan atau menjalankan proses agen sementara di terminal).
   - Basis data operasional resmi adalah **`pantau_db`**, di mana seluruh 10 aset server riil melapor aktif ke agen systemd resmi.
10. **Definisi Baku & Taksonomi Insiden/Akun (Glosarium Resmi):**
   - `pantau-server`: Nama resmi aplikasi platform pusat kendali operasional NOC.
   - `pantau-agent`: Nama resmi agen klien telemetri di node Linux.
   - `aset` (`assets`): Istilah tunggal resmi untuk seluruh entitas yang dipantau (server, router, aplikasi klien, gateway, dll.). Dilarang keras menggunakan istilah "fleet" atau "armada".
   - `insiden`: Masalah/gangguan/anomali/kejadian/peristiwa pada aset.
   - `insiden aktif` (*bukan insiden terbuka*): Insiden yang sedang terjadi dan masih aktif secara fisik.
   - *Severity 4-Tingkat:* `info` (biru, non-ancaman, info update package), `warning` (kuning, potensi ancaman/gangguan, layanan utama tetap jalan), `critical` (oranye pekat, layanan utama terganggu/mati, SSH ilegal), `danger` (merah, kelumpuhan sistem utama, host offline/down, disk read-only, kernel panic).
   - *Hierarki Pengguna:* `master-admin` (root absolut), `operator utama` (dibuat master-admin, hak kelola penuh harian, tak bisa hapus master-admin), `operator pembantu` (dibuat operator utama, izin granular terbatas), `tamu`/`guest` (peninjau murni / read-only).
   - *Prinsip Zero-Knowledge Master Admin:* Akun `master-admin` disembunyikan total dari operator/viewer (counter card disembunyikan, tabel disaring, respons API netral 404 Not Found, log audit disamarkan sebagai "Sistem").
11. **Kebijakan Dokumentasi & Larangan Mutlak Narasi Komparatif:**
   - **`README.md`**: Dokumen publik khusus bagi pengguna akhir (*end-user* / sysadmin) untuk instalasi, konfigurasi, dan panduan operasional.
   - **`DEVELOPMENT.md`**: Buku putih arsitektur, catatan teknis mendalam, dan riwayat changelog per rilis bagi operator dan asisten AI agar menjadi referensi masa depan.
   - **Larangan Mutlak Mention Aplikasi Lama:** Berkas `README.md` dan `DEVELOPMENT.md` **DILARANG KERAS** menyebut, merujuk, atau membandingkan dengan sistem/aplikasi lama (`~/rj45`, "aplikasi lama", dll.). Seluruh narasi wajib disajikan seolah-olah sistem ini murni dirancang dan dibangun dari 0 (*clean slate*).
12. **Standar Bahasa Antarmuka Eksklusif Bahasa Inggris (Strict English-Only Interface — For Now):**
   - Seluruh antarmuka web (tab navigasi, header kolom tabel, kartu KPI, tombol kontrol, status badge, teks dialog, modal diagnosa, pesan audit, dan tooltip) **WAJIB murni dan eksklusif menggunakan Bahasa Inggris (`en`)** baku NOC/sysadmin (`Actions`, `Triggered At`, `Incident Description`, `Severity`, `Duration`, `Solution`, `Actions ▾`, `Mark Handled`, `HANDLED`, `Ignore Incident`, `IGNORED`, `Cancel Ignore`, `Server Details`, dll.).
   - Komponen sakelar bahasa atau penerjemahan lokal ditangguhkan untuk sementara waktu guna menjaga keseragaman arsitektur teks dan efisiensi context window.
13. **Standar Leksikon & Terminologi Baku Komputasi & Jaringan (Standard Computing & Networking Lexicon):**
   - Seluruh penamaan variabel, modul, kolom tabel, tombol, metrik, pesan audit, status badge, dan dokumentasi **WAJIB menggunakan bahasa, kata, kalimat, dan terminologi yang umum, baku, dan telah mapan dalam dunia network, server engineering, Linux sysadmin, dan NOC**.
   - Dilarang keras mengarang istilah baru (*invented/colloquial terms*), menggunakan istilah dramatis/hiperbolis (*"investigate"*, *"magic"*, *"unlock"*), atau sinonim asing yang memicu salah paham dan perbedaan persepsi antar operator.
   - Rujukan terminologi baku:
     - Entitas yang dipantau: `Assets` / `Hosts` / `Nodes` (Dilarang menggunakan *fleet* atau *armada* di teks antarmuka).
     - Insiden & Gangguan: `Incidents`, `Active Incidents`, `Resolved Incidents`, `Incident Description`, `Severity`, `Triggered At`, `Duration`, `Solution`, `MTTR (Mean Time to Recovery)`.
     - Kontrol & Mitigasi: `Actions`, `Actions ▾`, `Server Details`, `Mark Handled`, `HANDLED BY`, `Ignore Incident`, `IGNORED UNTIL`, `Cancel Ignore`.
     - Infrastruktur & Subsistem: `Services`, `Units`, `Processes`, `PID`, `Listening Ports`, `Sockets`, `Firewall Rules`, `Cron Tasks`, `Storage / Mount Points`.
     - Metrik & Telemetri: `Telemetry`, `Heartbeat`, `Latency`, `Probe`, `Load Average`, `CPU Usage`, `Memory / RAM`, `Disk Usage`, `Uptime`.
14. **Mandat Dokumentasi Otonom & Permanen di `DEVELOPMENT.md` (Autonomous & Mandatory Documentation in DEVELOPMENT.md):**
   - Berkas `DEVELOPMENT.md` adalah *Single Source of Truth* arsitektur, rujukan rekayasa utama, dan basis pengetahuan permanen sistem Pantau Server.
   - Seluruh pengetahuan teknis baru, aturan sistem, standardisasi alur kerja (*workflows*), formulasi ergonomi tombol/tabel, dan penerapan metode *best practice* **WAJIB dicatat dan diperbarui ke dalam `DEVELOPMENT.md` secara otonom pada setiap iterasi/rilis, bahkan tanpa harus diperintah secara eksplisit oleh operator**.
   - Setiap keputusan arsitektur atau konvensi baru wajib dituangkan dalam bab yang terstruktur, rapi, dan komprehensif agar selalu menjadi kompas bagi seluruh pengembang dan agen AI di masa depan.

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
   Wajib menjalankan kueri basis data untuk memastikan 100% aset aktif telah menerima pembaruan dan melapor pada versi baru:
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

---

## 6. Integrasi Skill anti-slop (Filter Kebersihan UI, Copy & Kode)

Koleksi skill `anti-slop` dipasang lokal di `.agents/skills/antislop*` sebagai filter mutu pembantu:
- **Hierarki Otoritas:** `GEMINI.md` dan `AGENTS.md` adalah hukum tertinggi. `anti-slop` berposisi sebagai filter pembantu (*auxiliary filter*) untuk menolak artefak generik buatan AI. Jika terjadi perbedaan penafsiran, aturan Pantau Server selalu menang.
- **Mode Eksekusi Otomatis:** Mode terkunci pada `during` (aktif otomatis tanpa menanyakan opsi 1/2 kepada operator).
- **Pilar Penerapan di Pantau Server:**
  - **UI (`antislop-ui`):** Tolak gradien biru-ungu klise, larang rounded pill berlebihan pada tabel/tombol kontrol, tolak glassmorphism/glow mengambang yang merusak *NOC Data Density*.
  - **Kode (`antislop-code`):** Tolak komentar narasi sepele (`// Step 1: ...`), tolak JSDoc pengulang signature, hapus emoji dekoratif di kode, pertahankan komentar esensial (aturan kernel, keamanan, arsitektur).
  - **Teks (`antislop-copywriting`):** Tolak istilah hiperbolis/hype palsu (*"Unlock next-gen..."*), gunakan bahasa baku NOC ringkas.
  - **Aksesibilitas & Keterbacaan (`antislop-human`):** Penegakan kontras tajam dark/light mode dan tap target minimal 44px.

---

## 7. Integrasi Skill security-audit (Audit Keamanan Multi-Tahap Cloudflare)

Skill `security-audit` dipasang lokal di `.agents/skills/security-audit/` untuk audit celah keamanan, review API, dan penetration testing berbasis bukti:
- **Hierarki Otoritas:** `GEMINI.md` dan `AGENTS.md` tetap menjadi hukum tertinggi.
- **Keselamatan Eksekusi (Zero-Production Probing):** Dilarang keras menembak IP publik node aset, melakukan DoS, atau mengganggu daemon aktif (`pantau-server.service`, `agent_pantau.service`). Audit murni melalui inspeksi kode sumber lokal atau sandbox tertutup (`127.0.0.1`).
- **Verifikasi Adversarial:** Setiap kandidat temuan wajib diverifikasi oleh verifikator independen yang mencoba menyangkal hipotesis (*refute*) untuk membasmi *false positives*.
- **Vonis 3-Tingkat Baku:** Hasil audit diklasifikasikan ke `confirmed` (terbukti dengan trace kode dan dampak nyata), `needs_validation` (butuh validasi runtime khusus tanpa mengarang tingkat keparahan), atau `rejected` (terbantahkan).
- **Mode Operasi:** Secara *default* berstatus *Guidance Mode* (hanya menjawab konsultasi atau review terarah) dan hanya menjalankan alur 6 fase penuh jika ada permintaan audit eksplisit (*"security audit"*, *"pen-test"*).

---

## 8. Mandat Standar Rekayasa Hakiki (Zero-Hack, Zero-Workaround & Pure Architecture)

- **Larangan Mutlak Hardcoding & Workaround:** Dilarang keras menggunakan jalan pintas praktis (*lazy shortcuts*), akal-akalan, tambal sulam, regex substring hack yang rapuh di UI, data dummy, atau hardcoding nilai statis pada seluruh lapisan (backend FastAPI, routers, services, frontend Vue, script, agent).
- **Penanganan Akar Masalah (*Root Cause First*):** Perbaikan wajib menyentuh akar masalah. Jika data kurang di antarmuka, perbaiki skema & domain servis di backend, alirkan melalui Pydantic response envelope resmi, lalu sajikan di Vue secara bersih dan terstruktur.
- **Standar Rekayasa Tinggi:** Mengharuskan data fisik terukur tingkat kernel Linux (`/proc`, `/sys`, socket, systemd), konkurensi InnoDB murni, pemisahan lapisan yang disiplin, dan verifikasi nyata berbasis bukti.



