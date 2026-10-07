"""Compare jin variants v1 / v2 (=v2b) / v2c / v2d, agg over seeds 42,137,999."""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "rl" / "checkpoints" / "eval_multiseed"
SEEDS = [42, 137, 999]
VARIANTS = ["v1", "v2", "v2c", "v2d"]
LABEL = {"v1": "v1 (initial)", "v2": "v2b (sonnet anchor)",
         "v2c": "v2c (opus + claude/mistral)", "v2d": "v2d (opus + grok/gemini)"}


def load(variant: str) -> dict:
    agg = defaultdict(lambda: {"wins": 0, "draws": 0, "losses": 0, "games": 0})
    found = []
    for s in SEEDS:
        p = BASE / variant / f"seed{s}" / "jin" / "jin_opus_eval.csv"
        if not p.exists():
            continue
        found.append(s)
        with p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                k = (r["faction"], r["champion"])
                for kk in ("wins", "draws", "losses", "games"):
                    agg[k][kk] += int(r[kk])
    for v in agg.values():
        v["wr"] = (v["wins"] / v["games"]) if v["games"] else 0.0
    return {"combos": dict(agg), "seeds": found}


def main():
    data = {v: load(v) for v in VARIANTS}

    # Overview
    print(f"{'Variant':<32} {'seeds':<14} {'games':>6} {'WR':>7}")
    print("-" * 64)
    for v in VARIANTS:
        d = data[v]
        c = d["combos"]
        w = sum(x["wins"] for x in c.values())
        g = sum(x["games"] for x in c.values())
        wr = (w / g * 100) if g else 0
        s = ",".join(map(str, d["seeds"])) if d["seeds"] else "—"
        if g == 0:
            print(f"{LABEL[v]:<32} {s:<14} {'-':>6} {'-':>7}")
        else:
            print(f"{LABEL[v]:<32} {s:<14} {g:>6} {wr:>6.1f}%")

    # Best combo per variant
    print()
    print("Best combo per variant (WR / games)")
    print("-" * 64)
    for v in VARIANTS:
        c = data[v]["combos"]
        if not c:
            print(f"  {LABEL[v]:<32} —")
            continue
        b = max(c.items(), key=lambda kv: kv[1]["wr"])
        f, ch = b[0]
        x = b[1]
        print(f"  {LABEL[v]:<32} f{f}_{ch} {x['wr']*100:5.1f}% ({x['wins']}/{x['games']})")

    # Side-by-side per combo (only combos present in all available variants)
    avail = [v for v in VARIANTS if data[v]["combos"]]
    if len(avail) < 2:
        return
    print()
    print(f"=== Per combo, {' / '.join(avail)} ===")
    keys = set(data[avail[0]]["combos"])
    for v in avail[1:]:
        keys &= set(data[v]["combos"])
    rows = []
    for k in sorted(keys):
        wrs = [data[v]["combos"][k]["wr"] for v in avail]
        rows.append((k, wrs))
    rows.sort(key=lambda r: -max(r[1]))

    header = f"{'F':<3} {'C':<3}" + "".join(f"  {v:>7}" for v in avail) + "   best"
    print(header)
    print("-" * len(header))
    for (f, c), wrs in rows:
        cells = "".join(f"  {w*100:>6.1f}%" for w in wrs)
        best = avail[wrs.index(max(wrs))]
        print(f"f{f:<2} {c:<3}{cells}   {best}")


if __name__ == "__main__":
    main()
