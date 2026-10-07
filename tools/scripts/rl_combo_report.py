"""Génère un rapport markdown depuis le JSONL de rl_combo_eval.py.

Output : top combos par agent + recommandation 1st/2nd choice.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", type=Path, help="JSONL de rl_combo_eval.py")
    ap.add_argument("--out", type=Path, default=None,
                    help="Markdown de sortie (défaut : <jsonl>.md)")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    if args.out is None:
        args.out = args.jsonl.with_suffix(".md")

    stats: dict = defaultdict(lambda: defaultdict(lambda: {"w": 0, "d": 0, "l": 0, "n": 0}))
    with args.jsonl.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("event") != "game_end":
                continue
            agent = r["agent"]
            key   = (r["faction"], r["champion"])
            stats[agent][key]["n"] += 1
            w = r["winner"]
            if w == "a":   stats[agent][key]["w"] += 1
            elif w == "b": stats[agent][key]["l"] += 1
            else:          stats[agent][key]["d"] += 1

    lines = ["# RL Agents — Combo Discovery Report", ""]
    lines.append(f"Source : `{args.jsonl}`")
    lines.append("")

    for agent in sorted(stats.keys()):
        combos = stats[agent]
        total_w  = sum(v["w"] for v in combos.values())
        total_d  = sum(v["d"] for v in combos.values())
        total_l  = sum(v["l"] for v in combos.values())
        total_n  = sum(v["n"] for v in combos.values())
        mean_wr  = (total_w + 0.5 * total_d) / max(total_n, 1) * 100

        lines.append(f"## {agent.upper()}")
        lines.append(f"_Total : {total_w}W {total_d}D {total_l}L ({total_n} games), "
                     f"mean WR {mean_wr:.1f}%_")
        lines.append("")

        # Top combos
        rows = []
        for (fid, c), v in combos.items():
            if v["n"] == 0:
                continue
            wr = (v["w"] + 0.5 * v["d"]) / v["n"] * 100
            rows.append((fid, c, wr, v["w"], v["d"], v["l"], v["n"]))
        rows.sort(key=lambda r: -r[2])

        lines.append(f"### Top {args.top} combos")
        lines.append("| Rang | Faction | Champion | WR | W-D-L |")
        lines.append("|---|--:|---|--:|--:|")
        for i, (fid, c, wr, w, d, l, n) in enumerate(rows[:args.top], 1):
            lines.append(f"| {i} | f{fid} | {c} | **{wr:.1f}%** | {w}-{d}-{l} |")

        # 1st & 2nd choice (different factions if possible)
        if rows:
            first = rows[0]
            second = None
            for r in rows[1:]:
                if r[0] != first[0]:  # different faction
                    second = r
                    break
            if second is None and len(rows) > 1:
                second = rows[1]

            lines.append("")
            lines.append("### Recommandation")
            lines.append(f"- **1st choice** : f{first[0]}+{first[1]} (WR {first[2]:.1f}%)")
            if second:
                lines.append(f"- **2nd choice** : f{second[0]}+{second[1]} (WR {second[2]:.1f}%)")

        # Faction summary
        by_fac = defaultdict(lambda: {"w": 0, "d": 0, "l": 0, "n": 0})
        for (fid, c), v in combos.items():
            by_fac[fid]["w"] += v["w"]
            by_fac[fid]["d"] += v["d"]
            by_fac[fid]["l"] += v["l"]
            by_fac[fid]["n"] += v["n"]
        fac_rank = sorted(by_fac.items(),
                          key=lambda kv: -((kv[1]["w"] + 0.5 * kv[1]["d"]) / max(kv[1]["n"], 1)))
        lines.append("")
        lines.append("### Faction summary")
        lines.append("| Faction | WR | Games |")
        lines.append("|--:|--:|--:|")
        for fid, v in fac_rank[:8]:
            wr = (v["w"] + 0.5 * v["d"]) / max(v["n"], 1) * 100
            lines.append(f"| f{fid} | {wr:.1f}% | {v['n']} |")
        lines.append("")

    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Report -> {args.out}")


if __name__ == "__main__":
    main()
