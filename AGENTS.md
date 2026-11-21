# Agent Guidelines: Pantau Server

Berkas ini memandu seluruh asisten AI yang bekerja pada proyek **Pantau Server** (`/home/bos/pantau-server`).

## 1. Domain Docs (Single Source of Truth)

Seluruh definisi istilah domain, arsitektur sistem, aturan antarmuka visual, dan batas kewenangan diatur secara terpusat pada:
- [`CONTEXT.md`](file:///home/bos/pantau-server/CONTEXT.md): Kamus domain tunggal (*Ubiquitous Language*), prinsip rekayasa sistemik, spesifikasi baku UI/UX, dan protokol alur kerja.
- [`GEMINI.md`](file:///home/bos/pantau-server/GEMINI.md): Aturan teknis pelengkap dan ceklis sistem pra-lapor.
- [`MASTER_PLAN.md`](file:///home/bos/pantau-server/MASTER_PLAN.md): Rencana arsitektur induk Clean Architecture & FastAPI.
- [`FRONTEND_MASTER_PLAN.md`](file:///home/bos/pantau-server/FRONTEND_MASTER_PLAN.md): Standar visual dan interaksi Tactical Cyber Command Room.

## 2. Standar Operasional Prosedur (SOP) Rilis

Seluruh alur peningkatan versi SemVer, kompilasi sintaksis, verifikasi lapangan 100% armada, dan sinkronisasi wajib merujuk pada:
- Panduan skill: [`SKILL.md`](file:///home/bos/pantau-server/.agents/skills/sop-pantau/SKILL.md)
- Konstitusi Desain: [`HAKIKAT_DAN_ARAH_PENGEMBANGAN.md`](file:///home/bos/pantau-server/HAKIKAT_DAN_ARAH_PENGEMBANGAN.md)

## 3. Disiplin Rekayasa Mutlak

1. **Proteksi Dasbor (Murni Pasif)**: Dasbor adalah area pemantauan makro & triase insiden pasif. Dilarang menambahkan tombol aksi aktif atau mutasi di dasbor.
2. **Jendela Taktis Mengambang (Workspace Controller)**: Seluruh kontrol aktif dan investigasi mendalam (layanan, proses, port, firewall, cron, user/SSH) berada eksklusif di modal `ServerWorkspaceModal.vue`.
3. **Paginasi Universal**: $\le 10$ baris disembunyikan otomatis (`display: none !important`), $> 10$ baris ditampilkan.
4. **Standarisasi Kolom & Tindakan**: Header kolom kontrol bernama "Actions" / "Tindakan" (kapitalisasi diawali huruf besar). Dropdown `Aksi ▾` jika $> 2$ opsi aksi; tombol inline sejajar jika $\le 2$ opsi aksi.
5. **Kejujuran Data (Zero-Fake Data)**: Hanya simpan dan tampilkan data terukur fisik dari kernel. Dilarang mengarang atribusi atau memalsukan status.
6. **Keterbacaan Tipografi 100% Zoom**: Base font sans-serif terbaca tajam pada skala 100%, dilarang menggunakan font mikroskopis (<12px). Monospace dikhususkan untuk telemetri angka, IP, port, dan kode.
7. **Bahasa Default Bahasa Inggris (dengan i18n Reaktif)**: Default antarmuka menggunakan Bahasa Inggris baku NOC/sysadmin dengan toggle instan ke Bahasa Indonesia. Dilarang men-hardcode string lokal di template komponen.
8. **Anti-Jalan Praktis (Anti-Shortcut Mandate)**: Dilarang keras mengambil atau mengusulkan jalan pintas kompromis (seperti SQLite untuk sistem NOC). Selalu gunakan arsitektur standar produksi sejati (MySQL InnoDB, konkurensi tinggi, integritas fisik).
9. **Larangan Mutlak Nomenklatur "v2"**: Aplikasi ini bernama **Pantau Server** dengan baseline **`v0.1.0`**. DILARANG KERAS melabeli atau menamai database/variabel/branch dengan istilah "v2".
10. **Eksekusi Instan Mandat `/learn`**: Perintah `/learn` dari operator adalah instruksi mutlak; langsung catat dan terapkan ke berkas aturan tanpa menunggu konfirmasi atau persetujuan ulang.
11. **Kemurnian Arsitektur & Isolasi Data Bersih**: Seluruh alur kerja (*workflow*), kartu dasbor, dan jendela kerja mengambang dirancang murni berbasis spesifikasi domain; dilarang keras mengimpor skema tidak konsisten atau data warisan kotor.
12. **Pencatatan Kesalahan Wajib Tanpa Pengulangan (CDiP)**: Seluruh kesalahan dan koreksi operator wajib dicatat sebagai pengingat di `tasks/lessons.md` agar pantang diulang.
13. **Standar Ergonomi Tombol 4-Tier**: Penggunaan tombol wajib mematuhi 4 kategori ergonomi: Tier 1 (Ikon saja untuk aksi universal seperti minimize/maximize/close/refresh), Tier 2 (Ikon + Label untuk navigasi fungsional domain), Tier 3 (Ikon saja + Tooltip informatif untuk aksi objek spesifik di baris padat), dan Tier 4 (Ikon + Label + Tooltip informatif untuk kontrol berdampak kritis/sistemik).
