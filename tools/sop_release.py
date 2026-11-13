#!/usr/bin/env python3
"""
Skrip Otomatisasi Alur Rilis SOP Pantau Server (Fast Automated SOP Release Pipeline)
Menangani kenaikan versi SemVer secara sinkron pada 7 berkas, kompilasi/validasi sintaksis,
penyebaran agen lokal, restart systemd, serta commit Git, push, tag, dan GitHub Release
hanya dalam satu eksekusi cepat (15-30 detik).
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


def update_seven_files(new_ver: str, changelog_block: str = None) -> list:
    """Memperbarui 7 berkas proyek secara sinkron."""
    modified_files = []

    # 1. server/config.py
    f1 = ROOT_DIR / "server" / "config.py"
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

    # 2. server/templates/base.html
    f2 = ROOT_DIR / "server" / "templates" / "base.html"
    c2 = f2.read_text(encoding="utf-8")
    c2_new = re.sub(
        r'(pantau-noc\.css\?v=\{\{\s*app_version\s+or\s+["\'])[^"\']+(["\']\s*\}\})',
        rf'\g<1>{new_ver}\g<2>',
        c2
    )
    c2_new = re.sub(
        r'(<div class="sb-footer-ver">v\{\{\s*app_version\s+or\s+["\'])[^"\']+(["\']\s*\}\}</div>)',
        rf'\g<1>{new_ver}\g<2>',
        c2_new
    )
    if c2 != c2_new:
        f2.write_text(c2_new, encoding="utf-8")
        modified_files.append(str(f2.relative_to(ROOT_DIR)))

    # 3. package/opt/pantau/agent/agent_pantau.py
    f3 = ROOT_DIR / "package" / "opt" / "pantau" / "agent" / "agent_pantau.py"
    c3 = f3.read_text(encoding="utf-8")
    c3_new = re.sub(
        r'(AGENT_VERSION\s*=\s*["\'])[^"\']+(["\'])',
        rf'\g<1>{new_ver}\g<2>',
        c3,
        count=1
    )
    if c3 != c3_new:
        f3.write_text(c3_new, encoding="utf-8")
        modified_files.append(str(f3.relative_to(ROOT_DIR)))

    # 4. agent/agent_pantau.py (sinkron identik)
    f4 = ROOT_DIR / "agent" / "agent_pantau.py"
    c4 = f4.read_text(encoding="utf-8")
    c4_new = re.sub(
        r'(AGENT_VERSION\s*=\s*["\'])[^"\']+(["\'])',
        rf'\g<1>{new_ver}\g<2>',
        c4,
        count=1
    )
    if c4 != c4_new:
        f4.write_text(c4_new, encoding="utf-8")
        modified_files.append(str(f4.relative_to(ROOT_DIR)))

    # 5. package/install.sh
    f5 = ROOT_DIR / "package" / "install.sh"
    c5 = f5.read_text(encoding="utf-8")
    c5_new = re.sub(
        r'(AgentPantau-Installer/)[0-9]+\.[0-9]+\.[0-9]+',
        rf'\g<1>{new_ver}',
        c5
    )
    c5_new = re.sub(
        r"(base\['_meta_agent_version'\]\s*=\s*[\"'])[^\"']+([\"'])",
        rf"\g<1>{new_ver}\g<2>",
        c5_new
    )
    if c5 != c5_new:
        f5.write_text(c5_new, encoding="utf-8")
        modified_files.append(str(f5.relative_to(ROOT_DIR)))

    # 6. README.md
    f6 = ROOT_DIR / "README.md"
    c6 = f6.read_text(encoding="utf-8")
    c6_new = re.sub(
        r'(\*\*Pantau-Server\*\*\s*\(Versi\s*)[0-9]+\.[0-9]+\.[0-9]+(\))',
        rf'\g<1>{new_ver}\g<2>',
        c6,
        count=1
    )
    if c6 != c6_new:
        f6.write_text(c6_new, encoding="utf-8")
        modified_files.append(str(f6.relative_to(ROOT_DIR)))

    # 7. DEVELOPMENT.md
    f7 = ROOT_DIR / "DEVELOPMENT.md"
    c7 = f7.read_text(encoding="utf-8")
    if changelog_block:
        marker = "# Bagian II: Catatan Riwayat Perubahan Versi (Changelog)"
        if marker in c7:
            entry = f"{marker}\n\n## Versi {new_ver}\n\n{changelog_block.strip()}\n"
            c7_new = c7.replace(marker, entry, 1)
            if c7 != c7_new:
                f7.write_text(c7_new, encoding="utf-8")
                modified_files.append(str(f7.relative_to(ROOT_DIR)))

    return modified_files


def main():
    parser = argparse.ArgumentParser(
        description="Otomatisasi Penuh SOP Rilis Pantau Server (SemVer 7 berkas, build, restart, git, tag, release)"
    )
    parser.add_argument("version", nargs="?", help="Versi baru (contoh: 4.8.204). Kosongkan untuk patch bump otomatis.")
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

    # 1. Update 7 Berkas SemVer
    print("\n[1/5] Memperbarui versi pada 7 berkas secara serempak...")
    mod_files = update_seven_files(new_ver, changelog_block=args.changelog or args.notes)
    for mf in mod_files:
        print(f"  -> Diperbarui: {mf}")

    # 2. Uji Kompilasi & Sintaksis
    print("\n[2/5] Menjalankan uji kompilasi Python, shell, dan template Jinja...")
    py_exec = ROOT_DIR / "env" / "bin" / "python3"
    if not py_exec.exists():
        py_exec = "python3"
    else:
        py_exec = str(py_exec)

    run_cmd(f"{py_exec} -m py_compile server/config.py agent/agent_pantau.py package/opt/pantau/agent/agent_pantau.py")
    run_cmd("bash -n package/install.sh")
    jinja_check = f"""{py_exec} -c "
import jinja2
env = jinja2.Environment(loader=jinja2.FileSystemLoader('{ROOT_DIR}/server/templates'))
env.get_template('base.html')
env.get_template('services.html')
" """
    run_cmd(jinja_check)
    print("  -> Seluruh sintaks dan template lulus verifikasi 100%.")

    # 3. Penyebaran Agen & Restart Service Lokal
    print("\n[3/5] Menyalin agen klien dan me-restart layanan systemd...")
    run_cmd("sudo cp agent/agent_pantau.py /opt/pantau/agent/agent_pantau.py")
    run_cmd("sudo systemctl restart agent_pantau.service pantau-server.service")
    res_status = run_cmd("sudo systemctl is-active agent_pantau.service pantau-server.service")
    if "inactive" in res_status.stdout or "failed" in res_status.stdout:
        print("[ERR] Salah satu layanan tidak aktif!", file=sys.stderr)
        sys.exit(1)
    print("  -> Layanan agent_pantau dan pantau-server aktif (running).")

    if args.skip_git:
        print("\n[*] Flag --skip-git aktif: Proses selesai tanpa Git commit/push/release.")
        return

    # 4. Git Commit & Push
    print("\n[4/5] Menjalankan alur Git staging, commit, dan push master...")
    commit_msg = args.commit_msg or f"chore(release): rilis versi v{new_ver}"
    all_files_to_add = set(mod_files + (args.extra_files or []))
    add_str = " ".join(f"'{f}'" for f in all_files_to_add) if all_files_to_add else "."
    run_cmd(f"git add {add_str}")
    run_cmd(f'git commit -m "{commit_msg}"')
    run_cmd("git push origin master")

    # 5. Git Tag & GitHub Release
    print("\n[5/5] Membuat git tag dan mempublikasikan GitHub Release...")
    tag_name = f"v{new_ver}"
    release_title = args.title or f"{tag_name} - Pembaruan Otomatis Pantau Server"
    release_notes = args.notes or f"Rilis otomatis versi {tag_name}."

    run_cmd(f'git tag -a {tag_name} -m "Release {tag_name}: {release_title}"')
    run_cmd(f"git push origin {tag_name}")
    run_cmd(f'gh release create {tag_name} --title "{release_title}" --notes "{release_notes}"')

    print(f"\n[SUCCESS] Rilis {tag_name} berhasil diselesaikan dan dipublikasikan secara penuh!\n")


if __name__ == "__main__":
    main()
