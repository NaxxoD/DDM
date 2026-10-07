"""Phase 4a — Découverte combos RL agents.

Pour chaque agent RL × chaque combo (faction, champion), joue N games vs un
baseline LLM fixe. Output : WR par (agent, faction, champion).

Usage :
    python tools/scripts/rl_combo_eval.py --opponent glm --games 10 \\
        --out reports/rl_combo_eval/eval.jsonl

Output JSONL records :
    {"event": "game_end", "agent": "jin", "faction": 1, "champion": "A",
     "winner": "a"|"b"|"draw", "turns": int, ...}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rl.bracket import run_one_game, load_model, AGENT_CKPT  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_AGENTS = ["jin", "jio", "cross", "jaeha", "neosia"]
DEFAULT_OPPONENTS = ["greedy", "haiku", "gemini", "chatgpt", "mistral",
                     "grok", "sonnet", "opus", "deepseek", "qwen3", "glm"]
FACTIONS = list(range(1, 9))         # 1-8
CHAMPIONS = ["A", "B", "C", "D", "E"]


def load_opponent_pref(profile: str) -> tuple[int | None, str | None]:
    fp = ROOT / "data" / f"{profile}_prefs.json"
    if not fp.exists():
        return None, None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        p = data.get("preferred") or {}
        return p.get("faction"), p.get("champion")
    except Exception:
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(DEFAULT_AGENTS),
                    help="CSV des agents RL à tester")
    ap.add_argument("--opponents", default=",".join(DEFAULT_OPPONENTS),
                    help="CSV des LLM opponents (chacun avec sa pref forcée)")
    ap.add_argument("--games", type=int, default=3,
                    help="Games par combo × opponent (faction × champion × agent × opponent)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "reports" / "rl_combo_eval" / "eval.jsonl")
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()

    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    opponents = [o.strip() for o in args.opponents.split(",") if o.strip()]
    for a in agents:
        if a not in AGENT_CKPT:
            raise SystemExit(f"Agent inconnu : {a}. Dispo : {sorted(AGENT_CKPT)}")

    # Precompute opponent prefs
    opp_prefs = {o: load_opponent_pref(o) for o in opponents}
    print(f"[rl_combo_eval] opponents : {opponents}")
    print(f"[rl_combo_eval] opp prefs : {opp_prefs}\n")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not args.append and args.out.exists():
        args.out.unlink()

    total_combos = len(agents) * len(FACTIONS) * len(CHAMPIONS) * len(opponents)
    total_games  = total_combos * args.games
    print(f"[rl_combo_eval] {len(agents)} agents x {len(FACTIONS)*len(CHAMPIONS)} combos "
          f"x {len(opponents)} opponents x {args.games} games = {total_games} games")
    print(f"[rl_combo_eval] out = {args.out}\n", flush=True)

    t0 = time.time()
    done = 0

    with args.out.open("a", encoding="utf-8") as f:
        for agent in agents:
            print(f"\n=== Loading {agent} ===", flush=True)
            ckpt = AGENT_CKPT[agent]
            model = load_model(ckpt)

            for fid in FACTIONS:
                for champ in CHAMPIONS:
                    combo_wins = 0
                    combo_n    = 0
                    for opp in opponents:
                        opp_fid, opp_champ = opp_prefs.get(opp, (None, None))
                        for g in range(args.games):
                            gseed = args.seed + g + fid * 1000 + ord(champ) * 100 + hash(opp) % 10000
                            try:
                                res = run_one_game(
                                    model, opp,
                                    seed=gseed,
                                    rl_side="A",
                                    faction_rl=fid,
                                    champion_rl=champ,
                                    faction_opp=opp_fid,
                                    champion_opp=opp_champ,
                                )
                            except Exception as e:
                                print(f"  [ERR] {agent} f{fid}+{champ} vs {opp} g{g}: {e}", flush=True)
                                continue
                            w = res.get("winner")
                            if w == "a":   combo_wins += 1
                            elif w == "d" or w == "draw": combo_wins += 0.5
                            combo_n += 1
                            f.write(json.dumps({
                                "event":    "game_end",
                                "agent":    agent,
                                "faction":  fid,
                                "champion": champ,
                                "opponent": opp,
                                "opp_fac":  opp_fid,
                                "opp_champ": opp_champ,
                                "winner":   w,
                                "turns":    res.get("turns"),
                                "seed":     gseed,
                            }, ensure_ascii=False) + "\n")
                            f.flush()
                            done += 1

                    wr = combo_wins / max(combo_n, 1) * 100
                    elapsed = time.time() - t0
                    eta = elapsed / done * (total_games - done) if done else 0
                    print(f"  {agent} f{fid}+{champ}: WR {wr:5.1f}% "
                          f"vs {len(opponents)} LLMs ({combo_n}g)  ETA {eta/60:.1f} min", flush=True)

    print(f"\n[OK] Terminé en {(time.time()-t0)/60:.1f} min — {args.out}")
    print(f"Lance le rapport avec :")
    print(f"  python tools/scripts/rl_combo_report.py {args.out}")


if __name__ == "__main__":
    main()
