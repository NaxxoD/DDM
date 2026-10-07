"""
rl/bracket.py — RL vs RL bracket / matrix evaluation.

Plays N games between two PPO agents (or one agent vs greedy heuristic),
streaming JSONL results for live monitoring + post-hoc analysis.

Usage:
    # Single H2H pair
    python -m rl.bracket pair --side-a jin --side-b jio --games 50 --seed 42 --out reports/bracket/jin_vs_jio.jsonl

    # Full matrix (all 6 H2H pairs of 4 agents, 3 seeds, mirror)
    python -m rl.bracket matrix --games 50 --seeds 42,137,999 --out-dir reports/bracket/run_001/

    # Boss greedy (champion vs greedy)
    python -m rl.bracket boss --champion jin --games 100 --seeds 42,137,999 --out reports/bracket/run_001/boss.jsonl

JSONL format (one line per game):
    {"event":"game_end","ts":"...","match":"jin_vs_jio","seed":42,"mirror":"a",
     "game_idx":0,"side_a":"jin","side_b":"jio","faction_a":1,"champion_a":"B",
     "faction_b":3,"champion_b":"E","winner":"a","hq_a":12,"hq_b":0,"turns":47}

Configuration : checkpoints chargés via le mapping AGENT_CKPT (édite si besoin).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Force utf-8 stdout (sinon crash sur les flèches Unicode des profiles LLM).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Workers must mute stdout BEFORE engine import (same as eval_agent.py).
os.environ["DDM_RL_WORKER"] = "1"
os.environ["DDM_AUTORUN"]   = "1"

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stable_baselines3 import PPO

from rl.ddm_env import DDMEnv


# ── Production checkpoints (post-eval 2026-05-08) ─────────────────────────────

AGENT_CKPT = {
    "jin":          "rl/checkpoints/v1.7/jin/jin_final.zip",
    "jio":          "rl/checkpoints/v2/v2b/jio/jio_final.zip",
    "cross":        "rl/checkpoints/v1.7/cross/cross_final.zip",
    "jaeha":        "rl/checkpoints/v1.7/jaeha/jaeha_final.zip",
    "neosia":       "rl/checkpoints/neosia/neosia/neosia_final.zip",
    "zenom":        "rl/checkpoints/zenom/zenom/zenom_final.zip",
    "zenom_frozen": "rl/checkpoints/zenom/zenom/zenom_frozen.zip",
}

AGENTS = ["jin", "jio", "cross", "jaeha"]  # ordre canonique 4 agents (matrix défaut)
ALL_AGENTS = list(AGENT_CKPT.keys())  # incluant neosia


# ── Custom opponent fn : wraps a PPO model as opponent ────────────────────────

def make_rl_opponent_fn(model: PPO, env: DDMEnv):
    """Returns a phase_mobs_X-compatible fn that runs `model` for the opponent side.

    The trick: temporarily swap env.rl_side ↔ env.opp_side so _build_obs() yields
    the opponent's perspective, then restore.
    """
    def fn(state, owner, must_hq_fn):
        orig_rl  = env.rl_side
        orig_opp = env.opp_side
        env.rl_side  = owner
        env.opp_side = "A" if owner == "B" else "B"
        try:
            obs = env._build_obs()
            action, _ = model.predict(obs, deterministic=True)
            env._run_rl_mob_phase(action, state, owner, env.opp_side)
        finally:
            env.rl_side  = orig_rl
            env.opp_side = orig_opp
        return True
    return fn


# ── Game runner ───────────────────────────────────────────────────────────────

def run_one_game(model_a: PPO, opp_b, seed: int, max_rounds: int = 120,
                 bag_size: int = 11, rl_side: str = "A",
                 faction_rl: int | None = None, champion_rl: str | None = None,
                 faction_opp: int | None = None, champion_opp: str | None = None) -> dict:
    """Play one game. opp_b is either:
        - a PPO model (for RL vs RL)
        - a string in {"greedy", ...} (for RL vs heuristic LLM)

    rl_side : côté joué par le RL (model_a). Default "A". Si "B", l'heuristique
    (opp_b string) joue côté A. Permet le mirror b avec un boss heuristique.

    faction_rl/champion_rl/faction_opp/champion_opp : combos forcés (None = random).

    Returns a dict ready to be JSON-dumped.
    """
    if isinstance(opp_b, PPO):
        opponent_str = "greedy"  # placeholder (overridden by monkey-patch below)
    else:
        opponent_str = opp_b

    env = DDMEnv(
        opponent     = opponent_str,
        rl_side      = rl_side,
        faction_rl   = faction_rl,
        champion_rl  = champion_rl,
        faction_opp  = faction_opp,
        champion_opp = champion_opp,
        max_rounds   = max_rounds,
        bag_size     = bag_size,
        seed         = seed,
    )

    # If RL vs RL, swap the opponent fn for our custom predict-based wrapper.
    if isinstance(opp_b, PPO):
        custom_fn = make_rl_opponent_fn(opp_b, env)
        env._get_opp_fn = lambda: custom_fn  # bound replacement

    obs, _ = env.reset()
    if env.state is not None:
        env.state.run_mode = "iaia"

    done = False
    info = {}
    while not done:
        action, _ = model_a.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    hq_a = info.get("hq_A", 1)
    hq_b = info.get("hq_B", 1)
    if hq_b <= 0 and hq_a > 0:
        winner = "a"
    elif hq_a <= 0 and hq_b > 0:
        winner = "b"
    else:
        winner = "draw"

    # Mapping faction info → side_a/side_b selon rl_side
    if rl_side == "A":
        f_a, c_a = info.get("faction_rl"),  info.get("champion_rl")
        f_b, c_b = info.get("faction_opp"), info.get("champion_opp")
    else:  # rl_side == "B" : RL est sur side B, heuristique sur side A
        f_a, c_a = info.get("faction_opp"), info.get("champion_opp")
        f_b, c_b = info.get("faction_rl"),  info.get("champion_rl")

    out = {
        "winner":     winner,
        "hq_a":       hq_a,
        "hq_b":       hq_b,
        "turns":      info.get("round", 0),
        "faction_a":  f_a,
        "champion_a": c_a,
        "faction_b":  f_b,
        "champion_b": c_b,
    }
    env.close()
    return out


# ── Pair runner ───────────────────────────────────────────────────────────────

def load_model(path: str | Path) -> PPO:
    print(f"[bracket] loading {path}", file=sys.stderr)
    return PPO.load(str(path), env=None)


LLM_PROFILES = {"greedy","haiku","mistral","grok","gemini","chatgpt","sonnet","opus","deepseek","qwen3","glm","claude_api"}


def run_pair(side_a: str, side_b: str, games: int, seed: int,
             out_path: Path, mirror: str = "a",
             ckpt_a: str | None = None, ckpt_b: str | None = None,
             faction_a: int | None = None, champion_a: str | None = None,
             faction_b: int | None = None, champion_b: str | None = None) -> dict:
    """Run `games` matches between side_a and side_b. Append JSONL to out_path.

    side_a et side_b peuvent être :
      - un nom d'agent RL (jin/jio/cross/jaeha/neosia) → load PPO
      - "greedy" → heuristique greedy
      - "claude_api" → opponent Claude via API (nécessite ANTHROPIC_API_KEY)
      - tout autre nom de profil LLM scripté (claude, sonnet, opus, ...)

    Au moins un des deux côtés doit être un agent RL (le moteur a besoin d'un
    "rl_side" qui pilote via model.predict).

    Returns a summary dict.
    """
    a_is_llm = side_a in LLM_PROFILES
    b_is_llm = side_b in LLM_PROFILES
    if a_is_llm and b_is_llm:
        raise ValueError(f"At least one side must be an RL agent. Got {side_a} vs {side_b}.")

    # Si side_a est heuristique : on inverse — RL passe côté B, heuristique côté A.
    # Cela permet d'avoir un mirror b naturel quand un boss heuristique est en side_a.
    if a_is_llm:
        # Le RL est sur side_b → on le charge comme model_a et on opp_b = side_a (heuristique)
        ckpt_b = ckpt_b or AGENT_CKPT[side_b]
        model_a = load_model(ckpt_b)
        opp = side_a  # heuristique sur side A du moteur, mais on swap rl_side="B"
        rl_side = "B"
    else:
        ckpt_a = ckpt_a or AGENT_CKPT[side_a]
        model_a = load_model(ckpt_a)
        rl_side = "A"
        if b_is_llm:
            opp = side_b
        else:
            ckpt_b = ckpt_b or AGENT_CKPT[side_b]
            opp = load_model(ckpt_b)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    match_id = f"{side_a}_vs_{side_b}"

    wins_a = wins_b = draws = 0
    t0 = time.time()
    with out_path.open("a", encoding="utf-8") as f:
        # Game-start banner (visible in the JSONL stream for watchers)
        f.write(json.dumps({
            "event":   "match_start",
            "ts":      datetime.now().isoformat(timespec="seconds"),
            "match":   match_id,
            "seed":    seed,
            "mirror":  mirror,
            "side_a":  side_a,
            "side_b":  side_b,
            "games":   games,
        }) + "\n")
        f.flush()

        # Résoudre faction/champion selon quel côté est RL
        if a_is_llm:
            frl, crl   = faction_b, champion_b
            fopp, copp = faction_a, champion_a
        else:
            frl, crl   = faction_a, champion_a
            fopp, copp = faction_b, champion_b

        for i in range(games):
            res = run_one_game(model_a, opp, seed=seed * 10_000 + i, rl_side=rl_side,
                               faction_rl=frl, champion_rl=crl,
                               faction_opp=fopp, champion_opp=copp)
            res.update({
                "event":    "game_end",
                "ts":       datetime.now().isoformat(timespec="seconds"),
                "match":    match_id,
                "seed":     seed,
                "mirror":   mirror,
                "game_idx": i,
                "side_a":   side_a,
                "side_b":   side_b,
            })
            f.write(json.dumps(res) + "\n")
            f.flush()
            if res["winner"] == "a":
                wins_a += 1
            elif res["winner"] == "b":
                wins_b += 1
            else:
                draws += 1
            if (i + 1) % 10 == 0 or (i + 1) == games:
                elapsed = time.time() - t0
                eta = elapsed / (i + 1) * (games - i - 1)
                print(
                    f"  [{match_id} seed={seed} mirror={mirror}] "
                    f"{i+1}/{games}  A {wins_a}-{wins_b} B  ({draws}D)  "
                    f"ETA {eta:.0f}s",
                    file=sys.stderr,
                )

        summary = {
            "event":   "match_end",
            "ts":      datetime.now().isoformat(timespec="seconds"),
            "match":   match_id,
            "seed":    seed,
            "mirror":  mirror,
            "wins_a":  wins_a,
            "wins_b":  wins_b,
            "draws":   draws,
            "games":   games,
            "wr_a":    (wins_a + 0.5 * draws) / games if games else 0.0,
        }
        f.write(json.dumps(summary) + "\n")
    return summary


# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_pair(args):
    out = Path(args.out)
    res = run_pair(args.side_a, args.side_b, args.games, args.seed, out,
                   mirror=args.mirror, ckpt_a=args.ckpt_a, ckpt_b=args.ckpt_b)
    print(f"\n[OK] {res['match']} seed={res['seed']} mirror={res['mirror']}: "
          f"A {res['wins_a']}-{res['wins_b']} B  ({res['draws']}D)  WR_a={res['wr_a']:.1%}")


def cmd_matrix(args):
    seeds = [int(s) for s in args.seeds.split(",")]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pool = [a.strip() for a in args.pool.split(",")] if args.pool else AGENTS
    for a in pool:
        if a not in AGENT_CKPT:
            raise ValueError(f"Agent '{a}' inconnu. Dispo : {sorted(AGENT_CKPT)}")
    pairs = [(a, b) for i, a in enumerate(pool) for b in pool[i+1:]]

    print(f"[bracket] matrix mode: {len(pairs)} pairs × {len(seeds)} seeds × 2 mirrors × {args.games} games")
    print(f"[bracket] total : {len(pairs) * len(seeds) * 2 * args.games} games")
    print(f"[bracket] out   : {out_dir}")

    out_path = out_dir / "matrix.jsonl"
    # Reset stats : on est sur un nouveau run, on efface les anciennes données
    if out_path.exists() and not args.append:
        print(f"[bracket] reset {out_path} (existant)")
        out_path.unlink()
    for a, b in pairs:
        for s in seeds:
            for mirror in ("a", "b"):
                # mirror "b" : swap sides → side_a becomes b, side_b becomes a
                if mirror == "a":
                    run_pair(a, b, args.games, s, out_path, mirror="a")
                else:
                    run_pair(b, a, args.games, s, out_path, mirror="b")
    print(f"\n[OK] Matrix terminée → {out_path}")


def cmd_boss(args):
    seeds = [int(s) for s in args.seeds.split(",")]
    out_path = Path(args.out)
    if out_path.exists() and not args.append:
        print(f"[bracket] reset {out_path} (existant)")
        out_path.unlink()
    print(f"[bracket] boss greedy: {args.champion} vs greedy, {len(seeds)} seeds × {args.games} games")
    for s in seeds:
        run_pair(args.champion, "greedy", args.games, s, out_path, mirror="a")
    print(f"\n[OK] Boss terminé → {out_path}")


def cmd_bracket(args):
    """Single-elimination playoff: 4 agents → 2 demis → 1 finale → bosses séquentiels.

    Seeding is by --seeding (4 agents). Bosses by --bosses (csv, défaut: greedy).
    Demis: (1) vs (4), (2) vs (3). Winners go to finale.
    Champion face ensuite chaque boss dans l'ordre.
    """
    seeding = [s.strip() for s in args.seeding.split(",")]
    if len(seeding) != 4:
        print(f"[ERREUR] --seeding doit avoir 4 agents (csv), reçu : {seeding}", file=sys.stderr)
        sys.exit(1)
    valid_seeds = set(ALL_AGENTS)
    for s in seeding:
        if s not in valid_seeds:
            print(f"[ERREUR] seed '{s}' inconnu. Valides : {sorted(valid_seeds)}", file=sys.stderr)
            sys.exit(1)
    bosses = [b.strip() for b in args.bosses.split(",") if b.strip()]
    valid_bosses = set(ALL_AGENTS) | {"greedy", "claude_api"}
    for b in bosses:
        if b not in valid_bosses:
            print(f"[ERREUR] boss '{b}' inconnu. Valides : {sorted(valid_bosses)}", file=sys.stderr)
            sys.exit(1)

    seeds = [int(s) for s in args.seeds.split(",")]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "bracket.jsonl"
    # Reset stats : nouveau run = clean slate
    if out_path.exists() and not args.append:
        print(f"[bracket] reset {out_path} (existant)")
        out_path.unlink()

    s1, s2, s3, s4 = seeding

    def pick_winner(side_a: str, side_b: str, label: str) -> str:
        print(f"\n--- {label} : {side_a} vs {side_b} ---")
        wa = wb = 0
        for s in seeds:
            for mirror in ("a", "b"):
                if mirror == "a":
                    res = run_pair(side_a, side_b, args.games, s, out_path, mirror=f"{label}_a")
                    wa += res["wins_a"]; wb += res["wins_b"]
                else:
                    res = run_pair(side_b, side_a, args.games, s, out_path, mirror=f"{label}_b")
                    wa += res["wins_b"]; wb += res["wins_a"]  # swap because side_a = side_b
        print(f"--- {label} résultat : {side_a} {wa} - {wb} {side_b} ---")
        return side_a if wa >= wb else side_b

    print(f"[bracket] playoff seeding : (1){s1} (2){s2} (3){s3} (4){s4}")
    print(f"[bracket] bosses           : {' → '.join(bosses) if bosses else '(none)'}")
    semi1_winner = pick_winner(s1, s4, "semi1")
    semi2_winner = pick_winner(s2, s3, "semi2")
    final_winner = pick_winner(semi1_winner, semi2_winner, "final")

    # Bosses séquentiels (greedy → jaeha par défaut, ou personnalisé via --bosses)
    current_champion = final_winner
    for i, boss in enumerate(bosses, 1):
        boss_label = f"boss{i}_{boss}"
        print(f"\n--- BOSS {i}/{len(bosses)} : {current_champion} vs {boss} ---")
        wa = wb = 0
        for s in seeds:
            for mirror in ("a", "b"):
                if mirror == "a":
                    res = run_pair(current_champion, boss, args.games * 2, s, out_path, mirror=f"{boss_label}_a")
                    wa += res["wins_a"]; wb += res["wins_b"]
                else:
                    res = run_pair(boss, current_champion, args.games * 2, s, out_path, mirror=f"{boss_label}_b")
                    wa += res["wins_b"]; wb += res["wins_a"]
        print(f"--- BOSS {i} résultat : {current_champion} {wa} - {wb} {boss} ---")
        if wa <= wb:
            print(f"[bracket] ❌ {current_champion} battu par {boss}. Tournament stop.")
            current_champion = boss  # le boss devient champion (mais on stop le run)
            break
        print(f"[bracket] ✅ {current_champion} bat {boss}")

    print(f"\n[OK] Champion final : {current_champion}")
    print(f"[OK] Bracket terminé → {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p_pair = sp.add_parser("pair", help="Run a single H2H pairing")
    # side_a et side_b acceptent : agents RL (incluant neosia) + tous les profils LLM
    # heuristiques + claude_api. Au moins un des deux doit être un RL (validation runtime).
    _pair_choices = ALL_AGENTS + sorted(LLM_PROFILES)
    p_pair.add_argument("--side-a", required=True, choices=_pair_choices)
    p_pair.add_argument("--side-b", required=True, choices=_pair_choices)
    p_pair.add_argument("--games",  type=int, default=50)
    p_pair.add_argument("--seed",   type=int, default=42)
    p_pair.add_argument("--mirror", default="a", help="Tag pour distinguer mirror runs")
    p_pair.add_argument("--out",    required=True)
    p_pair.add_argument("--ckpt-a", default=None)
    p_pair.add_argument("--ckpt-b", default=None)
    p_pair.set_defaults(func=cmd_pair)

    p_mat = sp.add_parser("matrix", help="All H2H pairings (default 4 agents = 6 pairs)")
    p_mat.add_argument("--games",   type=int, default=50)
    p_mat.add_argument("--seeds",   default="42,137,999")
    p_mat.add_argument("--out-dir", required=True)
    p_mat.add_argument("--pool",    default=None,
                       help="CSV agents (defaut: jin,jio,cross,jaeha). Ajouter neosia = 5 agents = 10 pairs")
    p_mat.add_argument("--append",  action="store_true",
                       help="Conserve les données existantes (défaut: reset propre)")
    p_mat.set_defaults(func=cmd_matrix)

    p_bos = sp.add_parser("boss", help="Champion vs greedy (final boss)")
    p_bos.add_argument("--champion", required=True, choices=AGENTS)
    p_bos.add_argument("--games",    type=int, default=100)
    p_bos.add_argument("--seeds",    default="42,137,999")
    p_bos.add_argument("--out",      required=True)
    p_bos.add_argument("--append",   action="store_true",
                       help="Conserve les données existantes (défaut: reset propre)")
    p_bos.set_defaults(func=cmd_boss)

    p_brk = sp.add_parser("bracket", help="Single-elim playoff: 4 agents + bosses séquentiels")
    p_brk.add_argument("--seeding", default="jio,jin,cross,jaeha",
                       help="Ordre des seeds 1→4 (csv). 4 agents (peut inclure neosia).")
    p_brk.add_argument("--bosses",  default="greedy",
                       help="Bosses séquentiels après la finale (csv). Ex: 'greedy,jaeha'. "
                            "Le champion affronte chaque boss dans l'ordre. Stop si battu.")
    p_brk.add_argument("--games",   type=int, default=50)
    p_brk.add_argument("--seeds",   default="42,137,999")
    p_brk.add_argument("--out-dir", required=True)
    p_brk.add_argument("--append",  action="store_true",
                       help="Conserve les données existantes (défaut: reset propre)")
    p_brk.set_defaults(func=cmd_bracket)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
