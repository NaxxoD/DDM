"""
rl/train_ppo.py  —  PPO training script for Jin, Jio, Cross.

Usage examples
--------------
# Validation (étape 3) — 500k steps vs Haiku, 4 workers
python -m rl.train_ppo --agent jin --opponent claude --timesteps 500000

# Full curriculum stage — 150k steps per profile, sequential
python -m rl.train_ppo --agent jin --curriculum --timesteps-per-stage 150000

# Continue from checkpoint
python -m rl.train_ppo --agent jin --opponent mistral --load rl/checkpoints/v1/jin/jin_claude_final.zip

# Custom faction (lock RL to Orcs/A)
python -m rl.train_ppo --agent jin --opponent claude --faction-rl 5 --champion-rl A
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv, VecMonitor
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.utils import set_random_seed

# Ensure project root is on path when run as module
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rl.ddm_env import DDMEnv


# ── Opponent spec parser ──────────────────────────────────────────────────────

def _parse_opp_spec(spec: str) -> tuple[str, "int | None", "str | None"]:
    """Parse 'rl:jin:6:D' -> ('rl:jin', 6, 'D'). Other specs pass through unchanged."""
    parts = spec.split(":")
    if len(parts) == 4 and parts[0] == "rl":
        return f"rl:{parts[1]}", int(parts[2]), parts[3]
    return spec, None, None


# ── Curriculum ────────────────────────────────────────────────────────────────

# Jin & Jio : easy → hard
CURRICULUM_STANDARD = ["haiku", "mistral", "grok", "gemini", "chatgpt", "sonnet", "opus"]

# Cross : hard → easy
CURRICULUM_REVERSED = ["opus", "sonnet", "chatgpt", "gemini", "grok", "mistral", "haiku"]

# Jaeha phase 2 : random order, re-shuffled each run
CURRICULUM_RANDOM_BASE = ["haiku", "mistral", "grok", "gemini", "chatgpt", "sonnet", "opus"]

# Neosia phase 1 : training contre les 4 RL agents en rotation
CURRICULUM_NEOSIA_PHASE1 = ["rl:jin", "rl:jio", "rl:cross", "rl:jaeha"]

# Zenom : meta-final, expose à l'intégralité des combos possibles.
# 11 LLM (warmup) + 5 agents × 40 combos (8 factions × 5 champions) = 211 stages.
# Format RL : "rl:agent:faction:champion" (ex: "rl:jin:6:D").
# But : Zenom apprend à contrer n'importe quel combo faction/champion,
#       y compris ceux qu'un humain pourrait jouer.
CURRICULUM_ZENOM_PHASE1 = (
    # 11 LLM warmup
    ["greedy", "haiku", "gemini", "chatgpt", "mistral", "grok",
     "sonnet", "opus", "deepseek", "qwen3", "glm"]
    # 5 RL agents × 40 combos (f1-f8 × A-E), ordre naturel
    + [
        f"rl:{ag}:{f}:{c}"
        for ag in ["jin", "jio", "cross", "jaeha", "neosia"]
        for f in range(1, 9)
        for c in ["A", "B", "C", "D", "E"]
    ]
)
# Total : 211 stages

# Zenom phase 2 : self-play contre frozen copy (zenom_frozen)
# 40 stages : zenom_frozen sur tous les combos (f1-f8 × A-E)
CURRICULUM_ZENOM_PHASE2 = [
    f"rl:zenom_frozen:{f}:{c}"
    for f in range(1, 9)
    for c in ["A", "B", "C", "D", "E"]
]
# Total : 40 stages self-play

CURRICULA = {
    "jin":    CURRICULUM_STANDARD,
    "jio":    CURRICULUM_STANDARD,
    "cross":  CURRICULUM_REVERSED,
    "jaeha":  CURRICULUM_STANDARD,           # overridden by --curriculum-random
    "neosia": CURRICULUM_NEOSIA_PHASE1,
    "zenom":  CURRICULUM_ZENOM_PHASE1,       # phase 1 : 211 stages LLM + RL combos
}


# ── WR Callback ───────────────────────────────────────────────────────────────

class WRCallback(BaseCallback):
    """
    Tracks win-rate, average reward and episode length.
    Logs to stdout every `log_freq` timesteps.
    Optionally advances curriculum when WR >= `advance_wr` over `advance_window` episodes.
    """

    def __init__(
        self,
        agent_name:      str,
        opponent:        str,
        log_freq:        int   = 10_000,
        save_dir:        Path  = Path("rl/checkpoints"),
        curriculum:      Optional[list] = None,
        advance_mode:    str   = "fixed",   # "fixed" | "conditional"
        advance_wr:      float = 0.55,      # conditional: advance when WR >= this
        advance_window:  int   = 200,       # over last N episodes
        timesteps_per_stage: int = 150_000, # fixed: steps per profile
        stage_budgets:   Optional[list] = None,  # per-stage overrides (custom curriculum)
        verbose:         int   = 1,
    ):
        super().__init__(verbose)
        self.agent_name   = agent_name
        self.current_opp  = opponent
        self.log_freq     = log_freq
        self.save_dir     = Path(save_dir)
        self.curriculum   = curriculum
        self.advance_mode = advance_mode
        self.advance_wr   = advance_wr
        self.advance_window   = advance_window
        self.timesteps_per_stage = timesteps_per_stage
        self._stage_budgets = stage_budgets

        self.save_dir.mkdir(parents=True, exist_ok=True)

        # Rolling buffers (across all envs)
        self._wins     = deque(maxlen=advance_window)
        self._lengths  = deque(maxlen=1000)
        self._rewards  = deque(maxlen=1000)

        self._stage_start_steps = -1  # -1 = will be set on first _on_step call
        self._stage_idx = 0 if curriculum is None else (
            curriculum.index(opponent) if opponent in curriculum else 0
        )

        self._total_episodes = 0
        self._last_log_step  = 0

        # Faction/champion distribution tracking
        from collections import Counter
        self._faction_rl_ctr   = Counter()
        self._champion_rl_ctr  = Counter()
        self._faction_opp_ctr  = Counter()
        self._champion_opp_ctr = Counter()
        self._faction_rl_wins  = Counter()
        self._champion_rl_wins = Counter()
        self._pair_rl_ctr      = Counter()  # (faction, champion) pairs
        self._pair_rl_wins     = Counter()
        self._last_distrib_step = 0

        # File logging — opponent-scoped so phase 1 / phase 2 don't overwrite each other
        # Sanitize opponent for Windows filenames (replace ':' which est invalide)
        opp_safe = opponent.replace(":", "_")
        self.csv_path    = self.save_dir / f"{agent_name}_{opp_safe}_training.csv"
        self.md_path     = self.save_dir / f"{agent_name}_{opp_safe}_training.md"
        self.distrib_path = self.save_dir / f"{agent_name}_{opp_safe}_distrib.csv"
        self._stage_log: list = []
        with open(self.csv_path, "w") as _f:
            _f.write("step,stage,opponent,wr,avg_len,avg_r,total_ep\n")
        with open(self.distrib_path, "w") as _f:
            _f.write("step,stage,opponent,type,entity_id,picks,wins,wr\n")

    # ── SB3 hooks ─────────────────────────────────────────────────────────────

    def _on_step(self) -> bool:
        if self._stage_start_steps == -1:
            self._stage_start_steps = self.num_timesteps

        infos = self.locals.get("infos", [])
        dones = self.locals.get("dones", [])

        for done, info in zip(dones, infos):
            if not done:
                continue
            self._total_episodes += 1

            # Determine outcome from final HQ HP
            hq_a = info.get("hq_A", 1)
            hq_b = info.get("hq_B", 1)
            if hq_b <= 0 and hq_a > 0:
                outcome = 1   # RL win
            elif hq_a <= 0 and hq_b > 0:
                outcome = 0   # RL loss
            else:
                outcome = 0.5  # draw / timeout

            self._wins.append(outcome)

            # Faction/champion tracking
            f_rl  = info.get("faction_rl")
            ch_rl = info.get("champion_rl")
            if f_rl is not None:
                self._faction_rl_ctr[f_rl] += 1
                self._faction_rl_wins[f_rl] += outcome
            if ch_rl is not None:
                self._champion_rl_ctr[ch_rl] += 1
                self._champion_rl_wins[ch_rl] += outcome
            if f_rl is not None and ch_rl is not None:
                pair = (f_rl, ch_rl)
                self._pair_rl_ctr[pair]  += 1
                self._pair_rl_wins[pair] += outcome
            if info.get("faction_opp") is not None:
                self._faction_opp_ctr[info["faction_opp"]] += 1
            if info.get("champion_opp") is not None:
                self._champion_opp_ctr[info["champion_opp"]] += 1

            # VecMonitor injects episode stats into info["episode"]
            ep = info.get("episode")
            if ep:
                self._lengths.append(ep["l"])
                self._rewards.append(ep["r"])

        # Periodic log
        if self.num_timesteps - self._last_log_step >= self.log_freq:
            self._log_progress()
            self._last_log_step = self.num_timesteps

        # Distribution log every 50k steps
        if self.num_timesteps - self._last_distrib_step >= 50_000:
            self._log_distribution()
            self._last_distrib_step = self.num_timesteps

        # Curriculum advance check
        if self.curriculum and self._should_advance():
            self._advance_stage()

        return True

    def _on_training_end(self):
        stage_steps = self.num_timesteps - max(self._stage_start_steps, 0)
        self._stage_log.append({
            "stage":    self._stage_idx,
            "opponent": self.current_opp,
            "steps":    stage_steps,
            "final_wr": float(np.mean(self._wins)) if self._wins else float("nan"),
            "avg_len":  float(np.mean(self._lengths)) if self._lengths else float("nan"),
            "top_factions":  self._top_entities(self._faction_rl_ctr,  self._faction_rl_wins,  n=3),
            "top_champions": self._top_entities(self._champion_rl_ctr, self._champion_rl_wins, n=3),
        })
        self._write_md()
        self._save_checkpoint("final")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _log_progress(self):
        wr  = np.mean(self._wins)    if self._wins    else float("nan")
        arl = np.mean(self._lengths) if self._lengths else float("nan")
        arr = np.mean(self._rewards) if self._rewards else float("nan")

        print(
            f"[{self.agent_name.upper()}] step={self.num_timesteps:>8d} | "
            f"opp={self.current_opp:<8s} | "
            f"WR={wr:.1%} ({len(self._wins)} ep) | "
            f"avg_len={arl:.1f} | avg_r={arr:.4f} | "
            f"total_ep={self._total_episodes}"
        )

        # TensorBoard / SB3 logger
        self.logger.record("ddm/win_rate",    wr)
        self.logger.record("ddm/avg_length",  arl)
        self.logger.record("ddm/avg_reward",  arr)
        self.logger.record("ddm/episodes",    self._total_episodes)
        self.logger.dump(self.num_timesteps)

        # CSV log
        with open(self.csv_path, "a") as _f:
            _f.write(f"{self.num_timesteps},{self._stage_idx},{self.current_opp},"
                     f"{wr:.4f},{arl:.1f},{arr:.4f},{self._total_episodes}\n")

    def _log_distribution(self):
        if not self._faction_rl_ctr:
            return
        total = sum(self._faction_rl_ctr.values())

        def fmt_ctr(ctr, label):
            parts = []
            for k, v in sorted(ctr.items(), key=lambda x: -x[1]):
                parts.append(f"{k}:{v}({v*100//max(total,1)}%)")
            return f"{label}=[{' '.join(parts)}]"

        print(
            f"[{self.agent_name.upper()}] step={self.num_timesteps:>8d} | DISTRIB | "
            f"{fmt_ctr(self._faction_rl_ctr, 'f_rl')} "
            f"{fmt_ctr(self._champion_rl_ctr, 'ch_rl')} | "
            f"{fmt_ctr(self._faction_opp_ctr, 'f_opp')} "
            f"{fmt_ctr(self._champion_opp_ctr, 'ch_opp')}"
        )

        # Distrib CSV — cumulative picks + wins + WR per faction/champion
        with open(self.distrib_path, "a") as _f:
            for entity_id, picks in self._faction_rl_ctr.items():
                wins = self._faction_rl_wins[entity_id]
                wr   = wins / picks if picks else float("nan")
                _f.write(f"{self.num_timesteps},{self._stage_idx},{self.current_opp},"
                         f"faction_rl,{entity_id},{picks},{wins:.1f},{wr:.4f}\n")
            for entity_id, picks in self._champion_rl_ctr.items():
                wins = self._champion_rl_wins[entity_id]
                wr   = wins / picks if picks else float("nan")
                _f.write(f"{self.num_timesteps},{self._stage_idx},{self.current_opp},"
                         f"champion_rl,{entity_id},{picks},{wins:.1f},{wr:.4f}\n")
            for (f_id, ch_id), picks in self._pair_rl_ctr.items():
                wins = self._pair_rl_wins[(f_id, ch_id)]
                wr   = wins / picks if picks else float("nan")
                _f.write(f"{self.num_timesteps},{self._stage_idx},{self.current_opp},"
                         f"pair_rl,f{f_id}_{ch_id},{picks},{wins:.1f},{wr:.4f}\n")

    def _should_advance(self) -> bool:
        if self._stage_idx >= len(self.curriculum) - 1:
            return False
        if self.advance_mode == "fixed":
            budget = (
                self._stage_budgets[self._stage_idx]
                if self._stage_budgets is not None
                else self.timesteps_per_stage
            )
            return (self.num_timesteps - self._stage_start_steps) >= budget
        # conditional : avance si WR atteint OU si safety cap (2x budget) écoulé
        budget = (
            self._stage_budgets[self._stage_idx]
            if self._stage_budgets is not None
            else self.timesteps_per_stage
        )
        elapsed = self.num_timesteps - self._stage_start_steps
        if elapsed >= 2 * budget:
            print(f"[WRCallback] safety-cap reached on stage {self._stage_idx} "
                  f"({self.current_opp}) — advance forced (WR={float(np.mean(self._wins)) if self._wins else 0:.2f} < {self.advance_wr})")
            return True
        if len(self._wins) < self.advance_window:
            return False
        return float(np.mean(self._wins)) >= self.advance_wr

    def _advance_stage(self):
        stage_steps = self.num_timesteps - max(self._stage_start_steps, 0)
        self._stage_log.append({
            "stage":    self._stage_idx,
            "opponent": self.current_opp,
            "steps":    stage_steps,
            "final_wr": float(np.mean(self._wins)) if self._wins else float("nan"),
            "avg_len":  float(np.mean(self._lengths)) if self._lengths else float("nan"),
            "top_factions":  self._top_entities(self._faction_rl_ctr,  self._faction_rl_wins,  n=3),
            "top_champions": self._top_entities(self._champion_rl_ctr, self._champion_rl_wins, n=3),
        })
        self._write_md()

        self._save_checkpoint(f"stage{self._stage_idx}_{self.current_opp.replace(':','_')}")
        self._stage_idx += 1
        new_opp = self.curriculum[self._stage_idx]

        print(
            f"\n[{self.agent_name.upper()}] --- CURRICULUM ADVANCE ---  "
            f"{self.current_opp} -> {new_opp}  "
            f"(WR={np.mean(self._wins):.1%})\n"
        )

        self.current_opp = new_opp
        self._stage_start_steps = self.num_timesteps
        self._wins.clear()

        # Hot-swap the opponent in all SubprocVecEnv workers
        try:
            self.training_env.env_method("_set_opponent", new_opp)
        except Exception as e:
            print(f"[WARN] hot-swap failed ({e}). Restart required for opponent change.")

    def _top_entities(self, ctr, wins_ctr, n=3):
        if not ctr:
            return []
        entries = []
        for eid, picks in ctr.items():
            w  = wins_ctr[eid]
            wr = w / picks if picks else 0.0
            entries.append((eid, picks, w, wr))
        entries.sort(key=lambda x: -x[1])  # tri par picks desc
        return entries[:n]

    def _write_md(self):
        lines = [
            f"# {self.agent_name.upper()} — Training Log\n",
            "| Stage | Opponent | Steps | Final WR | Avg Len | Top Factions (picks WR%) | Top Champions (picks WR%) |",
            "|-------|----------|------:|----------|--------:|--------------------------|---------------------------|",
        ]
        for s in self._stage_log:
            wr_str  = f"{s['final_wr']:.1%}" if not np.isnan(s['final_wr']) else "N/A"
            arl_str = f"{s['avg_len']:.1f}"  if not np.isnan(s['avg_len'])  else "N/A"

            def fmt_top(entries):
                if not entries:
                    return "—"
                return " / ".join(f"{e[0]}({e[1]} {e[3]:.0%})" for e in entries)

            fac_str  = fmt_top(s.get("top_factions",  []))
            champ_str = fmt_top(s.get("top_champions", []))
            lines.append(
                f"| {s['stage']} | {s['opponent']:<8} | {s['steps']:>7,} | "
                f"{wr_str:>8} | {arl_str:>7} | {fac_str} | {champ_str} |"
            )
        with open(self.md_path, "w") as _f:
            _f.write("\n".join(lines) + "\n")

    def _save_checkpoint(self, tag: str):
        path = self.save_dir / f"{self.agent_name}_{tag}.zip"
        self.model.save(str(path))
        print(f"[{self.agent_name.upper()}] checkpoint saved: {path}")


# ── Env factory ───────────────────────────────────────────────────────────────

def make_env_fn(
    opponent:     str,
    faction_rl:   Optional[int] = None,
    champion_rl:  Optional[str] = None,
    faction_opp:  Optional[int] = None,
    champion_opp: Optional[str] = None,
    max_rounds:   int           = 120,
    bag_size:     int           = 11,
    seed:         int           = 0,
    rl_side:      str           = "A",
):
    """Returns a thunk for SubprocVecEnv."""
    def _init():
        set_random_seed(seed)
        env = DDMEnv(
            opponent     = opponent,
            rl_side      = rl_side,
            faction_rl   = faction_rl,
            champion_rl  = champion_rl,
            faction_opp  = faction_opp,
            champion_opp = champion_opp,
            max_rounds   = max_rounds,
            bag_size     = bag_size,
            seed         = seed,
        )
        return env
    return _init


# ── Add hot-swap method to DDMEnv ─────────────────────────────────────────────

def _set_opponent(self, opponent: str):
    """Hot-swap opponent profile without resetting the current episode.
    Supporte le format étendu 'rl:agent:faction:champion'."""
    base_opp, f_opp, c_opp = _parse_opp_spec(opponent)
    self.opponent = base_opp.lower()
    if f_opp is not None:
        self.faction_opp  = f_opp
        self.champion_opp = c_opp
    from rl.ddm_env import _PROFILE_FNS, _build_profile_fns
    import rl.ddm_env as _env_mod
    if _env_mod._PROFILE_FNS is None:
        _env_mod._PROFILE_FNS = _build_profile_fns()

DDMEnv._set_opponent = _set_opponent


# ── PPO hyperparameters ───────────────────────────────────────────────────────

PPO_KWARGS = dict(
    learning_rate  = 3e-4,
    n_steps        = 512,      # steps per env per update → 512×4=2048 samples
    batch_size     = 64,
    n_epochs       = 10,
    gamma          = 0.995,    # high gamma: games are long, delayed terminal reward
    gae_lambda     = 0.95,
    clip_range     = 0.2,
    ent_coef       = 0.01,     # mild entropy bonus to stay exploratory
    vf_coef        = 0.5,
    max_grad_norm  = 0.5,
    policy_kwargs  = dict(net_arch=[256, 256]),  # 2 hidden layers, 256 units each
    device         = "cpu",    # MlpPolicy is faster on CPU than GPU
    verbose        = 0,
)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    ap = argparse.ArgumentParser(description="Train PPO agent on DDM")

    # Identity
    ap.add_argument("--agent", choices=["jin", "jio", "cross", "jaeha", "neosia", "zenom"], default="jin")

    # Opponent / curriculum
    # Note: pour un opponent RL, utiliser "rl:<agent>" (ex: "rl:jin", "rl:jaeha")
    #       Ces strings ne sont pas dans choices car validation faite plus bas.
    ap.add_argument("--opponent", default="haiku",
                    help="Opponent profile. LLM heuristics: greedy/haiku/mistral/grok/gemini/"
                         "chatgpt/sonnet/opus/claude_api. RL agents: rl:jin, rl:jio, rl:cross, rl:jaeha.")
    ap.add_argument("--curriculum", action="store_true",
                    help="Run full curriculum (7 stages, fixed order)")
    ap.add_argument("--curriculum-random", action="store_true",
                    help="Jaeha phase 2: random order of 7 LLM profiles (re-shuffled each run)")
    ap.add_argument("--reverse-curriculum", action="store_true",
                    help="Reverse the agent's default curriculum order")
    ap.add_argument("--advance-mode", choices=["fixed","conditional"], default="fixed")
    ap.add_argument("--advance-wr", type=float, default=0.55,
                    help="Conditional advance: target WR threshold")
    ap.add_argument("--curriculum-custom", type=str, default=None,
                    help="Custom curriculum: comma-separated opponents (supports repeats, e.g. sonnet,claude,mistral,sonnet,chatgpt,gemini,grok,sonnet)")
    ap.add_argument("--anchor-steps", type=int, default=150_000,
                    help="Steps for anchor stages in custom curriculum (first unique opponent repeated)")
    ap.add_argument("--middle-steps", type=int, default=100_000,
                    help="Steps for non-anchor stages in custom curriculum")

    # Budget
    ap.add_argument("--timesteps", type=int, default=500_000,
                    help="Total timesteps (single-opponent mode)")
    ap.add_argument("--timesteps-per-stage", type=int, default=150_000,
                    help="Timesteps per curriculum stage (fixed mode)")

    # Parallelism
    ap.add_argument("--n-envs", type=int, default=4)
    ap.add_argument("--balance-sides", action="store_true",
                    help="Distribute workers half on side A, half on side B (default: all A). "
                         "Évite la sur-spécialisation côté A.")

    # Faction lock (optional)
    ap.add_argument("--faction-rl",   type=int,  default=None)
    ap.add_argument("--champion-rl",  type=str,  default=None)
    ap.add_argument("--faction-opp",  type=int,  default=None)
    ap.add_argument("--champion-opp", type=str,  default=None)

    # Game config
    ap.add_argument("--max-rounds", type=int, default=120)
    ap.add_argument("--bag-size",   type=int, default=11, choices=[11, 22])

    # I/O
    ap.add_argument("--load",     type=str, default=None, help="Resume from checkpoint .zip")
    ap.add_argument("--save-dir", type=str, default="rl/checkpoints")
    ap.add_argument("--log-freq", type=int, default=10_000)
    ap.add_argument("--seed",     type=int, default=42)

    args = ap.parse_args()
    # Validation opponent
    valid_llm = {"greedy","haiku","mistral","grok","gemini","chatgpt","sonnet","opus","deepseek","qwen3","glm","claude_api"}
    valid_rl  = {"rl:jin", "rl:jio", "rl:cross", "rl:jaeha", "rl:neosia", "rl:zenom", "rl:zenom_frozen"}
    import re as _re
    _rl_combo_re = _re.compile(r"^rl:(jin|jio|cross|jaeha|neosia|zenom|zenom_frozen):[1-8]:[ABCDE]$")
    if args.opponent not in valid_llm and args.opponent not in valid_rl \
            and not _rl_combo_re.match(args.opponent):
        raise SystemExit(
            f"--opponent invalide: '{args.opponent}'. "
            f"LLM: {sorted(valid_llm)}. RL simple: {sorted(valid_rl)}. "
            f"RL combo: rl:<agent>:<faction>:<champion>  ex: rl:jin:6:D"
        )
    return args


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    save_dir = Path(args.save_dir) / args.agent
    save_dir.mkdir(parents=True, exist_ok=True)

    # Determine starting opponent and total steps
    if args.curriculum_random:
        import random as _random
        curriculum = _random.sample(CURRICULUM_RANDOM_BASE, len(CURRICULUM_RANDOM_BASE))
        start_opp  = curriculum[0]
        total_steps = args.timesteps_per_stage * len(curriculum)
        stage_budgets = None
        print(f"  [Jaeha] Random curriculum order: {curriculum}")
    elif args.curriculum_custom:
        curriculum = [o.strip() for o in args.curriculum_custom.split(",")]
        start_opp  = curriculum[0]
        anchor_opp = curriculum[0]
        stage_budgets = [
            args.anchor_steps if opp == anchor_opp else args.middle_steps
            for opp in curriculum
        ]
        # x2 pour absorber les safety caps (2x budget/stage en mode conditionnel)
        budget_mult = 2.0 if args.advance_mode == "conditional" else 1.0
        total_steps = int(sum(stage_budgets) * budget_mult)
        print(f"  [Custom] Curriculum: {curriculum}")
        print(f"  [Custom] Budgets:    {stage_budgets}  (total={total_steps:,})")
    elif args.curriculum:
        curriculum = list(reversed(CURRICULA[args.agent])) if args.reverse_curriculum else CURRICULA[args.agent]
        start_opp  = curriculum[0]
        # Conditional : amortit budget sur stages faciles (rapides) et durs (safety cap 2x).
        # 50% de marge globale pour gérer le pire cas où plusieurs stages saturent.
        budget_mult = 1.5 if args.advance_mode == "conditional" else 1.0
        total_steps = int(args.timesteps_per_stage * len(curriculum) * budget_mult)
        stage_budgets = None
    else:
        curriculum  = None
        start_opp   = args.opponent
        total_steps = args.timesteps
        stage_budgets = None

    print(f"\n{'='*60}")
    print(f"  Agent      : {args.agent.upper()}")
    print(f"  Opponent   : {start_opp}")
    print(f"  Curriculum : {curriculum or 'none'}")
    print(f"  Timesteps  : {total_steps:,}")
    print(f"  Workers    : {args.n_envs}")
    print(f"  Save dir   : {save_dir}")
    print(f"{'='*60}\n")

    # ── Build vectorised env ──────────────────────────────────────────────────

    # Workers inherit this env var → ddm_env.py redirects their stdout to devnull
    os.environ["DDM_RL_WORKER"] = "1"

    # Parse start_opp : supporte "rl:jin:6:D" → base "rl:jin" + faction/champion
    base_start_opp, f_opp_init, c_opp_init = _parse_opp_spec(start_opp)
    faction_opp_eff  = f_opp_init  if f_opp_init  is not None else args.faction_opp
    champion_opp_eff = c_opp_init  if c_opp_init  is not None else args.champion_opp

    # Side allocation: balanced (alternate A/B per worker) or all A (default).
    if args.balance_sides:
        sides = ["A" if i % 2 == 0 else "B" for i in range(args.n_envs)]
        print(f"  Side balance : {sides.count('A')} workers A + {sides.count('B')} workers B")
    else:
        sides = ["A"] * args.n_envs

    env_fns = [
        make_env_fn(
            opponent     = base_start_opp,
            faction_rl   = args.faction_rl,
            champion_rl  = args.champion_rl,
            faction_opp  = faction_opp_eff,
            champion_opp = champion_opp_eff,
            max_rounds   = args.max_rounds,
            bag_size     = args.bag_size,
            seed         = args.seed + i,
            rl_side      = sides[i],
        )
        for i in range(args.n_envs)
    ]

    vec_env = SubprocVecEnv(env_fns)
    vec_env = VecMonitor(vec_env)   # injects "episode" dict into info on done

    # ── Build or load model ───────────────────────────────────────────────────

    if args.load:
        print(f"[INFO] Resuming from {args.load}")
        model = PPO.load(args.load, env=vec_env, **{
            k: v for k, v in PPO_KWARGS.items()
            if k not in ("verbose",)
        })
        model.set_env(vec_env)
    else:
        model = PPO("MlpPolicy", vec_env, **PPO_KWARGS, seed=args.seed)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    wr_cb = WRCallback(
        agent_name          = args.agent,
        opponent            = start_opp,
        log_freq            = args.log_freq,
        save_dir            = save_dir,
        curriculum          = curriculum,
        advance_mode        = args.advance_mode,
        advance_wr          = args.advance_wr,
        timesteps_per_stage = args.timesteps_per_stage,
        stage_budgets       = stage_budgets,
        verbose             = 1,
    )

    checkpoint_cb = CheckpointCallback(
        save_freq   = max(50_000 // args.n_envs, 1),
        save_path   = str(save_dir),
        name_prefix = f"{args.agent}_{start_opp.replace(':','_')}",
        verbose     = 0,
    )

    # ── Train ─────────────────────────────────────────────────────────────────

    t0 = time.time()
    print(f"[INFO] Training started — {total_steps:,} total steps\n")

    _completed = False
    try:
        model.learn(
            total_timesteps = total_steps,
            callback        = [wr_cb, checkpoint_cb],
            progress_bar    = True,
            reset_num_timesteps = (args.load is None),
        )
        _completed = True
    except KeyboardInterrupt:
        print("\n[INFO] Training interrupted by user.")
    finally:
        tag = "final" if _completed else f"interrupted_{int(time.time())}"
        out = save_dir / f"{args.agent}_{start_opp.replace(':','_')}_{tag}.zip"
        model.save(str(out))
        print(f"\n[INFO] Model saved: {out}")
        vec_env.close()

    elapsed = time.time() - t0
    print(f"[INFO] Done in {elapsed/60:.1f} min  ({total_steps/elapsed:.0f} steps/s)")

    if _completed:
        sentinel = save_dir / f"{args.agent}.done"
        sentinel.touch()
        print(f"[INFO] Sentinel written: {sentinel}")

        if args.agent == "jaeha" and args.curriculum_random:
            import subprocess
            print("[INFO] Mise a jour matrice empirique Jaeha...")
            subprocess.run(
                [sys.executable, "-m", "rl.build_jaeha_empirical",
                 "--root", args.save_dir],
                check=False,
            )


if __name__ == "__main__":
    main()
