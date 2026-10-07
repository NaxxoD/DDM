"""Compare laptop (Proto_DDM) vs desktop (DDM) project trees.

Usage:
    python tools/scripts/diff_machines.py --laptop F:/DDM/Proto_DDM --desktop F:/Projets Tour/Dev/DDM
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Patterns à ignorer (générés / pas pertinents pour comparaison)
IGNORE_DIRS = {
    "__pycache__", ".venv", "venv", "env",
    "logs", "rl_logs",
    ".vscode", ".idea", ".git",
    "_archive",
    "checkpoints",  # rl/checkpoints/
    "snapshots",    # engine/snapshots/
    "_pre_migration_backup",
}
IGNORE_SUFFIXES = {
    ".pyc", ".pyo", ".pyd", ".log", ".tmp", ".bak",
}
IGNORE_FILES = {
    ".DS_Store", "Thumbs.db",
}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & IGNORE_DIRS:
        return True
    if path.name in IGNORE_FILES:
        return True
    if path.suffix.lower() in IGNORE_SUFFIXES:
        return True
    return False


def walk(root: Path) -> dict[str, tuple[int, str]]:
    """Returns {relative_path: (size, md5)} for all non-ignored files."""
    out = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if should_skip(rel):
            continue
        try:
            size = p.stat().st_size
            # md5 only for small files (< 2 MB) to keep it fast
            if size < 2 * 1024 * 1024:
                with p.open("rb") as f:
                    md5 = hashlib.md5(f.read()).hexdigest()
            else:
                md5 = f"size:{size}"  # pour les gros, comparer juste taille
            out[str(rel).replace("\\", "/")] = (size, md5)
        except (OSError, PermissionError):
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--laptop",  required=True, help="Path laptop side (Proto_DDM)")
    ap.add_argument("--desktop", required=True, help="Path desktop side")
    ap.add_argument("--max-print", type=int, default=200,
                    help="Max files in chaque catégorie")
    args = ap.parse_args()

    laptop  = Path(args.laptop).resolve()
    desktop = Path(args.desktop).resolve()
    if not laptop.is_dir():  raise SystemExit(f"laptop n'existe pas: {laptop}")
    if not desktop.is_dir(): raise SystemExit(f"desktop n'existe pas: {desktop}")

    print(f"Laptop  : {laptop}")
    print(f"Desktop : {desktop}")
    print()
    print("Scanning laptop ...", end="", flush=True)
    L = walk(laptop)
    print(f" {len(L)} files")
    print("Scanning desktop ...", end="", flush=True)
    D = walk(desktop)
    print(f" {len(D)} files")

    only_laptop  = sorted(set(L) - set(D))
    only_desktop = sorted(set(D) - set(L))
    both         = sorted(set(L) & set(D))
    differ       = [r for r in both if L[r] != D[r]]
    identical    = [r for r in both if L[r] == D[r]]

    print()
    print("=" * 60)
    print(f"  RÉSUMÉ")
    print("=" * 60)
    print(f"  Identiques     : {len(identical)}")
    print(f"  Différents     : {len(differ)}")
    print(f"  Seulement laptop : {len(only_laptop)}")
    print(f"  Seulement desktop: {len(only_desktop)}")

    def show(title, items, with_size=None):
        print()
        print(f"=== {title} ({len(items)}) ===")
        if not items:
            print("  (aucun)")
            return
        for r in items[: args.max_print]:
            if with_size:
                lsize, dsize = with_size(r)
                print(f"  {r}  (lap={lsize} desk={dsize})")
            else:
                print(f"  {r}")
        if len(items) > args.max_print:
            print(f"  ... et {len(items) - args.max_print} de plus (utilise --max-print plus haut)")

    show("FICHIERS DIFFÉRENTS (laptop ≠ desktop)", differ,
         with_size=lambda r: (L[r][0], D[r][0]))
    show("SEULEMENT LAPTOP (à intégrer ?)", only_laptop)
    show("SEULEMENT DESKTOP (gardé localement)", only_desktop)


if __name__ == "__main__":
    main()
