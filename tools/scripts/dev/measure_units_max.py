"""
measure_units_max.py
Mesure la distribution du nombre d'unités simultanées sur un échantillon de logs.
Usage : python -m tools.scripts.dev.measure_units_max [--n 1000] [--logdir ...]
"""
from __future__ import annotations

import argparse
import os
import re
import random
import sys
from pathlib import Path
from collections import Counter

RE_UNITS = re.compile(r"\bSTATE_[AB]\b.*\bunits=(\d+)")


def scan_file(path: str) -> list[int]:
    counts = []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = RE_UNITS.search(line)
                if m:
                    counts.append(int(m.group(1)))
    except Exception:
        pass
    return counts


def percentile(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    idx = int(len(sorted_vals) * p / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000,
                    help="Nombre de fichiers à échantillonner (défaut: 1000)")
    ap.add_argument("--logdir", type=str, default=None,
                    help="Chemin vers le dossier de logs (défaut: auto-détecté)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    # --- détection du dossier de logs ---
    if args.logdir:
        log_dir = Path(args.logdir)
    else:
        script_dir = Path(__file__).resolve()
        # remonte jusqu'à trouver DDM/logs/
        for parent in script_dir.parents:
            candidate = parent / "logs" / "autorun_log_data" / "log"
            if candidate.is_dir():
                log_dir = candidate
                break
        else:
            print("[ERREUR] Impossible de trouver le dossier de logs. Utilise --logdir.")
            sys.exit(1)

    all_files = list(log_dir.glob("*.log"))
    total = len(all_files)
    print(f"[INFO] {total} fichiers trouvés dans {log_dir}")

    # échantillon aléatoire reproductible parmi les fichiers les plus récents
    # on garde les 5000 plus récents puis on tire dedans
    all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    pool = all_files[:min(5000, total)]
    random.seed(args.seed)
    sample = random.sample(pool, min(args.n, len(pool)))
    print(f"[INFO] Échantillon : {len(sample)} fichiers (parmi les {len(pool)} plus récents)")

    # --- scan ---
    all_values: list[int] = []
    max_per_game: list[int] = []

    for i, f in enumerate(sample):
        vals = scan_file(str(f))
        if vals:
            all_values.extend(vals)
            max_per_game.append(max(vals))
        if (i + 1) % 100 == 0:
            print(f"  ... {i+1}/{len(sample)} fichiers scannés", end="\r")

    print()

    if not all_values:
        print("[ERREUR] Aucune valeur units= trouvée. Vérifie le format des logs.")
        sys.exit(1)

    all_values.sort()
    max_per_game.sort()

    # --- distribution du max par partie ---
    print("\n=== Distribution du MAX d'unités par partie ===")
    print(f"  Parties analysées      : {len(max_per_game)}")
    print(f"  Médiane (p50)          : {percentile(max_per_game, 50)}")
    print(f"  p75                    : {percentile(max_per_game, 75)}")
    print(f"  p90                    : {percentile(max_per_game, 90)}")
    print(f"  p95                    : {percentile(max_per_game, 95)}")
    print(f"  p99                    : {percentile(max_per_game, 99)}")
    print(f"  MAX absolu             : {max(max_per_game)}")

    # histogramme condensé du max par partie
    ctr = Counter(max_per_game)
    print("\n  Histogramme max/partie :")
    for k in sorted(ctr):
        bar = "#" * min(40, ctr[k] * 40 // max(ctr.values()))
        print(f"    {k:3d} unités : {bar} ({ctr[k]})")

    # --- distribution instantanée (toutes observations) ---
    print("\n=== Distribution instantanée (toutes observations STATE_) ===")
    print(f"  Observations totales   : {len(all_values)}")
    print(f"  Médiane (p50)          : {percentile(all_values, 50)}")
    print(f"  p90                    : {percentile(all_values, 90)}")
    print(f"  p99                    : {percentile(all_values, 99)}")
    print(f"  MAX absolu             : {max(all_values)}")

    # --- recommandation padding ---
    p99_max = percentile(max_per_game, 99)
    abs_max = max(max_per_game)
    recommended = abs_max + 1  # +1 marge
    print(f"\n=== Recommandation padding observation ===")
    print(f"  p99 max/partie         : {p99_max}")
    print(f"  MAX absolu             : {abs_max}")
    print(f"  N_MAX recommande       : {recommended}  (abs_max + 1 de marge)")
    print(f"  Taille vecteur MLP     : ~{20 + recommended * 10 * 2 + 3} floats")


if __name__ == "__main__":
    main()
