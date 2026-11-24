#!/usr/bin/env python3
"""
Skrip Otomatisasi Alur Rilis SOP Pantau Server (Fast Automated SOP Release Pipeline)
Menangani kenaikan versi SemVer secara sinkron, kompilasi/validasi sintaksis backend & frontend,
serta commit Git, push ke main, tag, dan GitHub Release hanya dalam satu eksekusi cepat (15-30 detik).
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def run_cmd(cmd, check=True, cwd=ROOT_DIR):
    """Jalankan perintah shell dan cetak keluarannya."""
    print(f"[CMD] {cmd}")
    res = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=True)
    if res.stdout:
        print(res.stdout.strip())
    if res.returncode != 0:
        if res.stderr:
            print(f"[ERR] {res.stderr.strip()}", file=sys.stderr)
        if check:
            sys.exit(res.returncode)
    return res


def get_current_version() -> str:
    """Membaca APP_VERSION terkini dari server/config.py."""
    config_path = ROOT_DIR / "server" / "config.py"
    content = config_path.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION:\s*str\s*=\s*["\']([^"\']+)["\']', content)
    if not m:
        raise ValueError("Tidak dapat menemukan APP_VERSION di server/config.py")
    return m.group(1)


def bump_semver_patch(ver: str) -> str:
    """Menaikkan patch version X.Y.Z -> X.Y.(Z+1)."""
    parts = ver.strip().split(".")
    if len(parts) == 3 and parts[2].isdigit():
        return f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    raise ValueError(f"Format versi SemVer tidak valid: {ver}")


def update_version_files(new_ver: str, changelog_block: str = None) -> list:
    """Memperbarui versi pada berkas-berkas konfigurasi dan dokumentasi secara sinkron."""
    modified_files = []

    # 1. server/config.py
    f1 = ROOT_DIR / "server" / "config.py"
    if f1.exists():
        c1 = f1.read_text(encoding="utf-8")
        c1_new = re.sub(
            r'(APP_VERSION:\s*str\s*=\s*["\'])[^"\']+(["\'])',
            rf'\g<1>{new_ver}\g<2>',
            c1,
            count=1
        )
        if c1 != c1_new:
            f1.write_text(c1_new, encoding="utf-8")
            modified_files.append(str(f1.relative_to(ROOT_DIR)))

    # 2. frontend/package.json
    f2 = ROOT_DIR / "frontend" / "package.json"
    if f2.exists():
        c2 = f2.read_text(encoding="utf-8")
        c2_new = re.sub(
            r'("version":\s*["\'])[^"\']+(["\'])',
            rf'\g<1>{new_ver}\g<2>',
            c2,
            count=1
        )
        if c2 != c2_new:
            f2.write_text(c2_new, encoding="utf-8")
            modified_files.append(str(f2.relative_to(ROOT_DIR)))

    # 3. README.md
    f3 = ROOT_DIR / "README.md"
    if f3.exists():
        c3 = f3.read_text(encoding="utf-8")
        c3_new = re.sub(
            r'(version-v)[0-9]+\.[0-9]+\.[0-9]+(-blue\.svg)',
            rf'\g<1>{new_ver}\g<2>',
            c3,
            count=1
        )
        c3_new = re.sub(
            r'(\*\*Pantau Server\*\*\s*\(Versi\s*v?)[0-9]+\.[0-9]+\.[0-9]+(\))',
            rf'\g<1>{new_ver}\g<2>',
            c3_new,
            count=1
        )
        if c3 != c3_new:
            f3.write_text(c3_new, encoding="utf-8")
            modified_files.append(str(f3.relative_to(ROOT_DIR)))

    # 4. DEVELOPMENT.md
    f4 = ROOT_DIR / "DEVELOPMENT.md"
    if f4.exists() and changelog_block:
        c4 = f4.read_text(encoding="utf-8")
        marker = "## Catatan Perubahan (Changelog)"
        if marker in c4:
            entry = f"{marker}\n\n### Versi v{new_ver}\n\n{changelog_block.strip()}\n"
            c4_new = c4.replace(marker, entry, 1)
            if c4 != c4_new:
                f4.write_text(c4_new, encoding="utf-8")
                modified_files.append(str(f4.relative_to(ROOT_DIR)))

    # 5. frontend/src/components/Navbar.vue & LoginModal.vue
    for subpath in ("frontend/src/components/Navbar.vue", "frontend/src/components/LoginModal.vue"):
        fp = ROOT_DIR / subpath
        if fp.exists():
            c = fp.read_text(encoding="utf-8")
            c_new = re.sub(
                r'v[0-9]+\.[0-9]+\.[0-9]+',
                f'v{new_ver}',
                c,
                count=1
            )
            if c != c_new:
                fp.write_text(c_new, encoding="utf-8")
                modified_files.append(str(fp.relative_to(ROOT_DIR)))

    return modified_files


def main():
    parser = argparse.ArgumentParser(
        description="Otomatisasi Penuh SOP Rilis Pantau Server (SemVer, build frontend, compile python, git, tag, release)"
    )
    parser.add_argument("version", nargs="?", help="Versi baru (contoh: 0.1.1). Kosongkan untuk patch bump otomatis.")
    parser.add_argument("--commit-msg", "-m", help="Pesan commit Git baku (contoh: 'feat(scope): deskripsi baku (vX.Y.Z)')")
    parser.add_argument("--title", "-t", help="Judul rilis resmi GitHub (contoh: 'vX.Y.Z - Judul Baku')")
    parser.add_argument("--notes", "-n", help="Catatan ringkas untuk GitHub release body")
    parser.add_argument("--changelog", "-c", help="Teks isi changelog untuk disisipkan ke DEVELOPMENT.md")
    parser.add_argument("--extra-files", nargs="*", default=[], help="Berkas tambahan untuk di-stage git add")
    parser.add_argument("--skip-git", action="store_true", help="Lewati alur Git push, tag, dan gh release")
    parser.add_argument("--dry-run", action="store_true", help="Hanya cetak rencana aksi tanpa mengeksekusi")

    args = parser.parse_args()

    cur_ver = get_current_version()
    print(f"[*] Versi saat ini di server/config.py: {cur_ver}")

    if args.version:
        new_ver = args.version.lstrip("v")
    else:
        new_ver = bump_semver_patch(cur_ver)

    print(f"[*] Versi target rilis: {new_ver}")

    if args.dry_run:
        print("[*] Mode dry-run selesai. Tidak ada berkas yang diubah.")
        return

    # 1. Update Versi Berkas
    print("\n[1/4] Memperbarui versi pada berkas-berkas proyek...")
    mod_files = update_version_files(new_ver, changelog_block=args.changelog or args.notes)
    for mf in mod_files:
        print(f"  -> Diperbarui: {mf}")

    # 2. Uji Kompilasi & Sintaksis & Quality Gate
    print("\n[2/4] Menjalankan uji anti-hardcode, kompilasi Python backend dan build Vue frontend...")
    py_exec = ROOT_DIR / "env" / "bin" / "python3"
    if not py_exec.exists():
        py_exec = "python3"
    else:
        py_exec = str(py_exec)

    # Automated Anti-Hardcode Quality Gate
    run_cmd(f"{py_exec} tools/lint_i18n.py", cwd=ROOT_DIR)
    run_cmd(f"{py_exec} -m py_compile server/config.py server/main.py")
    run_cmd("npm run build", cwd=ROOT_DIR / "frontend")
    print("  -> Seluruh sintaks, anti-hardcode gate, dan build produksi lulus verifikasi 100%.")

    if args.skip_git:
        print("\n[*] Flag --skip-git aktif: Proses selesai tanpa Git commit/push/release.")
        return

    # 3. Git Commit & Push
    print("\n[3/4] Menjalankan alur Git staging, commit, dan push main...")
    commit_msg = args.commit_msg or f"chore(release): rilis versi v{new_ver}"
    all_files_to_add = set(mod_files + (args.extra_files or []))
    add_str = " ".join(f"'{f}'" for f in all_files_to_add) if all_files_to_add else "."
    run_cmd(f"git add {add_str}")
    run_cmd(f'git commit -m "{commit_msg}"')
    run_cmd("git push origin main")

    # 4. Git Tag & GitHub Release
    print("\n[4/4] Membuat git tag dan mempublikasikan GitHub Release...")
    tag_name = f"v{new_ver}"
    release_title = args.title or f"{tag_name} - Pembaruan Otomatis Pantau Server"
    release_notes = args.notes or f"Rilis otomatis versi {tag_name}."

    run_cmd(f'git tag -a {tag_name} -m "Release {tag_name}: {release_title}"')
    run_cmd(f"git push origin {tag_name}")
    run_cmd(f'gh release create {tag_name} --title "{release_title}" --notes "{release_notes}"')

    print(f"\n[SUCCESS] Rilis {tag_name} berhasil diselesaikan dan dipublikasikan secara penuh!\n")


if __name__ == "__main__":
    main()
