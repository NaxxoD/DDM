"""Compare RL eval results v1 vs v2 across multiple seeds.

Reads from rl/checkpoints/eval_multiseed/{version}/seed{N}/{agent}/{agent}_opus_eval.csv
and aggregates by version (sum across seeds), then compares v1 vs v2.

Usage:
    python tools/scripts/compare_eval_multiseed.py
    python tools/scripts/compare_eval_multiseed.py --top 15 --csv-out reports/Report/eval_multiseed_v1_vs_v2.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "rl" / "checkpoints" / "eval_multiseed"
AGENTS = ["cross", "jaeha", "jin", "jio"]
VERSIONS = ["v1", "v2"]
SEEDS = [42, 137, 999]


def load_csv(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"wins": 0, "draws": 0, "losses": 0, "games": 0}
    )
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (str(r["faction"]), str(r["champion"]))
            agg[key]["wins"] += int(r["wins"])
            agg[key]["draws"] += int(r["draws"])
            agg[key]["losses"] += int(r["losses"])
            agg[key]["games"] += int(r["games"])
    return dict(agg)


def aggregate_seeds(version: str, agent: str) -> tuple[dict, list[int]]:
    """Sum results from all seeds for given (version, agent). Returns (combos, found_seeds)."""
    combos: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"wins": 0, "draws": 0, "losses": 0, "games": 0}
    )
    found = []
    for s in SEEDS:
        p = BASE / version / f"seed{s}" / agent / f"{agent}_opus_eval.csv"
        loaded = load_csv(p)
        if not loaded:
            continue
        found.append(s)
        for k, v in loaded.items():
            for kk in ("wins", "draws", "losses", "games"):
                combos[k][kk] += v[kk]
    for v in combos.values():
        v["wr"] = (v["wins"] / v["games"]) if v["games"] else 0.0
    return dict(combos), found


def totals(combos: dict) -> dict:
    w = sum(v["wins"] for v in combos.values())
    d = sum(v["draws"] for v in combos.values())
    l = sum(v["losses"] for v in combos.values())
    g = sum(v["games"] for v in combos.values())
    return {"wins": w, "draws": d, "losses": l, "games": g, "wr": (w / g) if g else 0.0}


def fmt_delta(d: float) -> str:
    sign = "+" if d > 0 else ""
    return f"{sign}{d * 100:5.1f}pts"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--csv-out", type=Path, default=None)
    args = ap.parse_args()

    print(f"Source: {BASE}")
    print(f"Seeds : {SEEDS} (agreges par version)")
    print()

    print(f"{'Agent':<8} {'V1 seeds':<10} {'V1 games':>9} {'V1 WR':>7}  "
          f"{'V2 seeds':<10} {'V2 games':>9} {'V2 WR':>7} {'Δ WR':>9}")
    print("-" * 80)

    all_diffs = []
    summary = []
    for a in AGENTS:
        c1, s1 = aggregate_seeds("v1", a)
        c2, s2 = aggregate_seeds("v2", a)
        t1, t2 = totals(c1), totals(c2)
        delta = t2["wr"] - t1["wr"]
        s1_str = ",".join(map(str, s1)) if s1 else "—"
        s2_str = ",".join(map(str, s2)) if s2 else "—"
        if t2["games"] == 0 or t1["games"] == 0:
            print(f"{a:<8} {s1_str:<10} {t1['games']:>9} "
                  f"{(t1['wr']*100 if t1['games'] else 0):>6.1f}%  "
                  f"{s2_str:<10} {t2['games']:>9} "
                  f"{(t2['wr']*100 if t2['games'] else 0):>6.1f}% {'-':>9}")
        else:
            print(f"{a:<8} {s1_str:<10} {t1['games']:>9} {t1['wr']*100:>6.1f}%  "
                  f"{s2_str:<10} {t2['games']:>9} {t2['wr']*100:>6.1f}% "
                  f"{fmt_delta(delta):>9}")
        summary.append((a, c1, c2))
        keys = set(c1) | set(c2)
        for k in keys:
            v1c, v2c = c1.get(k), c2.get(k)
            if not v1c or not v2c or v1c["games"] == 0 or v2c["games"] == 0:
                continue
            all_diffs.append(
                (a, k[0], k[1], v1c["wr"], v2c["wr"], v2c["wr"] - v1c["wr"],
                 v1c["games"], v2c["games"])
            )

    if all_diffs:
        print()
        print(f"=== Top {args.top} hausses & {args.top} baisses (V2 - V1) ===")
        all_diffs.sort(key=lambda r: r[5], reverse=True)
        biggest = all_diffs[: args.top] + all_diffs[-args.top :]
        seen = set()
        print(f"{'Agent':<7} {'F':<3} {'C':<3} {'V1 WR':>7} {'V2 WR':>7} {'Δ':>9}  games(v1/v2)")
        print("-" * 60)
        for row in biggest:
            if row in seen:
                continue
            seen.add(row)
            a, f_, c, w1, w2, d, g1, g2 = row
            tag = "↑" if d > 0 else "↓"
            print(f"{a:<7} f{f_:<2} {c:<3} {w1*100:>6.1f}% {w2*100:>6.1f}% "
                  f"{fmt_delta(d):>9} {tag}  {g1}/{g2}")

    print()
    print("=== Best combo per agent (V1 vs V2) ===")
    for a, c1, c2 in summary:
        b1 = max(c1.items(), key=lambda kv: kv[1]["wr"]) if c1 else None
        b2 = max(c2.items(), key=lambda kv: kv[1]["wr"]) if c2 else None
        s1 = (f"f{b1[0][0]}_{b1[0][1]} {b1[1]['wr']*100:.1f}% "
              f"({b1[1]['wins']}/{b1[1]['games']})") if b1 else "—"
        s2 = (f"f{b2[0][0]}_{b2[0][1]} {b2[1]['wr']*100:.1f}% "
              f"({b2[1]['wins']}/{b2[1]['games']})") if b2 else "—"
        print(f"  {a:<8} V1: {s1:<28} V2: {s2}")

    if args.csv_out:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["agent", "faction", "champion", "wr_v1", "wr_v2", "delta",
                        "games_v1", "games_v2"])
            for row in sorted(all_diffs, key=lambda r: (r[0], r[1], r[2])):
                w.writerow([row[0], row[1], row[2], f"{row[3]:.4f}",
                            f"{row[4]:.4f}", f"{row[5]:.4f}", row[6], row[7]])
        print(f"\nPer-combo diff CSV: {args.csv_out}")


if __name__ == "__main__":
    main()
