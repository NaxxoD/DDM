"""Watcher live pour llm_matrix.py (mode both : group + playoff).

Lit le JSONL unique avec phase='group' ou 'playoff', affiche :
  - progression group stage + classement live
  - bracket playoff partiel (QF / SF / F) avec scores
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_POOL_SIZE = 11  # 11 LLMs → C(11,2)=55 paires

ROOT      = Path(__file__).resolve().parents[2]
PREFS_DIR = ROOT / "data"

# Court alias pour faction full → display tag
FACTION_TAGS = {
    1: "Humains", 2: "Egypte", 3: "Reptiliens", 4: "Cyborgs",
    5: "Orcs", 6: "Lycans", 7: "Demons", 8: "Abominations",
}


def load_combo(profile: str) -> str:
    """Retourne 'f6+A' depuis data/{profile}_prefs.json, ou 'rand' si absent."""
    fp = PREFS_DIR / f"{profile}_prefs.json"
    if not fp.exists():
        return "rand"
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        p = data.get("preferred") or {}
        f, c = p.get("faction"), p.get("champion")
        if f is None or c is None:
            return "rand"
        return f"f{f}+{c}"
    except Exception:
        return "rand"


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line.strip())
                if r.get("event") == "game_end":
                    out.append(r)
            except (json.JSONDecodeError, ValueError):
                pass
    return out


def section_group(games: list[dict], expected: int) -> str:
    if not games:
        return "GROUP STAGE : 0 games"

    n = len(games)
    pct = (n / expected * 100) if expected else 0
    bar_len = 50
    fill = int(bar_len * min(1.0, n / max(expected, 1)))
    bar  = "█" * fill + "░" * (bar_len - fill)

    stats = defaultdict(lambda: {"w": 0, "d": 0, "l": 0, "n": 0})
    for g in games:
        sa, sb, w = g["side_a"], g["side_b"], g["winner"]
        stats[sa]["n"] += 1
        stats[sb]["n"] += 1
        if w == "a":
            stats[sa]["w"] += 1; stats[sb]["l"] += 1
        elif w == "b":
            stats[sb]["w"] += 1; stats[sa]["l"] += 1
        else:
            stats[sa]["d"] += 1; stats[sb]["d"] += 1

    ranking = []
    for k, v in stats.items():
        if v["n"] == 0:
            continue
        wr = (v["w"] + 0.5 * v["d"]) / v["n"]
        ranking.append((k, v, wr))
    ranking.sort(key=lambda kv: -kv[2])

    lines = [f"GROUP STAGE : {n}/{expected} games  [{bar}] {pct:.1f}%", ""]
    lines.append("  CLASSEMENT LIVE")
    lines.append("  " + "-" * 60)
    for i, (name, v, wr) in enumerate(ranking, 1):
        marker = "🏆" if i == 1 else ("🟢" if i <= 8 else "  ")
        combo = load_combo(name)
        lines.append(f"  {marker} {i:>2}. {name:<10} [{combo:<6}] WR {wr*100:5.1f}%  "
                     f"{v['w']:>3}W {v['d']:>3}D {v['l']:>3}L  ({v['n']:>3}g)")
    return "\n".join(lines)


def section_playoff(games: list[dict]) -> str:
    if not games:
        return "PLAYOFF : pas démarré (en attente fin du group stage)"

    by_match = defaultdict(list)
    for g in games:
        key = (g.get("round"), g.get("match_id"))
        by_match[key].append(g)

    def match_summary(records: list[dict]) -> tuple[str, str, int, int]:
        wins = defaultdict(int)
        sa, sb = records[0]["side_a"], records[0]["side_b"]
        canon_a, canon_b = sorted([sa, sb])
        for r in records:
            w = r["winner"]
            if w == "a":
                wins[r["side_a"]] += 1
            elif w == "b":
                wins[r["side_b"]] += 1
        return canon_a, canon_b, wins[canon_a], wins[canon_b]

    lines = ["PLAYOFF BRACKET", ""]
    for round_name in ("QF", "SF", "F"):
        match_ids = sorted([k[1] for k in by_match if k[0] == round_name])
        if not match_ids:
            lines.append(f"  {round_name:<3} : ⏳ pas démarré")
            continue
        lines.append(f"  {round_name}")
        for mid in match_ids:
            recs = by_match[(round_name, mid)]
            ca, cb, wa, wb = match_summary(recs)
            n = len(recs)
            lead = ca if wa > wb else (cb if wb > wa else "?")
            star = "🏆" if (round_name == "F" and n >= 5 and wa != wb) else "  "
            lines.append(f"    {star}M{mid}  {ca:>9} {wa}-{wb} {cb:<9}  ({n}g)  lead={lead}")
        lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("usage: watch_llm_tournament.py <jsonl_path> [expected_group_games]")
        sys.exit(1)

    jsonl_path = Path(sys.argv[1])
    expected   = int(sys.argv[2]) if len(sys.argv) > 2 else 1100

    games = load(jsonl_path)
    group    = [g for g in games if g.get("phase", "group") == "group"]
    playoff  = [g for g in games if g.get("phase") == "playoff"]

    print(section_group(group, expected))
    print()
    print(section_playoff(playoff))


if __name__ == "__main__":
    main()
