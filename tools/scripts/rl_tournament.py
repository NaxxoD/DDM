"""Tournoi RL agents : group stage round-robin + playoff bracket top-4.

Mode "matrix"  : round-robin toutes paires
Mode "bracket" : suppose matrix existant -> playoff seedé sur top 4
Mode "both"    : matrix puis playoff direct (défaut)

Pool par défaut : jin, jio, cross, jaeha, neosia (5 agents -> 10 paires)

Records JSONL (compatible avec watch_llm_tournament.py) :
    {"event": "game_end", "phase": "group"|"playoff",
     "side_a": "jio", "side_b": "neosia", "winner": "a"|"b"|"draw",
     "round": "SF"|"F"|null, "match_id": int|null, ...}
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rl.bracket import run_pair, AGENT_CKPT  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_POOL = ["jin", "jio", "cross", "jaeha", "neosia"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _append_with_phase(src: Path, dst: Path, phase: str, **extra) -> None:
    """Lit le jsonl écrit par run_pair, ajoute phase + champs extra, append à dst."""
    if not src.exists():
        return
    with src.open(encoding="utf-8") as f, dst.open("a", encoding="utf-8") as g:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") != "game_end":
                continue
            rec["phase"] = phase
            rec.update(extra)
            g.write(json.dumps(rec, ensure_ascii=False) + "\n")
    src.unlink(missing_ok=True)


def _run_pair_phase(side_a: str, side_b: str, games: int, seed: int,
                    consolidated: Path, phase: str, mirror: str = "a",
                    combos: dict | None = None,
                    **extra) -> None:
    """Wrapper run_pair qui écrit dans un tmp puis copie avec phase tagging."""
    fa = ca = fb = cb = None
    if combos:
        if side_a in combos:
            fa, ca = combos[side_a]
        if side_b in combos:
            fb, cb = combos[side_b]
    tmp = Path(tempfile.mkdtemp()) / "tmp.jsonl"
    run_pair(side_a, side_b, games, seed, tmp, mirror=mirror,
             faction_a=fa, champion_a=ca, faction_b=fb, champion_b=cb)
    _append_with_phase(tmp, consolidated, phase, **extra)


# ── Phase 1 : Group Stage ─────────────────────────────────────────────────────

def run_matrix(pool: list[str], games: int, seeds: list[int],
               out_path: Path, append: bool = False,
               combos: dict | None = None) -> None:
    pairs = list(combinations(pool, 2))
    n_per_pair = len(seeds) * 2 * games
    total      = len(pairs) * n_per_pair

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not append and out_path.exists():
        out_path.unlink()

    print(f"[group] pool={pool}")
    print(f"[group] {len(pairs)} paires x {n_per_pair} games = {total} games")
    print()

    t0 = time.time()
    done = 0
    for a, b in pairs:
        for seed in seeds:
            for mirror, (sa, sb) in enumerate([(a, b), (b, a)]):
                _run_pair_phase(sa, sb, games, seed, out_path, "group",
                                mirror="ab" if mirror == 0 else "ba",
                                combos=combos)
                done += games
                eta = (time.time() - t0) / done * (total - done) if done else 0
                print(f"[GRP {done:>4}/{total}] {sa:>8} vs {sb:<8}  "
                      f"seed={seed} mirror={'ab' if mirror==0 else 'ba'}  "
                      f"ETA {eta/60:.1f} min")
    print(f"\n[group OK] {(time.time()-t0)/60:.1f} min")


# ── Ranking ──────────────────────────────────────────────────────────────────

def compute_ranking(jsonl_path: Path) -> list[tuple[str, dict]]:
    stats: dict[str, dict] = defaultdict(lambda: {"wins": 0, "draws": 0, "n": 0})
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            if r.get("event") != "game_end" or r.get("phase", "group") != "group":
                continue
            sa, sb, w = r.get("side_a"), r.get("side_b"), r.get("winner")
            if not sa or not sb:
                continue
            stats[sa]["n"] += 1
            stats[sb]["n"] += 1
            if w == "a":
                stats[sa]["wins"] += 1
            elif w == "b":
                stats[sb]["wins"] += 1
            else:
                stats[sa]["draws"] += 1
                stats[sb]["draws"] += 1
    ranking = []
    for k, v in stats.items():
        if v["n"] == 0:
            continue
        wr = (v["wins"] + 0.5 * v["draws"]) / v["n"]
        ranking.append((k, {**v, "wr": wr}))
    ranking.sort(key=lambda kv: -kv[1]["wr"])
    return ranking


# ── Phase 2 : Playoff (top 4 -> SF + F) ───────────────────────────────────────

def run_match_series(side_a: str, side_b: str, bo_games: int, base_seed: int,
                     out_path: Path, round_name: str, match_id: int,
                     combos: dict | None = None) -> str:
    """Best-of-N entre side_a et side_b. Retourne le vainqueur."""
    # Split bo_games en 2 batches alternés (mirrors a et b)
    half = bo_games // 2
    rest = bo_games - half

    print(f"\n  [{round_name} M{match_id}] {side_a} vs {side_b} (BO{bo_games})")

    # Mirror a : side_a vs side_b
    if half > 0:
        _run_pair_phase(side_a, side_b, half, base_seed, out_path,
                        "playoff", mirror=f"{round_name}_M{match_id}_a",
                        combos=combos, round=round_name, match_id=match_id)
    # Mirror b : side_b vs side_a
    if rest > 0:
        _run_pair_phase(side_b, side_a, rest, base_seed + 1, out_path,
                        "playoff", mirror=f"{round_name}_M{match_id}_b",
                        combos=combos, round=round_name, match_id=match_id)

    # Tally
    wins = defaultdict(int)
    with out_path.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            if r.get("phase") != "playoff" or r.get("round") != round_name \
               or r.get("match_id") != match_id:
                continue
            if r["winner"] == "a":
                wins[r["side_a"]] += 1
            elif r["winner"] == "b":
                wins[r["side_b"]] += 1

    winner = side_a if wins[side_a] >= wins[side_b] else side_b
    print(f"  -> vainqueur {round_name} M{match_id} : {winner} "
          f"({wins[side_a]}-{wins[side_b]})")
    return winner


def run_bracket_top4(top4: list[str], bo_games: int,
                     base_seed: int, out_path: Path,
                     combos: dict | None = None) -> dict:
    """Seeding NBA top 4 : SF1 = 1v4, SF2 = 2v3 -> F."""
    assert len(top4) == 4
    print(f"\n[playoff] Top 4 seedés : {top4}")
    print(f"[playoff] BO{bo_games} par match")

    sf1 = run_match_series(top4[0], top4[3], bo_games, base_seed + 0,
                           out_path, "SF", 1, combos=combos)
    sf2 = run_match_series(top4[1], top4[2], bo_games, base_seed + 200,
                           out_path, "SF", 2, combos=combos)
    champ = run_match_series(sf1, sf2, bo_games, base_seed + 500,
                             out_path, "F", 1, combos=combos)
    return {"sf": [sf1, sf2], "champion": champ}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode",  choices=["matrix", "bracket", "both"], default="both")
    ap.add_argument("--pool",  default=",".join(DEFAULT_POOL))
    ap.add_argument("--games", type=int, default=25,
                    help="Group : games par mirror")
    ap.add_argument("--seeds", default="42,137")
    ap.add_argument("--playoff-games", type=int, default=20,
                    help="Best-of-N par match playoff (split a/b mirrors)")
    ap.add_argument("--out",   type=Path,
                    default=ROOT / "reports" / "bracket" / "rl_tournament" / "matrix.jsonl")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--combos-file", type=Path, default=None,
                    help="JSON file: {\"agent\": [faction_int, \"champion_str\"], ...}")
    args = ap.parse_args()

    pool  = [p.strip() for p in args.pool.split(",") if p.strip()]
    seeds = [int(s) for s in args.seeds.split(",")]

    combos: dict | None = None
    if args.combos_file:
        combos = json.loads(args.combos_file.read_text(encoding="utf-8"))
        print(f"[combos] {combos}")

    for a in pool:
        if a not in AGENT_CKPT:
            raise SystemExit(f"Agent inconnu : {a}. Dispo : {sorted(AGENT_CKPT)}")

    print(f"[mode={args.mode}] out={args.out}")
    print()

    if args.mode in ("matrix", "both"):
        run_matrix(pool, args.games, seeds, args.out, append=args.append, combos=combos)

    if args.mode in ("bracket", "both"):
        if not args.out.exists():
            print(f"[ERR] Pas de matrix data dans {args.out} — lance --mode matrix d'abord.")
            sys.exit(1)
        ranking = compute_ranking(args.out)
        if len(ranking) < 4:
            print(f"[ERR] Seulement {len(ranking)} agents classés, besoin de 4 minimum.")
            sys.exit(1)

        print("\n=== CLASSEMENT GROUP STAGE ===")
        for i, (name, s) in enumerate(ranking, 1):
            tag = "🏆" if i == 1 else ("🟢" if i <= 4 else "❌")
            print(f"  {tag} {i:>2}. {name:<10}  WR {s['wr']*100:5.1f}%  "
                  f"({s['wins']}W {s['draws']}D, {s['n']} games)")

        top4 = [r[0] for r in ranking[:4]]
        result = run_bracket_top4(top4, args.playoff_games,
                                  base_seed=99000, out_path=args.out,
                                  combos=combos)

        print("\n" + "=" * 60)
        print(f"  CHAMPION RL : {result['champion'].upper()}")
        print("=" * 60)


if __name__ == "__main__":
    main()
