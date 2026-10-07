#!/usr/bin/env python3
"""Deduplicate identical logs between HvIA and AutoRuns folders.

Usage (dry-run):
  python tools/scripts/dedup_logs_by_hash.py

Apply deletions (keep hvia copy):
  python tools/scripts/dedup_logs_by_hash.py --apply --keep hvia

Apply deletions (keep autorun copy):
  python tools/scripts/dedup_logs_by_hash.py --apply --keep autorun
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Dict, Tuple


def sha1_file(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_project_root(start: Path) -> Path:
    for base in [start, *start.parents]:
        if (base / "logs").is_dir() and (base / "engine").is_dir():
            return base
    if start.parent.name.lower() == "scripts" and start.parent.parent.name.lower() == "tools":
        return start.parents[2]
    return Path.cwd().resolve()


def list_files(d: Path) -> Dict[str, Path]:
    if not d.exists():
        return {}
    return {p.name: p for p in d.glob("*") if p.is_file()}


def dedup_pair(hvia_dir: Path, autorun_dir: Path, keep: str, apply: bool) -> Tuple[int, int, int]:
    fa = list_files(hvia_dir)
    fb = list_files(autorun_dir)
    common = sorted(set(fa) & set(fb))

    same = diff = removed = 0
    root = find_project_root(hvia_dir)

    for name in common:
        pa, pb = fa[name], fb[name]
        ha, hb = sha1_file(pa), sha1_file(pb)
        if ha == hb:
            same += 1
            if keep == "hvia":
                victim, kept = pb, pa
            else:
                victim, kept = pa, pb
            try:
                kept_rel = kept.relative_to(root)
            except Exception:
                kept_rel = kept
            try:
                victim_rel = victim.relative_to(root)
            except Exception:
                victim_rel = victim
            print(f"[DUP] {name} -> keep: {kept_rel} ; remove: {victim_rel}")
            if apply:
                victim.unlink(missing_ok=True)
                removed += 1
        else:
            diff += 1
            print(f"[CONFLICT] {name} differs -> keep both / inspect (hvia={pa} | autorun={pb})")
    return same, diff, removed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually delete duplicates (default: dry-run)")
    ap.add_argument("--keep", choices=["hvia", "autorun"], default="hvia", help="Which copy to keep when identical")
    args = ap.parse_args()

    root = find_project_root(Path(__file__).resolve())

    hvia_log = root / "logs" / "log_data" / "log"
    hvia_stdout = root / "logs" / "log_data" / "stdout"
    autorun_log = root / "logs" / "autorun_log_data" / "log"
    autorun_stdout = root / "logs" / "autorun_log_data" / "stdout"

    print(f"Project root: {root}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'} | keep={args.keep}\n")

    total_same = total_diff = total_removed = 0

    for a, b, label in [
        (hvia_log, autorun_log, "log"),
        (hvia_stdout, autorun_stdout, "stdout"),
    ]:
        print(f"== Checking {label}:\n  hvia:   {a}\n  autorun:{b}")
        same, diff, removed = dedup_pair(a, b, args.keep, args.apply)
        total_same += same
        total_diff += diff
        total_removed += removed
        print(f" -> identical={same} | conflicts={diff} | removed={removed}\n")

    print(f"Done. identical={total_same} | conflicts={total_diff} | removed={total_removed}")
    if not args.apply:
        print("(dry-run) Re-run with --apply to delete the duplicates.")
    if total_diff:
        print("Conflicts exist: those files are different. Inspect manually before deleting.")


if __name__ == "__main__":
    main()
