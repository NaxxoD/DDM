"""
rl/build_jaeha_empirical.py
Scanne tous les checkpoints Jaeha (toutes versions) et construit
une matrice empirique position x adversaire -> WR moyen.

Usage :
    python -m rl.build_jaeha_empirical
    python -m rl.build_jaeha_empirical --out rl/checkpoints/jaeha_empirical.md
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


OPPONENTS = ["haiku", "mistral", "grok", "gemini", "chatgpt", "sonnet", "opus"]
N_STAGES  = 7


def find_jaeha_csvs(root: Path) -> list[Path]:
    """Trouve tous les CSV de training Jaeha phase 2 (pas greedy)."""
    csvs = []
    for p in root.rglob("jaeha*training.csv"):
        if "greedy" not in p.name:
            csvs.append(p)
    return sorted(csvs)


def extract_stage_wrs(csv_path: Path) -> list[dict]:
    """
    Extrait le WR final de chaque stage depuis un CSV de training.
    Retourne une liste de dicts {stage, opponent, wr}.
    """
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        return []

    # Groupe par stage — on prend la dernière ligne de chaque stage (WR le plus récent)
    stages: dict[str, list] = defaultdict(list)
    for row in rows:
        stages[row["stage"]].append(row)

    results = []
    for stage_idx, stage_rows in sorted(stages.items(), key=lambda x: int(x[0])):
        last = stage_rows[-1]
        try:
            wr = float(last["wr"])
        except (ValueError, KeyError):
            continue
        if wr != wr:  # nan
            continue
        results.append({
            "stage":    int(stage_idx),
            "opponent": last["opponent"].strip(),
            "wr":       wr,
        })
    return results


def build_matrix(csvs: list[Path]) -> tuple[dict, dict]:
    """
    Construit deux dicts :
      data[(position, opponent)] = [wr1, wr2, ...]
      runs_per_opp[opponent]     = nombre de fois rencontré
    """
    data: dict = defaultdict(list)
    runs_per_opp: dict = defaultdict(int)

    for csv_path in csvs:
        stage_wrs = extract_stage_wrs(csv_path)
        for entry in stage_wrs:
            key = (entry["stage"], entry["opponent"])
            data[key].append(entry["wr"])
            runs_per_opp[entry["opponent"]] += 1

    return data, runs_per_opp


def format_cell(values: list[float]) -> str:
    if not values:
        return "  —  "
    avg = sum(values) / len(values)
    n   = len(values)
    return f"{avg:.1%}(n={n})"


def write_md(data: dict, runs_per_opp: dict, out_path: Path, total_runs: int):
    lines = [
        "# JAEHA — Matrice empirique curriculum (position × adversaire)\n",
        f"Runs phase 2 analysés : **{total_runs}**\n",
        "Valeurs : WR moyen (n = nombre de fois en cette position)\n",
    ]

    # Header
    header = "| Pos |" + "".join(f" {opp:<14}|" for opp in OPPONENTS)
    sep    = "|-----|" + "".join(f":{'-'*14}:|" for _ in OPPONENTS)
    lines += [header, sep]

    # Rows
    for pos in range(N_STAGES):
        row = f"|  {pos}  |"
        for opp in OPPONENTS:
            cell = format_cell(data.get((pos, opp), []))
            row += f" {cell:<14}|"
        lines.append(row)

    # Best position par adversaire
    lines += [
        "\n## Meilleure position par adversaire\n",
        "| Adversaire | Meilleure pos | WR moyen | Runs |",
        "|------------|---------------|----------|------|",
    ]
    for opp in OPPONENTS:
        best_pos, best_wr, best_n = None, 0.0, 0
        for pos in range(N_STAGES):
            vals = data.get((pos, opp), [])
            if vals:
                avg = sum(vals) / len(vals)
                if avg > best_wr:
                    best_wr, best_pos, best_n = avg, pos, len(vals)
        if best_pos is not None:
            lines.append(f"| {opp:<10} | stage {best_pos}       | {best_wr:.1%}   | {best_n}    |")
        else:
            lines.append(f"| {opp:<10} | —             | —        | 0    |")

    # Ordre optimal suggéré (tri par best_pos croissant)
    order_suggestion = []
    for opp in OPPONENTS:
        best_pos = 0
        best_wr  = -1.0
        for pos in range(N_STAGES):
            vals = data.get((pos, opp), [])
            if vals:
                avg = sum(vals) / len(vals)
                if avg > best_wr:
                    best_wr, best_pos = avg, pos
        order_suggestion.append((best_pos, best_wr, opp))
    order_suggestion.sort(key=lambda x: x[0])

    lines += [
        "\n## Ordre optimal suggéré (basé sur meilleure position empirique)\n",
        "```",
        " → ".join(o[2] for o in order_suggestion),
        "```",
        f"\n*Dernière mise à jour : {__import__('datetime').date.today()}*\n",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[OK] Matrice écrite : {out_path}  ({total_runs} runs)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="rl/checkpoints",
                    help="Racine des checkpoints (cherche récursivement)")
    ap.add_argument("--out",  default="rl/checkpoints/jaeha_empirical.md",
                    help="Fichier MD de sortie")
    args = ap.parse_args()

    root = Path(args.root)
    out  = Path(args.out)

    csvs = find_jaeha_csvs(root)
    if not csvs:
        print(f"[WARN] Aucun CSV Jaeha phase 2 trouvé sous {root}")
        return

    print(f"[INFO] {len(csvs)} CSV(s) trouvé(s) :")
    for c in csvs:
        print(f"  {c}")

    data, runs_per_opp = build_matrix(csvs)
    total_runs = max((len(v) for v in data.values()), default=0)
    write_md(data, runs_per_opp, out, total_runs)


if __name__ == "__main__":
    main()
