"""Compare RL eval results v1 (baseline backup) vs v2 (latest run).

Usage:
    python tools/scripts/compare_eval_v1_v2.py
    python tools/scripts/compare_eval_v1_v2.py --top 15
    python tools/scripts/compare_eval_v1_v2.py --csv-out reports/eval_v1_vs_v2.csv
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
EVAL_DIR = ROOT / "rl" / "checkpoints" / "eval"
V1_DIR = EVAL_DIR / "_v1_baseline_2026-04-22"
AGENTS = ["cross", "jaeha", "jin", "jio"]


def load_csv(path: Path) -> dict[tuple[str, str], dict]:
    """Return {(faction, champion): {wins, draws, losses, games, wr, phase}}.

    If a combo appears in both exploration and confirmation rows, sum them.
    """
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
    for v in agg.values():
        v["wr"] = (v["wins"] / v["games"]) if v["games"] else 0.0
    return dict(agg)


def agent_totals(combos: dict) -> dict:
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
    ap.add_argument("--top", type=int, default=10, help="Top N biggest WR moves to show")
    ap.add_argument("--csv-out", type=Path, default=None, help="Write per-combo diff CSV")
    args = ap.parse_args()

    print(f"V1 baseline : {V1_DIR}")
    print(f"V2 latest   : {EVAL_DIR}/<agent>/")
    print()

    # Per-agent overview
    print(f"{'Agent':<8} {'V1 games':>9} {'V1 WR':>7} {'V2 games':>9} {'V2 WR':>7} {'Δ WR':>9}")
    print("-" * 56)
    summary_rows = []
    all_diffs = []
    for a in AGENTS:
        v1 = load_csv(V1_DIR / f"{a}_opus_eval.csv")
        v2 = load_csv(EVAL_DIR / a / f"{a}_opus_eval.csv")
        t1, t2 = agent_totals(v1), agent_totals(v2)
        delta = t2["wr"] - t1["wr"]
        v2_status = "—" if t2["games"] == 0 else ""
        if t2["games"] == 0:
            print(
                f"{a:<8} {t1['games']:>9} {t1['wr']*100:>6.1f}% {'(no v2)':>9} {'-':>7} {'-':>9}"
            )
        else:
            print(
                f"{a:<8} {t1['games']:>9} {t1['wr']*100:>6.1f}% "
                f"{t2['games']:>9} {t2['wr']*100:>6.1f}% {fmt_delta(delta):>9}"
            )
        summary_rows.append((a, v1, v2))
        # Collect per-combo diffs
        keys = set(v1) | set(v2)
        for k in keys:
            wr1 = v1.get(k, {}).get("wr")
            wr2 = v2.get(k, {}).get("wr")
            g1 = v1.get(k, {}).get("games", 0)
            g2 = v2.get(k, {}).get("games", 0)
            if wr1 is None or wr2 is None or g2 == 0:
                continue
            all_diffs.append((a, k[0], k[1], wr1, wr2, wr2 - wr1, g1, g2))

    # Top movers
    if all_diffs:
        print()
        print(f"=== Top {args.top} biggest WR shifts (V2 - V1) ===")
        all_diffs.sort(key=lambda r: r[5], reverse=True)
        print(f"{'Agent':<7} {'F':<3} {'C':<3} {'V1 WR':>7} {'V2 WR':>7} {'Δ':>9}  games(v1→v2)")
        print("-" * 60)
        biggest = all_diffs[: args.top] + all_diffs[-args.top :]
        seen = set()
        for row in biggest:
            if row in seen:
                continue
            seen.add(row)
            a, f_, c, w1, w2, d, g1, g2 = row
            tag = "↑" if d > 0 else "↓"
            print(
                f"{a:<7} f{f_:<2} {c:<3} {w1*100:>6.1f}% {w2*100:>6.1f}% "
                f"{fmt_delta(d):>9} {tag}  {g1}→{g2}"
            )

    # Per-agent best combo before/after
    print()
    print("=== Best combo per agent (V1 vs V2) ===")
    for a, v1, v2 in summary_rows:
        if not v1 and not v2:
            continue
        b1 = max(v1.items(), key=lambda kv: kv[1]["wr"]) if v1 else None
        b2 = max(v2.items(), key=lambda kv: kv[1]["wr"]) if v2 else None
        s1 = f"f{b1[0][0]}_{b1[0][1]} {b1[1]['wr']*100:.0f}%" if b1 else "—"
        s2 = f"f{b2[0][0]}_{b2[0][1]} {b2[1]['wr']*100:.0f}%" if b2 else "—"
        print(f"  {a:<8} V1: {s1:<15} V2: {s2}")

    if args.csv_out:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["agent", "faction", "champion", "wr_v1", "wr_v2", "delta", "games_v1", "games_v2"])
            for row in sorted(all_diffs, key=lambda r: (r[0], r[1], r[2])):
                w.writerow([row[0], row[1], row[2], f"{row[3]:.4f}", f"{row[4]:.4f}", f"{row[5]:.4f}", row[6], row[7]])
        print(f"\nPer-combo diff CSV: {args.csv_out}")


if __name__ == "__main__":
    main()
