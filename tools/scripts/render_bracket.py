"""Render bracket results from one or more JSONL streams.

Aggregates per-game records produced by rl/bracket.py and outputs:
  - WR matrix (4×4 H2H)
  - Final ranking by mean WR
  - ASCII playoff tree (semi/final/boss)
  - Elo ratings (start 1500, K=32)
  - Draft identities per agent (top factions, top champions, top combos)
  - Killers detected (dominant micro-matchups)

Usage:
    python tools/scripts/render_bracket.py --jsonl reports/bracket/run_001/matrix.jsonl
    python tools/scripts/render_bracket.py --jsonl reports/bracket/run_001/*.jsonl --out reports/Report/bracket_001.md
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

AGENTS = ["jin", "jio", "cross", "jaeha", "neosia"]


def load_games(paths: list[Path]) -> list[dict]:
    games = []
    for p in paths:
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
    return games


# ── Aggregations ──────────────────────────────────────────────────────────────

def h2h_matrix(games: list[dict]) -> dict[tuple[str, str], dict]:
    """Returns {(a, b): {wins_a, wins_b, draws, games}} aggregated over mirrors+seeds.

    Mirror handling: when mirror="b", side_a/side_b are already swapped by the
    bracket runner — we DON'T re-swap; we just accumulate per (side_a, side_b).
    For the final symmetric matrix we then merge (a,b) and (b,a) entries.
    """
    raw = defaultdict(lambda: {"wins_a": 0, "wins_b": 0, "draws": 0, "games": 0})
    for g in games:
        a, b = g.get("side_a"), g.get("side_b")
        if a is None or b is None or b == "greedy":
            continue
        key = (a, b)
        raw[key]["games"] += 1
        if g["winner"] == "a":
            raw[key]["wins_a"] += 1
        elif g["winner"] == "b":
            raw[key]["wins_b"] += 1
        else:
            raw[key]["draws"] += 1

    # Merge symmetric pairs into canonical (alphabetical) key, swapping wins as needed.
    merged = defaultdict(lambda: {"wins_x": 0, "wins_y": 0, "draws": 0, "games": 0})
    for (a, b), v in raw.items():
        if a < b:
            x, y = a, b
            merged[(x, y)]["wins_x"] += v["wins_a"]
            merged[(x, y)]["wins_y"] += v["wins_b"]
        else:
            x, y = b, a
            merged[(x, y)]["wins_x"] += v["wins_b"]
            merged[(x, y)]["wins_y"] += v["wins_a"]
        merged[(x, y)]["draws"] += v["draws"]
        merged[(x, y)]["games"] += v["games"]
    return dict(merged)


def render_h2h(matrix: dict[tuple[str, str], dict], agents: list[str]) -> str:
    lines = ["MATRICE WR H2H (lignes vs colonnes)"]
    header = "         " + "  ".join(f"{a[:6]:>6}" for a in agents)
    lines.append(header)
    for a in agents:
        cells = []
        for b in agents:
            if a == b:
                cells.append(f"{'----':>6}")
                continue
            x, y = (a, b) if a < b else (b, a)
            v = matrix.get((x, y))
            if not v or v["games"] == 0:
                cells.append(f"{'?':>6}")
                continue
            wa = v["wins_x"] if a == x else v["wins_y"]
            wb = v["wins_y"] if a == x else v["wins_x"]
            wr = (wa + 0.5 * v["draws"]) / v["games"]
            cells.append(f"{wr*100:>5.1f}%")
        lines.append(f"{a[:7]:<7}  " + "  ".join(cells))
    return "\n".join(lines)


def ranking(matrix: dict, agents: list[str]) -> list[tuple[str, float, int, int]]:
    """Returns [(agent, mean_wr, total_wins, total_games)] sorted by mean WR desc."""
    rows = []
    for a in agents:
        wrs = []
        wt = gt = 0
        for b in agents:
            if a == b:
                continue
            x, y = (a, b) if a < b else (b, a)
            v = matrix.get((x, y))
            if not v or v["games"] == 0:
                continue
            wa = v["wins_x"] if a == x else v["wins_y"]
            wr = (wa + 0.5 * v["draws"]) / v["games"]
            wrs.append(wr)
            wt += wa; gt += v["games"]
        mean = sum(wrs) / len(wrs) if wrs else 0.0
        rows.append((a, mean, wt, gt))
    rows.sort(key=lambda r: -r[1])
    return rows


# ── Elo ────────────────────────────────────────────────────────────────────────

def elo_ratings(games: list[dict], start: float = 1500.0, k: float = 32.0) -> dict:
    rating = {a: start for a in AGENTS + ["greedy"]}
    for g in games:
        a, b = g.get("side_a"), g.get("side_b")
        if a not in rating or b not in rating:
            continue
        ra, rb = rating[a], rating[b]
        ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400))
        if g["winner"] == "a":
            sa = 1.0
        elif g["winner"] == "b":
            sa = 0.0
        else:
            sa = 0.5
        delta = k * (sa - ea)
        rating[a] = ra + delta
        rating[b] = rb - delta
    return rating


# ── Draft / faction / champion stats ─────────────────────────────────────────

def draft_stats(games: list[dict]) -> dict[str, dict]:
    """Returns {agent: {factions: Counter, champions: Counter, combos: {key: {games, wins}}}}."""
    out = {a: {"factions": defaultdict(int),
               "champions": defaultdict(int),
               "combos": defaultdict(lambda: {"games": 0, "wins": 0}),
               "games": 0,
               "wins": 0}
           for a in AGENTS + ["greedy"]}

    for g in games:
        a, b = g.get("side_a"), g.get("side_b")
        if a not in out or b not in out:
            continue
        for who, side in (("a", a), ("b", b)):
            f = g.get(f"faction_{who}")
            ch = g.get(f"champion_{who}")
            if f is None or ch is None:
                continue
            agent_won = (g["winner"] == who)
            out[side]["factions"][f] += 1
            out[side]["champions"][ch] += 1
            out[side]["combos"][(f, ch)]["games"] += 1
            if agent_won:
                out[side]["combos"][(f, ch)]["wins"] += 1
                out[side]["wins"] += 1
            out[side]["games"] += 1
    return out


def render_draft(stats: dict, top_n: int = 3) -> str:
    lines = ["DRAFT IDENTITIES (top picks par agent, agrégé sur tout le bracket)"]
    for a in AGENTS:
        s = stats.get(a, {})
        n = s.get("games", 0)
        if n == 0:
            continue
        lines.append(f"\n{a.upper()}  ({n} games)")
        # factions
        top_f = sorted(s["factions"].items(), key=lambda kv: -kv[1])[:top_n]
        f_str = "  ".join(f"f{f} ({c}× / {c/n*100:.0f}%)" for f, c in top_f)
        lines.append(f"  Factions  : {f_str}")
        # champions
        top_c = sorted(s["champions"].items(), key=lambda kv: -kv[1])[:top_n]
        c_str = "  ".join(f"{ch} ({c}× / {c/n*100:.0f}%)" for ch, c in top_c)
        lines.append(f"  Champions : {c_str}")
        # combos
        combos = sorted(s["combos"].items(),
                        key=lambda kv: (-kv[1]["games"], -kv[1]["wins"]))[:top_n]
        for (f, ch), v in combos:
            wr = v["wins"] / v["games"] if v["games"] else 0.0
            lines.append(f"  Combo top : f{f}+{ch}  {v['games']}× → WR {wr*100:.1f}%  ({v['wins']}/{v['games']})")
    return "\n".join(lines)


def render_killers(games: list[dict], min_games: int = 8, threshold: float = 0.65) -> str:
    """Find combo×combo matchups where one side dominates."""
    matchup = defaultdict(lambda: {"games": 0, "wins_a": 0, "draws": 0})
    for g in games:
        a, b = g.get("side_a"), g.get("side_b")
        if a not in AGENTS or b not in AGENTS:
            continue
        fa, ca = g.get("faction_a"), g.get("champion_a")
        fb, cb = g.get("faction_b"), g.get("champion_b")
        if None in (fa, ca, fb, cb):
            continue
        key = (a, fa, ca, b, fb, cb)
        matchup[key]["games"] += 1
        if g["winner"] == "a":
            matchup[key]["wins_a"] += 1
        elif g["winner"] == "draw":
            matchup[key]["draws"] += 1

    rows = []
    for (a, fa, ca, b, fb, cb), v in matchup.items():
        if v["games"] < min_games:
            continue
        wr = (v["wins_a"] + 0.5 * v["draws"]) / v["games"]
        if wr >= threshold or wr <= (1 - threshold):
            rows.append((a, fa, ca, b, fb, cb, wr, v["games"]))
    rows.sort(key=lambda r: -abs(r[6] - 0.5))

    if not rows:
        return "KILLERS DETECTED : aucun matchup dominant détecté (seuil non atteint)."
    lines = [f"KILLERS DETECTED (>{threshold*100:.0f}% sur ≥{min_games} games)"]
    for a, fa, ca, b, fb, cb, wr, n in rows[:15]:
        side = "↑" if wr > 0.5 else "↓"
        lines.append(f"  {a} f{fa}+{ca} vs {b} f{fb}+{cb}  {side} WR {wr*100:.1f}%  ({n}g)")
    return "\n".join(lines)


# ── Bracket tree ASCII ────────────────────────────────────────────────────────

def render_tree(games: list[dict], seeding: list[str] | None = None) -> str:
    """If JSONL contains mirror tags 'semi1_*', 'semi2_*', 'final_*', 'boss',
    render a playoff tree from those. Otherwise produce an inferred tree
    from the matrix ranking."""
    semi1 = [g for g in games if g.get("mirror", "").startswith("semi1")]
    semi2 = [g for g in games if g.get("mirror", "").startswith("semi2")]
    final = [g for g in games if g.get("mirror", "").startswith("final")]
    # Bosses : ancien format ("boss") + nouveau format ("boss1_<name>", "boss2_<name>", ...)
    boss_groups: list[tuple[str, list[dict]]] = []
    boss_old = [g for g in games if g.get("mirror") == "boss"]
    if boss_old:
        boss_groups.append(("boss", boss_old))
    # Détecte les bosses séquentiels et préserve leur ordre (boss1 → boss2 → ...)
    boss_indices = sorted({g.get("mirror","").split("_")[0]
                           for g in games
                           if g.get("mirror","").startswith("boss") and g.get("mirror") != "boss"})
    for boss_idx in boss_indices:
        # Récupère le nom du boss depuis le mirror tag (ex: boss1_greedy_a → greedy)
        bg = [g for g in games if g.get("mirror","").startswith(f"{boss_idx}_")]
        if bg:
            # Determine boss agent name (whoever isn't the champion in side_a/side_b)
            sample_mirror = bg[0]["mirror"]  # ex: boss1_greedy_a
            parts = sample_mirror.split("_")
            boss_name = parts[1] if len(parts) >= 2 else "?"
            boss_groups.append((boss_name, bg))
    boss = boss_old  # gardé pour compatibilité avec le code aval

    def winner_of(group):
        wa = sum(1 for g in group if g["winner"] == "a")
        wb = sum(1 for g in group if g["winner"] == "b")
        if not group:
            return None, None, None, 0
        side_a = group[0]["side_a"]; side_b = group[0]["side_b"]
        # Note: side_a/side_b are constant per match in semi*_a, but in semi*_b they're swapped.
        # Re-aggregate properly to canonical agent names.
        return side_a if wa >= wb else side_b, max(wa, wb), min(wa, wb), wa + wb

    if not (semi1 and semi2 and final):
        # No bracket data (only matrix) → infer ranking-style tree
        matrix = h2h_matrix(games)
        rk = ranking(matrix, AGENTS)
        if not rk:
            return "(pas de données pour l'arbre)"
        seeds = [r[0] for r in rk]
        # Infer hypothetical bracket from ranking
        s1, s2, s3, s4 = seeds + [None] * max(0, 4 - len(seeds))
        return (
            f"ARBRE HYPOTHÉTIQUE (basé sur ranking matrix, pas sur des matchs joués)\n"
            f"\n"
            f"  ({1}) {s1:<6} ─┐\n"
            f"               ├─ ?\n"
            f"  ({4}) {s4:<6} ─┘\n"
            f"  ({2}) {s2:<6} ─┐\n"
            f"               ├─ ?\n"
            f"  ({3}) {s3:<6} ─┘"
        )

    # Real bracket: compute proper winners using mirror-aware tally
    def tally(group):
        wins = defaultdict(int)
        for g in group:
            wins[g["side_a"] if g["winner"] == "a" else g["side_b"] if g["winner"] == "b" else "draw"] += 1
        return wins

    s1_t = tally(semi1); s2_t = tally(semi2); fin_t = tally(final); bos_t = tally(boss)

    def best_of(t):
        items = [(k, v) for k, v in t.items() if k != "draw"]
        items.sort(key=lambda kv: -kv[1])
        return items

    s1_rk = best_of(s1_t); s2_rk = best_of(s2_t); fin_rk = best_of(fin_t); bos_rk = best_of(bos_t)
    s1_winner = s1_rk[0][0] if s1_rk else "?"
    s2_winner = s2_rk[0][0] if s2_rk else "?"
    fin_winner = fin_rk[0][0] if fin_rk else "?"

    s1_a = semi1[0]["side_a"] if semi1 else "?"
    s1_b = semi1[0]["side_b"] if semi1 else "?"
    s2_a = semi2[0]["side_a"] if semi2 else "?"
    s2_b = semi2[0]["side_b"] if semi2 else "?"

    s1_score = f"{s1_rk[0][1]}-{s1_rk[1][1] if len(s1_rk) > 1 else 0}" if s1_rk else "?"
    s2_score = f"{s2_rk[0][1]}-{s2_rk[1][1] if len(s2_rk) > 1 else 0}" if s2_rk else "?"
    fin_score = f"{fin_rk[0][1]}-{fin_rk[1][1] if len(fin_rk) > 1 else 0}" if fin_rk else "?"

    # Construction des lignes bosses séquentiels
    current_champion = fin_winner
    boss_lines = []
    for boss_name, boss_games in boss_groups:
        b_t = tally(boss_games)
        b_rk = best_of(b_t)
        if not b_rk:
            boss_lines.append(f"  vs {boss_name:<7} : (pas joué)")
            continue
        winner = b_rk[0][0]
        loser  = b_rk[1][0] if len(b_rk) > 1 else "?"
        ws, ls = b_rk[0][1], (b_rk[1][1] if len(b_rk) > 1 else 0)
        if winner == current_champion:
            boss_lines.append(f"  vs {boss_name:<7} : {current_champion} {ws}-{ls} {boss_name}  ✅")
        else:
            boss_lines.append(f"  vs {boss_name:<7} : {boss_name} {ws}-{ls} {current_champion}  ❌ (champion battu)")
            current_champion = winner

    return (
        f"ARBRE PLAYOFF\n\n"
        f"  DEMI-FINALES               FINALE             BOSSES\n\n"
        f"  {s1_a:<6} ─┐\n"
        f"           ├─ {s1_winner:<6} {s1_score:>6} ─┐\n"
        f"  {s1_b:<6} ─┘                         │\n"
        f"                                ├─ {fin_winner:<6} {fin_score:>6}\n"
        f"  {s2_a:<6} ─┐                         │\n"
        f"           ├─ {s2_winner:<6} {s2_score:>6} ─┘\n"
        f"  {s2_b:<6} ─┘\n"
        f"\n"
        + ("\n".join(boss_lines) + "\n\n" if boss_lines else "")
        + f"  CHAMPION FINAL : {current_champion}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", nargs="+", required=True,
                    help="One or more JSONL files (globs OK)")
    ap.add_argument("--out", default=None,
                    help="Path to write the rendered report. Default: stdout only.")
    ap.add_argument("--killers-min-games", type=int, default=8)
    ap.add_argument("--killers-threshold", type=float, default=0.65)
    args = ap.parse_args()

    paths: list[Path] = []
    for pat in args.jsonl:
        paths.extend(Path(p) for p in glob.glob(pat))
    if not paths:
        print(f"[ERREUR] Aucun fichier trouvé pour {args.jsonl}", file=sys.stderr)
        sys.exit(1)

    games = load_games(paths)
    print(f"[render] {len(games)} games chargés depuis {len(paths)} fichier(s)")
    if not games:
        sys.exit(0)

    sections = []

    # 1. Tree (if bracket data) or hypothetical
    sections.append(render_tree(games))

    # 2. H2H matrix
    matrix = h2h_matrix(games)
    sections.append(render_h2h(matrix, AGENTS))

    # 3. Ranking
    rk = ranking(matrix, AGENTS)
    rk_lines = ["CLASSEMENT (WR moyen sur autres agents)"]
    for i, (a, mean, wt, gt) in enumerate(rk, 1):
        rk_lines.append(f"  {i}. {a:<6}  WR moy {mean*100:5.1f}%   total {wt}/{gt}")
    sections.append("\n".join(rk_lines))

    # 4. Elo
    elo = elo_ratings(games)
    elo_rows = sorted([(a, r) for a, r in elo.items() if a in AGENTS + ["greedy"]],
                      key=lambda kv: -kv[1])
    elo_lines = ["ELO RATINGS (start 1500, K=32, ordre des matchs = ordre du JSONL)"]
    for a, r in elo_rows:
        delta = r - 1500
        elo_lines.append(f"  {a:<7}  {r:7.1f}  ({delta:+.1f})")
    sections.append("\n".join(elo_lines))

    # 5. Draft identities
    sections.append(render_draft(draft_stats(games)))

    # 6. Killers
    sections.append(render_killers(games, args.killers_min_games, args.killers_threshold))

    report = "\n\n" + "\n\n".join(sections) + "\n"
    print(report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\n[OK] Report écrit : {out}")


if __name__ == "__main__":
    main()
