"""Compare two bracket runs (pre vs post migration, or any 2 runs).

Usage:
    python tools/scripts/compare_brackets.py --pre run_quick --post post_migr_blind
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ["jin", "jio", "cross", "jaeha"]


def load_run(name: str) -> dict:
    base = ROOT / "reports" / "bracket" / name
    games = []
    for kind in ("matrix", "bracket"):
        p = base / f"{kind}.jsonl"
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("event") == "game_end":
                    games.append(rec)
    return {"games": games, "name": name}


def h2h_wr(games: list[dict]) -> dict[tuple[str, str], float]:
    raw = defaultdict(lambda: {"wins_x": 0, "draws": 0, "games": 0})
    for g in games:
        a, b = g.get("side_a"), g.get("side_b")
        if a not in AGENTS or b not in AGENTS:
            continue
        x, y = (a, b) if a < b else (b, a)
        raw[(x, y)]["games"] += 1
        if g["winner"] == "draw":
            raw[(x, y)]["draws"] += 1
        else:
            winner = a if g["winner"] == "a" else b
            if winner == x:
                raw[(x, y)]["wins_x"] += 1
    out = {}
    for (x, y), v in raw.items():
        if v["games"]:
            out[(x, y)] = (v["wins_x"] + 0.5 * v["draws"]) / v["games"]
    return out


def mean_wr(games: list[dict]) -> dict[str, float]:
    raw = defaultdict(lambda: {"wins": 0, "games": 0})
    for g in games:
        a, b = g.get("side_a"), g.get("side_b")
        if a not in AGENTS or b not in AGENTS:
            continue
        for who, agent in (("a", a), ("b", b)):
            raw[agent]["games"] += 1
            if g["winner"] == who:
                raw[agent]["wins"] += 1
            elif g["winner"] == "draw":
                raw[agent]["wins"] += 0.5
    return {a: v["wins"] / v["games"] for a, v in raw.items() if v["games"]}


def boss_wr(games: list[dict]) -> dict[str, float]:
    raw = defaultdict(lambda: {"wins": 0, "games": 0})
    for g in games:
        if g.get("mirror") != "boss":
            continue
        a, b = g.get("side_a"), g.get("side_b")
        if a in AGENTS and b == "greedy":
            raw[a]["games"] += 1
            if g["winner"] == "a":
                raw[a]["wins"] += 1
            elif g["winner"] == "draw":
                raw[a]["wins"] += 0.5
        elif b in AGENTS and a == "greedy":
            raw[b]["games"] += 1
            if g["winner"] == "b":
                raw[b]["wins"] += 1
            elif g["winner"] == "draw":
                raw[b]["wins"] += 0.5
    return {a: v["wins"] / v["games"] for a, v in raw.items() if v["games"]}


def champion(games: list[dict]) -> str | None:
    boss = [g for g in games if g.get("mirror") == "boss"]
    if not boss:
        return None
    side_a = boss[0].get("side_a")
    side_b = boss[0].get("side_b")
    rl = side_a if side_a != "greedy" else side_b
    return rl


def fmt_delta(d: float) -> str:
    sign = "+" if d > 0 else ""
    return f"{sign}{d * 100:5.2f}pts"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre",  default="run_quick")
    ap.add_argument("--post", default="post_migr_blind")
    ap.add_argument("--out",  default=None)
    args = ap.parse_args()

    pre  = load_run(args.pre)
    post = load_run(args.post)
    print(f"PRE  : {args.pre:<20}  {len(pre['games'])} games")
    print(f"POST : {args.post:<20}  {len(post['games'])} games")
    print()

    sections = []

    # --- Section 1 : champions
    c_pre  = champion(pre["games"])
    c_post = champion(post["games"])
    sections.append(
        f"=== CHAMPIONS ===\n"
        f"  PRE  : {c_pre or '?'}\n"
        f"  POST : {c_post or '?'}\n"
        f"  → {'IDENTIQUE' if c_pre == c_post else 'CHANGÉ'}"
    )

    # --- Section 2 : WR moyen par agent (mean over all opponents)
    pre_wr  = mean_wr(pre["games"])
    post_wr = mean_wr(post["games"])
    lines = ["=== WR MOYEN PAR AGENT (sur tous adversaires RL) ===",
             f"{'Agent':<8} {'PRE':>8}  {'POST':>8}  {'Δ':>10}"]
    for a in AGENTS:
        wp = pre_wr.get(a, 0.0)
        wq = post_wr.get(a, 0.0)
        d = wq - wp
        lines.append(f"{a:<8} {wp*100:>7.2f}%  {wq*100:>7.2f}%   {fmt_delta(d):>10}")
    sections.append("\n".join(lines))

    # --- Section 3 : H2H WR par pair
    pre_h2h  = h2h_wr(pre["games"])
    post_h2h = h2h_wr(post["games"])
    lines = ["=== H2H WR PAR PAIR (côté gauche du pair) ===",
             f"{'Pair':<18} {'PRE':>8}  {'POST':>8}  {'Δ':>10}"]
    for pair in sorted(set(pre_h2h) | set(post_h2h)):
        x, y = pair
        wp = pre_h2h.get(pair, 0.0)
        wq = post_h2h.get(pair, 0.0)
        d = wq - wp
        lines.append(f"{x} vs {y:<10} {wp*100:>7.2f}%  {wq*100:>7.2f}%   {fmt_delta(d):>10}")
    sections.append("\n".join(lines))

    # --- Section 4 : boss greedy WR
    pre_boss  = boss_wr(pre["games"])
    post_boss = boss_wr(post["games"])
    lines = ["=== WR vs GREEDY (boss) ==="]
    for a in AGENTS:
        if a in pre_boss or a in post_boss:
            wp = pre_boss.get(a, None)
            wq = post_boss.get(a, None)
            wp_str = f"{wp*100:.2f}%" if wp is not None else "—"
            wq_str = f"{wq*100:.2f}%" if wq is not None else "—"
            d_str = f"   {fmt_delta(wq-wp):>10}" if wp is not None and wq is not None else ""
            lines.append(f"  {a:<8} PRE: {wp_str:<8} POST: {wq_str:<8}{d_str}")
    sections.append("\n".join(lines))

    # --- Section 5 : Verdict synthétique
    deltas = []
    for a in AGENTS:
        wp = pre_wr.get(a, 0.0)
        wq = post_wr.get(a, 0.0)
        deltas.append((a, wq - wp))
    biggest_loss  = min(deltas, key=lambda kv: kv[1])
    biggest_gain  = max(deltas, key=lambda kv: kv[1])
    avg = sum(abs(d) for _, d in deltas) / len(deltas)

    verdict = []
    verdict.append("=== VERDICT ENGINE FIX ===")
    verdict.append(f"  Δ WR moyen absolu  : {avg*100:.2f} pts")
    verdict.append(f"  Plus grosse perte  : {biggest_loss[0]} ({biggest_loss[1]*100:+.2f} pts)")
    verdict.append(f"  Plus gros gain     : {biggest_gain[0]} ({biggest_gain[1]*100:+.2f} pts)")
    verdict.append(f"  Champion           : {'identique' if c_pre == c_post else 'changé'}")

    if avg < 0.03:
        verdict.append("  → IMPACT FAIBLE (< 3 pts en moyenne) : retraining peut être skip")
    elif avg < 0.07:
        verdict.append("  → IMPACT MODÉRÉ : retraining recommandé pour fine-tuning")
    else:
        verdict.append("  → IMPACT FORT (> 7 pts) : retraining nécessaire")
    sections.append("\n".join(verdict))

    report = "\n\n".join(sections) + "\n"
    print(report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\n[OK] Report écrit : {out}")


if __name__ == "__main__":
    main()
