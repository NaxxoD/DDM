"""Watcher helper — reads matrix.jsonl + bracket.jsonl and prints live state.

Called once per refresh by watch_bracket.bat (which clears + sleeps).
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_games(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("event") == "game_end":
                    out.append(rec)
            except json.JSONDecodeError:
                pass
    return out


def tally(group: list[dict]) -> dict[str, int]:
    wins = defaultdict(int)
    for g in group:
        if g["winner"] == "a":
            wins[g["side_a"]] += 1
        elif g["winner"] == "b":
            wins[g["side_b"]] += 1
    return wins


def matrix_section(games: list[dict]) -> str:
    if not games:
        return "MATRIX : 0 games"
    n = len(games)
    target = 1800  # 6 pairs × 3 seeds × 2 mirrors × 50 games
    pct = n / target * 100
    bar_len = 40
    fill = int(bar_len * min(1.0, n / target))
    bar = "█" * fill + "░" * (bar_len - fill)

    # Per-pair tally
    raw = defaultdict(lambda: {"a": 0, "b": 0, "d": 0, "n": 0})
    for g in games:
        a, b = g["side_a"], g["side_b"]
        # Canonicalize
        x, y = (a, b) if a < b else (b, a)
        key = (x, y)
        raw[key]["n"] += 1
        if g["winner"] == "a":
            raw[key]["a" if a == x else "b"] += 1
        elif g["winner"] == "b":
            raw[key]["a" if b == x else "b"] += 1
        else:
            raw[key]["d"] += 1

    lines = [f"MATRIX : {n}/{target} games  [{bar}] {pct:.1f}%"]
    for (x, y), v in sorted(raw.items()):
        lines.append(f"  {x:<6} {v['a']:>3} - {v['b']:<3} {y:<6}  ({v['d']}D, {v['n']}g)")
    return "\n".join(lines)


def bracket_section(games: list[dict]) -> str:
    if not games:
        return "BRACKET : pas démarré"

    groups = defaultdict(list)
    for g in games:
        groups[g.get("mirror", "")].append(g)

    # Determine current state
    semi1 = groups.get("semi1_a", []) + groups.get("semi1_b", [])
    semi2 = groups.get("semi2_a", []) + groups.get("semi2_b", [])
    final = groups.get("final_a", []) + groups.get("final_b", [])
    boss  = groups.get("boss", [])

    target_semi  = 200  # 50 × 2 mirrors × 2 seeds
    target_final = 200
    target_boss  = 200  # 100 × 2 seeds

    s1_t = tally(semi1)
    s2_t = tally(semi2)
    f_t  = tally(final)
    b_t  = tally(boss)

    def winner(t: dict) -> tuple[str, int, str, int]:
        items = sorted(t.items(), key=lambda kv: -kv[1])
        if not items:
            return ("?", 0, "?", 0)
        if len(items) == 1:
            return (items[0][0], items[0][1], "?", 0)
        return (items[0][0], items[0][1], items[1][0], items[1][1])

    s1_w, s1_wc, s1_l, s1_lc = winner(s1_t)
    s2_w, s2_wc, s2_l, s2_lc = winner(s2_t)
    f_w,  f_wc,  f_l,  f_lc  = winner(f_t)
    b_w,  b_wc,  b_l,  b_lc  = winner(b_t)

    s1_pct = len(semi1) / target_semi * 100
    s2_pct = len(semi2) / target_semi * 100
    f_pct  = len(final) / target_final * 100
    b_pct  = len(boss)  / target_boss * 100

    def bar(pct):
        bar_len = 20
        fill = int(bar_len * min(1.0, pct / 100))
        return "█" * fill + "░" * (bar_len - fill)

    def status(round_games, target):
        if round_games == 0:
            return "⏳ pas démarré"
        if round_games < target:
            return f"🟢 en cours ({round_games}/{target})"
        return f"✅ terminé ({round_games}/{target})"

    lines = ["BRACKET PLAYOFF :"]
    lines.append(f"  Semi 1 : {status(len(semi1), target_semi)}  [{bar(s1_pct)}]")
    if s1_w != "?":
        lines.append(f"           {s1_w} {s1_wc:>3}-{s1_lc:<3} {s1_l}")
    lines.append(f"  Semi 2 : {status(len(semi2), target_semi)}  [{bar(s2_pct)}]")
    if s2_w != "?":
        lines.append(f"           {s2_w} {s2_wc:>3}-{s2_lc:<3} {s2_l}")
    lines.append(f"  Finale : {status(len(final), target_final)}  [{bar(f_pct)}]")
    if f_w != "?":
        lines.append(f"           {f_w} {f_wc:>3}-{f_lc:<3} {f_l}")
    lines.append(f"  Boss   : {status(len(boss), target_boss)}  [{bar(b_pct)}]")
    if b_w != "?":
        lines.append(f"           {b_w} {b_wc:>3}-{b_lc:<3} {b_l}")

    # Current tree (partial OK)
    lines.append("")
    lines.append("ARBRE LIVE :")

    def label(name, count, target):
        if count == 0:
            return "⏳"
        if count >= target:
            return "✅"
        return f"{count}/{target}"

    s1_label = label("", len(semi1), target_semi)
    s2_label = label("", len(semi2), target_semi)
    f_label  = label("", len(final), target_final)
    b_label  = label("", len(boss),  target_boss)

    s1_score = f"{s1_wc}-{s1_lc}" if s1_w != "?" else "?-?"
    s2_score = f"{s2_wc}-{s2_lc}" if s2_w != "?" else "?-?"
    f_score  = f"{f_wc}-{f_lc}"   if f_w  != "?" else "?-?"
    b_score  = f"{b_wc}-{b_lc}"   if b_w  != "?" else "?-?"

    s1_top = semi1[0]["side_a"] if semi1 else "?"
    s1_bot = semi1[0]["side_b"] if semi1 else "?"
    s2_top = semi2[0]["side_a"] if semi2 else "?"
    s2_bot = semi2[0]["side_b"] if semi2 else "?"

    lines.append(f"  {s1_top:<6} ─┐")
    lines.append(f"           ├─ {s1_w:<6} {s1_score:>6} {s1_label} ─┐")
    lines.append(f"  {s1_bot:<6} ─┘                       │")
    lines.append(f"                                ├─ {f_w:<6} {f_score:>6} {f_label} ─→ vs greedy {b_score} {b_label}")
    lines.append(f"  {s2_top:<6} ─┐                       │")
    lines.append(f"           ├─ {s2_w:<6} {s2_score:>6} {s2_label} ─┘")
    lines.append(f"  {s2_bot:<6} ─┘")

    if b_w != "?" and len(boss) >= target_boss:
        if b_w == f_w:
            lines.append(f"\n  🏆 CHAMPION : {f_w}  (bat greedy {b_wc}-{b_lc})")
        else:
            lines.append(f"\n  ❌ {f_w} battu par greedy ({b_lc}-{b_wc})")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("usage: watch_bracket_helper.py <run_dir>")
        sys.exit(1)

    run_dir = Path(sys.argv[1])
    matrix_path  = run_dir / "matrix.jsonl"
    bracket_path = run_dir / "bracket.jsonl"

    matrix_games  = load_games(matrix_path)
    bracket_games = load_games(bracket_path)

    print(matrix_section(matrix_games))
    print()
    print(bracket_section(bracket_games))


if __name__ == "__main__":
    main()
