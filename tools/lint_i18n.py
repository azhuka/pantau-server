#!/usr/bin/env python3
"""
Automated i18n & Anti-Hardcoding Quality Gate for Pantau Server.
Scans all Vue templates in frontend/src/ to ensure:
1. Zero hardcoded Indonesian strings in templates (strict English default or t(...) mapping).
2. All table headers (<th>) use i18n t(...) bindings rather than raw unlocalized strings.
"""

import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_SRC = ROOT_DIR / "frontend" / "src"

FORBIDDEN_ID_WORDS = [
    "Nama", "Ukuran", "Izin", "Pemilik", "Waktu", "Tindakan",
    "Aksi", "Pilih", "Batal", "Simpan", "Tutup", "Kembali",
    "Memuat", "Berkas"
]

def check_file(file_path: Path) -> list:
    errors = []
    content = file_path.read_text(encoding="utf-8")
    
    # Check template block
    m = re.search(r"<template>(.*?)</template>", content, re.DOTALL)
    if not m:
        return errors

    template_str = m.group(1)
    lines = template_str.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        clean_line = line.strip()
        # Skip HTML comments
        if clean_line.startswith("<!--") or clean_line.startswith("//"):
            continue

        # 1. Check for forbidden Indonesian words in template
        for word in FORBIDDEN_ID_WORDS:
            # Word boundary check
            pattern = rf"\b{re.escape(word)}\b"
            if re.search(pattern, clean_line):
                # Ignore if inside a comment or data attribute
                if not ("data-i18n" in clean_line or "t(" in clean_line):
                    errors.append(
                        f"[{file_path.name}:{line_idx}] Hardcoded Indonesian word '{word}': {clean_line[:80]}"
                    )

        # 2. Check for raw <th>Text</th> without Vue binding
        th_match = re.search(r"<th\b[^>]*>([^<]+)</th>", clean_line)
        if th_match:
            raw_text = th_match.group(1).strip()
            # If it's not a Vue interpolation or empty
            if raw_text and not (raw_text.startswith("{{") and raw_text.endswith("}}")):
                errors.append(
                    f"[{file_path.name}:{line_idx}] Raw table header '{raw_text}' must use {{{{ t(...) }}}}: {clean_line[:80]}"
                )

    return errors

def main():
    print("[*] Running Anti-Hardcode & i18n Quality Gate...")
    all_errors = []

    for root, _, files in os.walk(FRONTEND_SRC):
        for f in files:
            if f.endswith(".vue"):
                full_path = Path(root) / f
                errs = check_file(full_path)
                all_errors.extend(errs)

    if all_errors:
        print(f"\n[ERROR] Found {len(all_errors)} hardcoded/i18n violations:")
        for err in all_errors:
            print(f"  -> {err}")
        print("\nFix these violations by wrapping text with useI18n t(...) before proceeding.")
        sys.exit(1)
    else:
        print("[OK] All Vue templates passed Anti-Hardcode & i18n Quality Gate 100%!")
        sys.exit(0)

if __name__ == "__main__":
    main()
