"""Round-robin tournament LLM-only + optional playoff bracket.

Mode "matrix"  : round-robin toutes paires, écrit JSONL.
Mode "bracket" : suppose qu'un matrix existe déjà -> lit ranking -> joue playoff seedé.
Mode "both"    : matrix puis playoff direct sur le top 8.

Records JSONL :
    {"event": "game_end", "phase": "group"|"playoff",
     "side_a": "haiku", "side_b": "opus", "winner": "a"|"b"|"draw",
     "turns": int, "faction_a": int, "champion_a": str,
     "round": "QF"|"SF"|"F"|null, "match_id": int|null, ...}

Usage :
    python tools/scripts/llm_matrix.py --mode matrix --games 5
    python tools/scripts/llm_matrix.py --mode both   --games 5 --playoff-games 11
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[2]
PYTHON   = sys.executable
SNAPSHOT = ROOT / "engine" / "snapshots" / "latest.json"
PREFS_DIR = ROOT / "data"


EXPLORATION_RATE = 0.0  # set by main()


def load_profile_pref(profile: str) -> tuple[int | None, str | None]:
    """Lit data/{profile}_prefs.json -> (faction_id, champion_letter).
    Si EXPLORATION_RATE > 0, applique random pick à ce taux.
    Retourne (None, None) si pas de prefs (ex: greedy -> engine random)."""
    fp = PREFS_DIR / f"{profile}_prefs.json"
    if not fp.exists():
        return None, None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        p = data.get("preferred") or {}
        # Mode exploration : rare random pick d'une autre faction
        if EXPLORATION_RATE > 0:
            import random as _r
            if _r.random() < EXPLORATION_RATE:
                faction_pool = [1, 2, 3, 4, 5, 6, 7, 8]
                pref_f = p.get("faction")
                if pref_f in faction_pool:
                    faction_pool.remove(pref_f)
                f_explore = _r.choice(faction_pool)
                c_explore = _r.choice(["A", "B", "C", "D", "E"])
                return f_explore, c_explore
        return p.get("faction"), p.get("champion")
    except Exception:
        return None, None

DEFAULT_POOL = [
    "greedy", "haiku", "gemini", "chatgpt", "mistral", "grok",
    "sonnet", "opus", "deepseek", "qwen3", "glm",
]


# ── Engine call ────────────────────────────────────────────────────────────────

_RE_SUMMARY = None  # lazy compile


def run_one_game(profile_a: str, profile_b: str, seed: int, max_rounds: int = 120) -> dict:
    """Lance 1 game iaia, parse stdout pour SUMMARY_END (winner=A/B/draw)."""
    global _RE_SUMMARY
    import re
    if _RE_SUMMARY is None:
        _RE_SUMMARY = re.compile(r"SUMMARY_END\s+winner=(\S+)\s+rounds=(\d+)")

    env = os.environ.copy()
    env["DDM_AI_PROFILE_A"] = profile_a
    env["DDM_AI_PROFILE_B"] = profile_b
    env["DDM_AUTORUN"]      = "1"
    env["DDM_LOG_FAMILY"]   = "autorun"
    env["PYTHONIOENCODING"] = "utf-8"

    # Force preferred faction/champion (option 1 - no exploration)
    fa_id, ch_a = load_profile_pref(profile_a)
    fb_id, ch_b = load_profile_pref(profile_b)

    cmd = [
        PYTHON, "-m", "engine.ddm_p4_loop",
        "--mode", "iaia",
        "--seed", str(seed),
        "--bag", "11",
        "--max-rounds", str(max_rounds),
    ]
    if fa_id is not None:
        cmd += ["--faction-a", str(fa_id)]
    if ch_a:
        cmd += ["--champion-a", ch_a]
    if fb_id is not None:
        cmd += ["--faction-b", str(fb_id)]
    if ch_b:
        cmd += ["--champion-b", ch_b]
    # Stream stdout pour éviter de saturer le buffer OS (l'engine print bcp).
    # On garde la dernière ligne SUMMARY_END seulement.
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        bufsize=1, text=True, encoding="utf-8", errors="ignore",
    )
    summary_match = None
    try:
        for line in proc.stdout:
            m = _RE_SUMMARY.search(line)
            if m:
                summary_match = m
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"winner": "timeout"}

    if summary_match is None:
        return {"winner": "error", "rc": proc.returncode}

    raw_winner = summary_match.group(1).strip()
    rounds = int(summary_match.group(2))
    # Map A/B/draw/D -> "a"/"b"/"draw"
    win = {"A": "a", "B": "b", "D": "draw", "draw": "draw"}.get(raw_winner, raw_winner.lower())

    # Faction/champion depuis snapshot (peut être stale d'un game précédent en cas d'erreur,
    # mais pour iaia normal c'est OK car le snapshot final est écrit après HQ destroyed)
    fac_a = fac_b = ch_a = ch_b = None
    if SNAPSHOT.exists():
        try:
            snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            ja, jb = snap.get("joueur_A") or {}, snap.get("joueur_B") or {}
            ch_a = (ja.get("champion") or {}).get("nom") if isinstance(ja.get("champion"), dict) else ja.get("champion")
            ch_b = (jb.get("champion") or {}).get("nom") if isinstance(jb.get("champion"), dict) else jb.get("champion")
            fac_a = ja.get("faction")
            fac_b = jb.get("faction")
        except Exception:
            pass

    return {"winner": win, "turns": rounds,
            "faction_a": fac_a, "faction_b": fac_b,
            "champion_a": ch_a, "champion_b": ch_b}


def write_record(f, **kwargs):
    f.write(json.dumps(kwargs, ensure_ascii=False) + "\n")
    f.flush()


# ── Phase 1 : Group Stage (round-robin) ──────────────────────────────────────

def run_matrix(pool: list[str], games: int, seeds: list[int],
               out_path: Path, append: bool = False) -> None:
    pairs = list(combinations(pool, 2))
    n_per_pair = len(seeds) * 2 * games
    total      = len(pairs) * n_per_pair

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not append and out_path.exists():
        out_path.unlink()

    print(f"[group] pool={pool}")
    print(f"[group] {len(pairs)} paires x {n_per_pair} games = {total} games")
    print()

    t0   = time.time()
    done = 0
    with out_path.open("a", encoding="utf-8") as f:
        for a, b in pairs:
            for seed in seeds:
                for mirror, (sa, sb) in enumerate([(a, b), (b, a)]):
                    for g in range(games):
                        gseed = seed * 1000 + mirror * 100 + g
                        res   = run_one_game(sa, sb, gseed)
                        write_record(
                            f,
                            event="game_end", phase="group",
                            side_a=sa, side_b=sb,
                            winner=res.get("winner"), turns=res.get("turns"),
                            faction_a=res.get("faction_a"),  faction_b=res.get("faction_b"),
                            champion_a=res.get("champion_a"), champion_b=res.get("champion_b"),
                            seed=gseed, mirror="ab" if mirror == 0 else "ba",
                        )
                        done += 1
                        eta = (time.time() - t0) / done * (total - done)
                        turns_str = str(res.get('turns') or '?')
                        print(f"[GRP {done:>4}/{total}] {sa:>9} vs {sb:<9} "
                              f"seed={gseed} winner={str(res.get('winner')):>5} "
                              f"turns={turns_str:>3}  ETA {eta/60:.1f} min")
    print(f"\n[group OK] {(time.time()-t0)/60:.1f} min")


# ── Ranking depuis JSONL group ───────────────────────────────────────────────

def compute_ranking(jsonl_path: Path) -> list[tuple[str, dict]]:
    """Calcule WR par profil sur les records phase='group' (ou tout si phase absent)."""
    stats: dict[str, dict] = defaultdict(lambda: {"wins": 0, "draws": 0, "n": 0})
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("event") != "game_end":
                continue
            if r.get("phase", "group") != "group":
                continue
            sa, sb = r.get("side_a"), r.get("side_b")
            if not sa or not sb:
                continue
            stats[sa]["n"] += 1
            stats[sb]["n"] += 1
            w = r.get("winner")
            if w == "a":
                stats[sa]["wins"] += 1
            elif w == "b":
                stats[sb]["wins"] += 1
            else:  # draw / error
                stats[sa]["draws"] += 1
                stats[sb]["draws"] += 1
    # Score = WR (wins+0.5*draws) / n
    ranking = []
    for k, v in stats.items():
        if v["n"] == 0:
            continue
        score = (v["wins"] + 0.5 * v["draws"]) / v["n"]
        ranking.append((k, {**v, "wr": score}))
    ranking.sort(key=lambda kv: -kv[1]["wr"])
    return ranking


# ── Phase 2 : Playoff bracket ────────────────────────────────────────────────

def run_match(side_a: str, side_b: str, games: int, base_seed: int,
              out_path: Path, round_name: str, match_id: int) -> str:
    """Joue une série best-of-N (a vs b alternés). Retourne le vainqueur."""
    wins = {side_a: 0, side_b: 0}
    print(f"\n  [{round_name} M{match_id}] {side_a} vs {side_b} (BO{games})")
    with out_path.open("a", encoding="utf-8") as f:
        for g in range(games):
            # Mirror : games pairs sa joue A, impairs sb joue A
            sa, sb = (side_a, side_b) if g % 2 == 0 else (side_b, side_a)
            gseed  = base_seed + g
            res    = run_one_game(sa, sb, gseed)
            w = res.get("winner")
            if w == "a":   wins[sa] += 1
            elif w == "b": wins[sb] += 1
            # Les draws ne comptent pour personne en playoff

            write_record(
                f,
                event="game_end", phase="playoff",
                side_a=sa, side_b=sb,
                winner=w, turns=res.get("turns"),
                faction_a=res.get("faction_a"),  faction_b=res.get("faction_b"),
                champion_a=res.get("champion_a"), champion_b=res.get("champion_b"),
                seed=gseed, round=round_name, match_id=match_id,
                game_in_match=g + 1,
            )
            print(f"    g{g+1:02} seed={gseed} {sa} vs {sb} -> {w}  "
                  f"[{side_a}={wins[side_a]} {side_b}={wins[side_b]}]")

    winner = side_a if wins[side_a] >= wins[side_b] else side_b
    print(f"  -> vainqueur {round_name} M{match_id} : {winner} "
          f"({wins[side_a]}-{wins[side_b]})")
    return winner


def run_bracket(top8: list[str], games_per_match: int,
                base_seed: int, out_path: Path) -> dict:
    """NBA seeding : 1v8, 2v7, 3v6, 4v5 -> SF1=W1/W4 vs W2/W3 -> F."""
    assert len(top8) == 8
    print(f"\n[playoff] Top 8 seedés : {top8}")
    print(f"[playoff] BO{games_per_match} par match")

    qf = [
        run_match(top8[0], top8[7], games_per_match, base_seed + 0,   out_path, "QF", 1),
        run_match(top8[3], top8[4], games_per_match, base_seed + 100, out_path, "QF", 2),
        run_match(top8[1], top8[6], games_per_match, base_seed + 200, out_path, "QF", 3),
        run_match(top8[2], top8[5], games_per_match, base_seed + 300, out_path, "QF", 4),
    ]
    sf = [
        run_match(qf[0], qf[1], games_per_match, base_seed + 500, out_path, "SF", 1),
        run_match(qf[2], qf[3], games_per_match, base_seed + 600, out_path, "SF", 2),
    ]
    champ = run_match(sf[0], sf[1], games_per_match, base_seed + 800, out_path, "F", 1)
    return {"qf": qf, "sf": sf, "champion": champ}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode",  choices=["matrix", "bracket", "both"], default="both")
    ap.add_argument("--pool",  default=",".join(DEFAULT_POOL))
    ap.add_argument("--games", type=int, default=5,
                    help="Group : games par mirror. Total/paire = 2 mirrors x N seeds x games")
    ap.add_argument("--seeds", default="42,137")
    ap.add_argument("--playoff-games", type=int, default=9,
                    help="Best-of-N par match playoff (9 = first à 5)")
    ap.add_argument("--out",   type=Path,
                    default=ROOT / "reports" / "bracket" / "llm_tournament" / "matrix.jsonl")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--exploration", type=float, default=0.0,
                    help="Taux d'exploration random faction (ex: 0.15 = 15%%)")
    args = ap.parse_args()

    global EXPLORATION_RATE
    EXPLORATION_RATE = args.exploration

    pool  = [p.strip() for p in args.pool.split(",") if p.strip()]
    seeds = [int(s) for s in args.seeds.split(",")]

    print(f"[mode={args.mode}] out={args.out}")
    print()

    if args.mode in ("matrix", "both"):
        run_matrix(pool, args.games, seeds, args.out, append=args.append)

    if args.mode in ("bracket", "both"):
        if not args.out.exists():
            print(f"[ERR] Pas de matrix data dans {args.out} — lance --mode matrix d'abord.")
            sys.exit(1)
        ranking = compute_ranking(args.out)
        if len(ranking) < 8:
            print(f"[ERR] Seulement {len(ranking)} profils classés, besoin de 8 pour le bracket.")
            sys.exit(1)

        print("\n=== CLASSEMENT GROUP STAGE ===")
        for i, (name, s) in enumerate(ranking[:11], 1):
            print(f"  {i:>2}. {name:<10}  WR {s['wr']*100:5.1f}%  "
                  f"({s['wins']}W {s['draws']}D, {s['n']} games)")

        top8 = [r[0] for r in ranking[:8]]
        result = run_bracket(top8, args.playoff_games, base_seed=99000, out_path=args.out)

        print("\n" + "=" * 60)
        print(f"  CHAMPION LLM : {result['champion'].upper()}")
        print("=" * 60)


if __name__ == "__main__":
    main()
