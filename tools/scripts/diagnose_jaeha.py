"""Diagnose Jaeha's weaknesses from bracket JSONL data.

Analyzes:
- WR by faction × champion drawn
- WR by opponent
- WR by opponent's faction (counter-pick analysis)
- Turn distribution (loses fast or slow?)
- HQ damage distribution at game end
- Top losing combos vs winning combos
- Specific killer matchups (combo vs combo)

Usage:
    python tools/scripts/diagnose_jaeha.py --jsonl reports/bracket/post_migr_blind/matrix.jsonl reports/bracket/post_migr_blind/bracket.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load(paths: list[str]) -> list[dict]:
    games = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("event") == "game_end":
                        games.append(rec)
                except json.JSONDecodeError:
                    continue
    return games


def jaeha_games(games: list[dict]) -> list[dict]:
    """Returns games where jaeha played, with normalized fields:
       jaeha_faction, jaeha_champion, jaeha_won, opp, opp_faction, opp_champion, turns, jaeha_hq, opp_hq
    """
    out = []
    for g in games:
        a, b = g.get("side_a"), g.get("side_b")
        if a == "jaeha":
            out.append({
                "jaeha_faction":  g.get("faction_a"),
                "jaeha_champion": g.get("champion_a"),
                "jaeha_won":      g["winner"] == "a",
                "is_draw":        g["winner"] == "draw",
                "opp":            b,
                "opp_faction":    g.get("faction_b"),
                "opp_champion":   g.get("champion_b"),
                "turns":          g.get("turns", 0),
                "jaeha_hq":       g.get("hq_a", 0),
                "opp_hq":         g.get("hq_b", 0),
            })
        elif b == "jaeha":
            out.append({
                "jaeha_faction":  g.get("faction_b"),
                "jaeha_champion": g.get("champion_b"),
                "jaeha_won":      g["winner"] == "b",
                "is_draw":        g["winner"] == "draw",
                "opp":            a,
                "opp_faction":    g.get("faction_a"),
                "opp_champion":   g.get("champion_a"),
                "turns":          g.get("turns", 0),
                "jaeha_hq":       g.get("hq_b", 0),
                "opp_hq":         g.get("hq_a", 0),
            })
    return out


def section(title: str) -> str:
    return f"\n{'='*60}\n  {title}\n{'='*60}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", nargs="+", required=True)
    args = ap.parse_args()

    all_games = load(args.jsonl)
    jg = jaeha_games(all_games)
    if not jg:
        print("No jaeha games found.")
        sys.exit(0)

    n = len(jg)
    wins = sum(1 for g in jg if g["jaeha_won"])
    draws = sum(1 for g in jg if g["is_draw"])
    losses = n - wins - draws
    overall_wr = (wins + 0.5 * draws) / n

    print(section("OVERVIEW"))
    print(f"  Total games   : {n}")
    print(f"  Wins / Draws / Losses : {wins} / {draws} / {losses}")
    print(f"  Overall WR    : {overall_wr*100:.2f}%")

    # --- WR par faction Jaeha ---
    print(section("WR PAR FACTION JAEHA TIRÉE"))
    by_f = defaultdict(lambda: {"w": 0, "n": 0})
    for g in jg:
        by_f[g["jaeha_faction"]]["n"] += 1
        if g["jaeha_won"]:
            by_f[g["jaeha_faction"]]["w"] += 1
    rows = sorted(by_f.items(), key=lambda kv: -(kv[1]["w"] / kv[1]["n"]) if kv[1]["n"] else 0)
    for f, v in rows:
        wr = v["w"] / v["n"] * 100 if v["n"] else 0
        print(f"  f{f}  WR {wr:5.1f}%  ({v['w']}/{v['n']})")

    # --- WR par champion ---
    print(section("WR PAR CHAMPION JAEHA TIRÉ"))
    by_c = defaultdict(lambda: {"w": 0, "n": 0})
    for g in jg:
        by_c[g["jaeha_champion"]]["n"] += 1
        if g["jaeha_won"]:
            by_c[g["jaeha_champion"]]["w"] += 1
    rows = sorted(by_c.items(), key=lambda kv: -(kv[1]["w"] / kv[1]["n"]) if kv[1]["n"] else 0)
    for c, v in rows:
        wr = v["w"] / v["n"] * 100 if v["n"] else 0
        print(f"  {c}   WR {wr:5.1f}%  ({v['w']}/{v['n']})")

    # --- WR par opponent ---
    print(section("WR PAR OPPONENT"))
    by_opp = defaultdict(lambda: {"w": 0, "n": 0})
    for g in jg:
        by_opp[g["opp"]]["n"] += 1
        if g["jaeha_won"]:
            by_opp[g["opp"]]["w"] += 1
    rows = sorted(by_opp.items(), key=lambda kv: -(kv[1]["w"] / kv[1]["n"]) if kv[1]["n"] else 0)
    for opp, v in rows:
        wr = v["w"] / v["n"] * 100 if v["n"] else 0
        print(f"  vs {opp:<8} WR {wr:5.1f}%  ({v['w']}/{v['n']})")

    # --- WR par faction adverse ---
    print(section("WR PAR FACTION ADVERSE (counter-pick)"))
    by_opp_f = defaultdict(lambda: {"w": 0, "n": 0})
    for g in jg:
        by_opp_f[g["opp_faction"]]["n"] += 1
        if g["jaeha_won"]:
            by_opp_f[g["opp_faction"]]["w"] += 1
    rows = sorted(by_opp_f.items(), key=lambda kv: -(kv[1]["w"] / kv[1]["n"]) if kv[1]["n"] else 0)
    for f, v in rows:
        wr = v["w"] / v["n"] * 100 if v["n"] else 0
        print(f"  vs f{f}  WR {wr:5.1f}%  ({v['w']}/{v['n']})")

    # --- Distribution des tours ---
    print(section("DISTRIBUTION DES TOURS (fast vs slow loss)"))
    won = [g["turns"] for g in jg if g["jaeha_won"]]
    lost = [g["turns"] for g in jg if not g["jaeha_won"] and not g["is_draw"]]
    if won:
        print(f"  Wins  - mean={statistics.mean(won):.1f} median={statistics.median(won):.1f} "
              f"min={min(won)} max={max(won)}")
    if lost:
        print(f"  Loss  - mean={statistics.mean(lost):.1f} median={statistics.median(lost):.1f} "
              f"min={min(lost)} max={max(lost)}")
    if won and lost:
        diff = statistics.mean(lost) - statistics.mean(won)
        print(f"  Diff  : losses durent en moyenne {diff:+.1f} tours de plus que les wins")

    # Histogramme rapide
    print()
    print("  Histogramme tours (loss):")
    bins = [(0, 30), (30, 50), (50, 70), (70, 100), (100, 200)]
    for lo, hi in bins:
        count = sum(1 for t in lost if lo <= t < hi)
        bar = "█" * (count // 5)
        print(f"  [{lo:>3}-{hi:<3}]  {count:>3}  {bar}")

    # --- Damage HQ at end ---
    print(section("DÉGÂTS QG À LA FIN (loss only)"))
    losses_data = [g for g in jg if not g["jaeha_won"] and not g["is_draw"]]
    if losses_data:
        # Jaeha QG starts at 35
        jaeha_hp_remaining = [max(0, g["jaeha_hq"]) for g in losses_data]
        opp_hp_remaining = [g["opp_hq"] for g in losses_data]
        print(f"  Jaeha HP à la fin  : mean={statistics.mean(jaeha_hp_remaining):.1f}  median={statistics.median(jaeha_hp_remaining):.1f}")
        print(f"  Opp HP à la fin    : mean={statistics.mean(opp_hp_remaining):.1f}  median={statistics.median(opp_hp_remaining):.1f}")
        # Jaeha killed → his hp went to ≤0 → mean opp_hp tells how much damage Jaeha had time to deal
        diff_avg = 35 - statistics.mean(opp_hp_remaining)
        print(f"  Dégâts moyens infligés au QG adverse avant de perdre : {diff_avg:.1f} / 35")

    # --- Top losing combos ---
    print(section("TOP COMBOS PERDANTS (Jaeha)"))
    combo_stats = defaultdict(lambda: {"w": 0, "n": 0})
    for g in jg:
        key = (g["jaeha_faction"], g["jaeha_champion"])
        combo_stats[key]["n"] += 1
        if g["jaeha_won"]:
            combo_stats[key]["w"] += 1
    # Filter to combos played ≥ 8 times for stats
    rows = [(k, v) for k, v in combo_stats.items() if v["n"] >= 8]
    rows.sort(key=lambda kv: kv[1]["w"] / kv[1]["n"])
    print("  Pires combos (≥8 games) :")
    for (f, c), v in rows[:8]:
        wr = v["w"] / v["n"] * 100
        print(f"    f{f}+{c}  WR {wr:5.1f}%  ({v['w']}/{v['n']})")
    print("  Meilleurs combos (≥8 games) :")
    for (f, c), v in rows[-8:][::-1]:
        wr = v["w"] / v["n"] * 100
        print(f"    f{f}+{c}  WR {wr:5.1f}%  ({v['w']}/{v['n']})")

    # --- Top killer matchups ---
    print(section("TOP MATCHUPS DE LA MORT (combo Jaeha vs faction adverse)"))
    matchup_stats = defaultdict(lambda: {"w": 0, "n": 0})
    for g in jg:
        key = (g["jaeha_faction"], g["jaeha_champion"], g["opp_faction"])
        matchup_stats[key]["n"] += 1
        if g["jaeha_won"]:
            matchup_stats[key]["w"] += 1
    rows = [(k, v) for k, v in matchup_stats.items() if v["n"] >= 5]
    rows.sort(key=lambda kv: kv[1]["w"] / kv[1]["n"])
    print("  Pires matchups (≥5 games) :")
    for (jf, jc, of_), v in rows[:10]:
        wr = v["w"] / v["n"] * 100
        print(f"    Jaeha f{jf}+{jc}  vs  f{of_}  → WR {wr:5.1f}%  ({v['w']}/{v['n']})")


if __name__ == "__main__":
    main()
