"""
rl/eval_agent.py  —  Eval matricielle faction×champion vs un adversaire LLM.

Usage :
    python -m rl.eval_agent --agent jin --checkpoint rl/checkpoints/v2/v2b/jin/jin_final.zip
    python -m rl.eval_agent --agent jio --checkpoint rl/checkpoints/v2/v2b/jio/jio_final.zip --opponent opus
    python -m rl.eval_agent --agent cross --checkpoint rl/checkpoints/v2/v2d/cross/cross_final.zip

Flow :
    Phase 1 — Exploration : 40 combos (8 factions × 5 champions) × N games
    Phase 2 — Confirmation : top K combos × M games supplémentaires
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stable_baselines3 import PPO
from rl.ddm_env import DDMEnv


FACTIONS  = [1, 2, 3, 4, 5, 6, 7, 8]
CHAMPIONS = ["A", "B", "C", "D", "E"]


# ── Env helpers ───────────────────────────────────────────────────────────────

def make_env(
    opponent:    str,
    faction_rl:  int,
    champion_rl: str,
    max_rounds:  int = 120,
    bag_size:    int = 11,
    seed:        int = 0,
) -> DDMEnv:
    env = DDMEnv(
        opponent     = opponent,
        rl_side      = "A",
        faction_rl   = faction_rl,
        champion_rl  = champion_rl,
        faction_opp  = None,   # opponent plays random
        champion_opp = None,
        max_rounds   = max_rounds,
        bag_size     = bag_size,
        seed         = seed,
    )
    return env


def run_episodes(
    model:       PPO,
    opponent:    str,
    faction_rl:  int,
    champion_rl: str,
    n_games:     int,
    seed_offset: int = 0,
    max_rounds:  int = 120,
    bag_size:    int = 11,
) -> tuple[int, int, int]:
    """Runs n_games episodes. Returns (wins, draws, losses)."""
    wins = draws = losses = 0

    for i in range(n_games):
        env = make_env(opponent, faction_rl, champion_rl,
                       max_rounds=max_rounds, bag_size=bag_size,
                       seed=seed_offset + i)
        obs, _ = env.reset()
        if env.state is not None:
            env.state.run_mode = "iaia"  # désactive les input() interactifs
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, _, terminated, truncated, info = env.step(action)
            done = terminated or truncated

        hq_a = info.get("hq_A", 1)
        hq_b = info.get("hq_B", 1)
        if hq_b <= 0 and hq_a > 0:
            wins += 1
        elif hq_a <= 0 and hq_b > 0:
            losses += 1
        else:
            draws += 1
        env.close()

    return wins, draws, losses


# ── Output ────────────────────────────────────────────────────────────────────

def write_csv(results: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["faction", "champion", "games", "wins", "draws", "losses", "wr", "phase"])
        writer.writeheader()
        writer.writerows(results)


def write_md(
    agent:      str,
    opponent:   str,
    results:    list[dict],
    confirm:    list[dict],
    out_path:   Path,
    n_games:    int,
    n_confirm:  int,
):
    # Sort exploration by WR desc
    sorted_res = sorted(results, key=lambda r: -r["wr"])

    lines = [
        f"# {agent.upper()} — Eval vs {opponent}",
        f"",
        f"**Exploration** : {len(results)} combos × {n_games} games = {len(results)*n_games} games  ",
        f"**Confirmation** : top {len(confirm)} combos × {n_confirm} games supplémentaires  ",
        f"*Généré le {__import__('datetime').date.today()}*",
        "",
        "## Phase 1 — Exploration (tous combos, triés par WR)",
        "",
        "| Faction | Champion | Wins | Draws | Losses | WR     |",
        "|---------|----------|-----:|------:|-------:|--------|",
    ]
    for r in sorted_res:
        lines.append(
            f"| f{r['faction']:<6} | {r['champion']:<8} | {r['wins']:>4} | {r['draws']:>5} | {r['losses']:>6} | {r['wr']:.1%} |"
        )

    # Matrix view
    lines += [
        "",
        "## Matrice WR (faction × champion)",
        "",
        "| Faction | " + " | ".join(CHAMPIONS) + " |",
        "|---------|" + "|".join(["-------"] * len(CHAMPIONS)) + "|",
    ]
    res_map = {(r["faction"], r["champion"]): r["wr"] for r in results}
    for f in FACTIONS:
        row = f"| f{f:<6} |"
        for ch in CHAMPIONS:
            wr = res_map.get((f, ch))
            row += f" {wr:.1%}  |" if wr is not None else "  —    |"
        lines.append(row)

    # Confirmation
    if confirm:
        lines += [
            "",
            f"## Phase 2 — Confirmation (top combos, {n_confirm} games chacun)",
            "",
            "| Faction | Champion | Wins | Draws | Losses | WR (confirm) | WR (exploration) |",
            "|---------|----------|-----:|------:|-------:|--------------|-----------------|",
        ]
        for r in confirm:
            expl_wr = res_map.get((r["faction"], r["champion"]), float("nan"))
            lines.append(
                f"| f{r['faction']:<6} | {r['champion']:<8} | {r['wins']:>4} | {r['draws']:>5} | {r['losses']:>6} |"
                f" {r['wr']:.1%}        | {expl_wr:.1%}           |"
            )

    # Best combo summary
    best = sorted_res[0]
    lines += [
        "",
        "## Résumé",
        "",
        f"- **Meilleur combo** : faction {best['faction']} + champion {best['champion']} → WR {best['wr']:.1%}",
    ]
    if confirm:
        best_conf = max(confirm, key=lambda r: r["wr"])
        lines.append(
            f"- **Meilleur combo confirmé** : faction {best_conf['faction']} + champion {best_conf['champion']} → WR {best_conf['wr']:.1%} (confirmation)"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] MD écrit : {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent",         required=True, choices=["jin","jio","cross","jaeha"])
    ap.add_argument("--checkpoint",    required=True, help="Chemin vers le .zip SB3")
    ap.add_argument("--opponent",      default="opus",
                    choices=["greedy","haiku","mistral","grok","gemini","chatgpt","sonnet","opus","deepseek","qwen3","glm","claude_api"])
    ap.add_argument("--games-per-combo",  type=int, default=10)
    ap.add_argument("--confirm-games",    type=int, default=50,
                    help="Games supplémentaires pour les top combos (0 = désactivé)")
    ap.add_argument("--top-k",            type=int, default=2,
                    help="Nombre de combos à confirmer")
    ap.add_argument("--save-dir",      default="rl/checkpoints/eval_monoseed")
    ap.add_argument("--max-rounds",    type=int, default=120)
    ap.add_argument("--bag-size",      type=int, default=11, choices=[11, 22])
    ap.add_argument("--seed",          type=int, default=42)
    return ap.parse_args()


def main():
    args = parse_args()

    os.environ["DDM_RL_WORKER"] = "1"
    os.environ["DDM_AUTORUN"]   = "1"   # désactive tous les input() interactifs

    save_dir = Path(args.save_dir) / args.agent
    save_dir.mkdir(parents=True, exist_ok=True)

    csv_path = save_dir / f"{args.agent}_{args.opponent}_eval.csv"
    md_path  = save_dir / f"{args.agent}_{args.opponent}_eval.md"

    print(f"\n{'='*60}")
    print(f"  EVAL : {args.agent.upper()} vs {args.opponent}")
    print(f"  Checkpoint : {args.checkpoint}")
    print(f"  Combos     : {len(FACTIONS)} factions × {len(CHAMPIONS)} champions = {len(FACTIONS)*len(CHAMPIONS)}")
    print(f"  Games/combo: {args.games_per_combo}  (exploration)")
    print(f"  Confirm    : top {args.top_k} combos × {args.confirm_games} games")
    print(f"  Save dir   : {save_dir}")
    print(f"{'='*60}\n")

    # Load model (env=None — on crée les envs manuellement par combo)
    model = PPO.load(args.checkpoint, env=None)
    print(f"[OK] Checkpoint chargé : {args.checkpoint}\n")

    # ── Phase 1 — Exploration ─────────────────────────────────────────────────
    results = []
    total_combos = len(FACTIONS) * len(CHAMPIONS)
    done_combos  = 0
    t0 = time.time()

    for faction in FACTIONS:
        for champion in CHAMPIONS:
            done_combos += 1
            seed_offset = args.seed + done_combos * args.games_per_combo

            wins, draws, losses = run_episodes(
                model, args.opponent, faction, champion,
                n_games     = args.games_per_combo,
                seed_offset = seed_offset,
                max_rounds  = args.max_rounds,
                bag_size    = args.bag_size,
            )
            total = wins + draws + losses
            wr    = (wins + 0.5 * draws) / total if total else float("nan")

            results.append({
                "faction":  faction,
                "champion": champion,
                "games":    total,
                "wins":     wins,
                "draws":    draws,
                "losses":   losses,
                "wr":       wr,
                "phase":    "exploration",
            })

            elapsed = time.time() - t0
            eta = elapsed / done_combos * (total_combos - done_combos)
            print(
                f"  [{done_combos:>2}/{total_combos}] f{faction}+{champion} → "
                f"WR {wr:.1%} ({wins}W {draws}D {losses}L)  "
                f"ETA ~{eta/60:.0f}min"
            )

    print(f"\n[Phase 1 terminée en {(time.time()-t0)/60:.1f} min]")

    # ── Phase 2 — Confirmation ────────────────────────────────────────────────
    confirm_results = []
    if args.confirm_games > 0:
        top_combos = sorted(results, key=lambda r: -r["wr"])[:args.top_k]
        print(f"\n[Phase 2] Confirmation des top {args.top_k} combos ({args.confirm_games} games chacun)...")

        for rank, combo in enumerate(top_combos):
            seed_offset = args.seed + 10_000 + rank * args.confirm_games
            wins, draws, losses = run_episodes(
                model, args.opponent, combo["faction"], combo["champion"],
                n_games     = args.confirm_games,
                seed_offset = seed_offset,
                max_rounds  = args.max_rounds,
                bag_size    = args.bag_size,
            )
            total = wins + draws + losses
            wr    = (wins + 0.5 * draws) / total if total else float("nan")

            confirm_results.append({
                "faction":  combo["faction"],
                "champion": combo["champion"],
                "games":    total,
                "wins":     wins,
                "draws":    draws,
                "losses":   losses,
                "wr":       wr,
                "phase":    "confirmation",
            })
            print(f"  f{combo['faction']}+{combo['champion']} → WR {wr:.1%} ({wins}W {draws}D {losses}L)")

    # ── Output ────────────────────────────────────────────────────────────────
    all_results = results + confirm_results
    write_csv(all_results, csv_path)
    write_md(
        agent     = args.agent,
        opponent  = args.opponent,
        results   = results,
        confirm   = confirm_results,
        out_path  = md_path,
        n_games   = args.games_per_combo,
        n_confirm = args.confirm_games,
    )

    print(f"\n{'='*60}")
    print(f"  EVAL TERMINÉE")
    top = sorted(results, key=lambda r: -r["wr"])[0]
    print(f"  Meilleur combo : faction {top['faction']} + champion {top['champion']} → {top['wr']:.1%}")
    if confirm_results:
        best_c = max(confirm_results, key=lambda r: r["wr"])
        print(f"  Confirmé       : faction {best_c['faction']} + champion {best_c['champion']} → {best_c['wr']:.1%}")
    print(f"  CSV : {csv_path}")
    print(f"  MD  : {md_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
