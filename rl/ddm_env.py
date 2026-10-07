"""
rl/ddm_env.py  —  Gymnasium wrapper around the DDM engine.

One episode  = one full game.
One step     = one round (RL agent acts, then opponent acts).
Action space = MultiDiscrete([N_CMDS] * N_MAX)
  Commands per unit slot :
    0 = pass
    1 = advance toward enemy HQ (move + attack if adjacent)
    2 = hunt nearest enemy unit (move toward it + attack if adjacent)
    3 = attack only (adjacent enemy or adjacent HQ, no move)
    4 = use ability

Observation = flat float32 vector of size OBS_SIZE (340).
  - 20 scalars  : QG HP, pools, champion states, turn, territory
  - 320 units   : N_MAX slots per side × 10 features, zero-padded

Stdout suppression :
  Set DDM_AUTORUN=1 + DDM_CAPTURE_STDOUT=0 + DDM_PRINT_ROLL=0 before import.
  For full silence redirect subprocess stdout to os.devnull when using
  SubprocVecEnv — each worker is a separate process so it's safe.
"""
from __future__ import annotations

import os
import random
import importlib
from typing import Optional

import numpy as np

# Must be set before any engine import to suppress file logging & stdout
os.environ.setdefault("DDM_AUTORUN",         "1")
os.environ.setdefault("DDM_CAPTURE_STDOUT",  "0")
os.environ.setdefault("DDM_LOG_CANON",       "OFF")
os.environ.setdefault("DDM_PRINT_ROLL",      "0")

# Redirect stdout only in worker subprocesses (DDM_RL_WORKER=1).
# Suppresses unicode-crashing engine/LLM profile prints without silencing
# the main training process (WRCallback logs, progress bar, etc.)
import sys
if os.environ.get("DDM_RL_WORKER") == "1":
    import io as _io
    _devnull = _io.TextIOWrapper(_io.open(os.devnull, "wb"), encoding="utf-8")
    sys.stdout = _devnull

import gymnasium as gym
from gymnasium import spaces

import engine.ddm_p1_core as _core   # module ref keeps _core.FACTIONS_DATA live after reload

from engine.ddm_p1_core import (
    GameState, UNITS, HQ_POS, HEIGHT, WIDTH,
    P1_TILE, P2_TILE, P1_QG, P2_QG,
    load_factions_data, choose_faction, _RL_QG_DMG_PENDING,
)
from engine.ddm_p2_board_dice import (
    create_board, create_starter_dice, build_standard_dice_bag,
)
from engine.ddm_p3_mechanics import (
    manhattan, apply_damage_to_unit,
    find_enemy_adjacent, find_enemy_in_range,
    use_unit_ability, end_turn_tick,
    reset_units_for_new_mob_phase, get_unit_at,
)
from engine.ddm_p4_turn import roll_dice_for_player
from engine.ddm_p4_ai import phase_mobs_ai, pick_champion_letter
from engine.ddm_p4_rl import (
    _rl_min_dist_to_hq, _rl_count_threats,
    _rl_adjacent_to_hq, _rl_terminal_for_player,
)
from rl.ddm_reward_v2 import RewardCfg, compute_reward_12


# ── Constants ─────────────────────────────────────────────────────────────────

N_MAX        = 16   # unit padding per side (covers p99 of empirical distribution)
N_CMDS       = 5    # actions per unit slot
N_UNIT_FEATS = 10   # features per unit slot

_N_SCALARS = 20     # 2 QG HP + 8 pool + 6 champ-state + 1 turn + 3 territory
OBS_SIZE   = _N_SCALARS + N_MAX * N_UNIT_FEATS * 2  # = 340

_HQ_MAX   = 35
_POOL_MAX = 12
_HP_MAX   = 30   # safe upper-bound for unit HP normalisation


# ── Lazy profile registry ──────────────────────────────────────────────────────

_PROFILE_FNS: dict | None = None

_PROFILE_MAP = {
    # haiku = ancien "claude" renommé. Vrai Claude API sous claude_api.
    "haiku":       ("engine.ddm_p4_haiku",       "phase_mobs_haiku"),
    "mistral":     ("engine.ddm_p4_mistral",     "phase_mobs_mistral"),
    "grok":        ("engine.ddm_p4_grok",        "phase_mobs_grok"),
    "gemini":      ("engine.ddm_p4_gemini",      "phase_mobs_gemini"),
    "chatgpt":     ("engine.ddm_p4_chatgpt",     "phase_mobs_chatgpt"),
    "sonnet":      ("engine.ddm_p4_sonnet",      "phase_mobs_sonnet"),
    "opus":        ("engine.ddm_p4_opus",        "phase_mobs_opus"),
    "deepseek":    ("engine.ddm_p4_deepseek",    "phase_mobs_deepseek"),
    "qwen3":       ("engine.ddm_p4_qwen3",       "phase_mobs_qwen3"),
    "glm":         ("engine.ddm_p4_glm",         "phase_mobs_glm"),
    # Claude API direct (nécessite ANTHROPIC_API_KEY env var)
    "claude_api":  ("engine.ddm_p4_claude_api",  "phase_mobs_claude_api"),
}

# ── RL opponent registry (pour Neosia, Zenom, etc.) ─────────────────────────
# Permet d'utiliser un PPO pré-entraîné comme opponent via opponent="rl:<agent>".
# Les checkpoints sont chargés à la demande (lazy) et cachés par nom.
RL_AGENT_CKPT: dict[str, str] = {
    "jin":   "rl/checkpoints/v1.7/jin/jin_final.zip",         # v1.7 balanced (+11 pts)
    "jio":   "rl/checkpoints/v2/v2b/jio/jio_final.zip",       # v2b (rollback : v1.7 -12.7 pts)
    "cross": "rl/checkpoints/v1.7/cross/cross_final.zip",     # v1.7 balanced (mean ≈v2d, moins asymétrique)
    "jaeha": "rl/checkpoints/v1.7/jaeha/jaeha_final.zip",     # v1.7 balanced (+28 pts)
    "neosia":       "rl/checkpoints/neosia/neosia/neosia_final.zip",
    "zenom":        "rl/checkpoints/zenom/zenom/zenom_final.zip",
    "zenom_frozen": "rl/checkpoints/zenom/zenom/zenom_frozen.zip",
}

# Cache au niveau worker (chaque SubprocVecEnv worker a son propre cache).
_RL_MODELS_CACHE: dict[str, object] = {}


def _load_rl_opponent_model(agent_name: str):
    """Charge (et cache) un modèle PPO pour usage comme opponent."""
    if agent_name in _RL_MODELS_CACHE:
        return _RL_MODELS_CACHE[agent_name]
    if agent_name not in RL_AGENT_CKPT:
        raise ValueError(f"Unknown RL agent '{agent_name}'. Choices: {list(RL_AGENT_CKPT)}")
    from stable_baselines3 import PPO
    ckpt = RL_AGENT_CKPT[agent_name]
    model = PPO.load(ckpt, env=None)
    _RL_MODELS_CACHE[agent_name] = model
    return model


def _make_rl_opponent_fn(model, env: "DDMEnv"):
    """Wrappe un PPO model en fonction phase_mobs-compatible (state, owner, must_hq_fn).

    Swap temporairement env.rl_side pour que _build_obs / _run_rl_mob_phase
    travaillent du point de vue du owner (= côté joué par cet opponent RL).
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


def _build_profile_fns() -> dict:
    out = {"greedy": phase_mobs_ai}
    for tag, (mod_name, fn_name) in _PROFILE_MAP.items():
        try:
            mod = importlib.import_module(mod_name)
            out[tag] = getattr(mod, fn_name)
        except Exception:
            out[tag] = phase_mobs_ai  # graceful fallback
    return out


# ── DDMEnv ────────────────────────────────────────────────────────────────────

class DDMEnv(gym.Env):
    """
    Parameters
    ----------
    opponent : str
        "greedy" | "haiku" | "mistral" | "grok" | "gemini"
        | "chatgpt" | "sonnet" | "opus"
    rl_side : "A" | "B"
        Camp controlled by the RL agent. "A" is canonical (recommended).
    faction_rl / faction_opp : int | None
        Faction IDs. None = random each episode.
    champion_rl / champion_opp : str | None
        Champion letter ("A".."E"). None = random.
    max_rounds : int
        Hard per-episode cap (default 120).
    bag_size : int
        Dice bag size (11 or 22).
    reward_cfg : RewardCfg | None
        Custom reward weights. None = defaults.
    seed : int | None
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        opponent:     str            = "greedy",
        rl_side:      str            = "A",
        faction_rl:   Optional[int]  = None,
        champion_rl:  Optional[str]  = None,
        faction_opp:  Optional[int]  = None,
        champion_opp: Optional[str]  = None,
        max_rounds:   int            = 120,
        bag_size:     int            = 11,
        reward_cfg:   Optional[RewardCfg] = None,
        seed:         Optional[int]  = None,
    ):
        super().__init__()

        assert rl_side in ("A", "B"), "rl_side must be 'A' or 'B'"

        self.opponent     = opponent.lower()
        self.rl_side      = rl_side
        self.opp_side     = "B" if rl_side == "A" else "A"
        self.faction_rl   = faction_rl
        self.champion_rl  = champion_rl
        self.faction_opp  = faction_opp
        self.champion_opp = champion_opp
        self.max_rounds   = max_rounds
        self.bag_size     = bag_size
        self.reward_cfg   = reward_cfg or RewardCfg()
        self._rng         = random.Random(seed)

        self.action_space      = spaces.MultiDiscrete([N_CMDS] * N_MAX)
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(OBS_SIZE,), dtype=np.float32,
        )

        # Runtime state (initialised in reset)
        self.state:  Optional[GameState] = None
        self.dice_A: list = []
        self.dice_B: list = []
        self._round  = 0
        self._snap:  dict = {}

        if not _core.FACTIONS_DATA:
            load_factions_data()

    # ── reset ─────────────────────────────────────────────────────────────────

    def reset(self, seed=None, options=None):
        if seed is not None:
            self._rng = random.Random(seed)

        # Clear module-level globals (safe because SubprocVecEnv isolates processes)
        UNITS["A"].clear()
        UNITS["B"].clear()
        _RL_QG_DMG_PENDING.clear()

        fids = [int(f["id"]) for f in _core.FACTIONS_DATA
                if isinstance(f, dict) and f.get("id") is not None]

        fid_rl  = self.faction_rl  or self._rng.choice(fids)
        fid_opp = self.faction_opp or self._rng.choice(fids)
        ch_rl   = self.champion_rl  or pick_champion_letter(fid_rl,  _core.FACTIONS_DATA)
        ch_opp  = self.champion_opp or pick_champion_letter(fid_opp, _core.FACTIONS_DATA)

        # Store for info tracking
        self._fid_rl  = fid_rl
        self._ch_rl   = ch_rl
        self._fid_opp = fid_opp
        self._ch_opp  = ch_opp

        if self.rl_side == "A":
            fA = choose_faction(fid_rl,  ch_rl)
            fB = choose_faction(fid_opp, ch_opp)
        else:
            fA = choose_faction(fid_opp, ch_opp)
            fB = choose_faction(fid_rl,  ch_rl)

        board      = create_board()
        self.state = GameState(board, fA, fB)
        self.state.max_rounds = self.max_rounds

        catalog    = create_starter_dice()
        self.dice_A = build_standard_dice_bag(catalog, self.bag_size)
        self.dice_B = build_standard_dice_bag(catalog, self.bag_size)
        self._round = 0
        self._snap  = {}

        return self._build_obs(), {}

    # ── step ──────────────────────────────────────────────────────────────────

    def step(self, action):
        state = self.state
        rl    = self.rl_side
        opp   = self.opp_side

        # ── RL agent half-turn ────────────────────────────────────────────────

        state.current_player = 1 if rl == "A" else 2
        state.turn = self._round

        # Roll dice + automated invocation (AI logic, DDM_AUTORUN=1)
        rl_bag = self.dice_A if rl == "A" else self.dice_B
        roll_dice_for_player(state, rl_bag, 1 if rl == "A" else 2)

        # Snapshot before mob phase (used in reward)
        self._take_snap(state, rl, opp)

        # Execute RL mob phase
        self._run_rl_mob_phase(action, state, rl, opp)

        # Check: RL destroyed opponent HQ
        if self._terminal(state):
            r = self._reward(state, rl, opp, terminal=True)
            end_turn_tick(state)
            return self._build_obs(), r, True, False, self._info(state)

        end_turn_tick(state)

        # ── Opponent half-turn ────────────────────────────────────────────────

        state.current_player = 2 if rl == "A" else 1
        state.turn = self._round

        opp_bag = self.dice_B if rl == "A" else self.dice_A
        roll_dice_for_player(state, opp_bag, 2 if rl == "A" else 1)

        self._get_opp_fn()(state, opp, lambda s: HQ_POS[s])

        # Check: opponent destroyed RL HQ
        if self._terminal(state):
            r = self._reward(state, rl, opp, terminal=True)
            end_turn_tick(state)
            self._round += 1
            return self._build_obs(), r, True, False, self._info(state)

        end_turn_tick(state)
        self._round += 1

        truncated = self._round >= self.max_rounds
        r = self._reward(state, rl, opp, terminal=False)
        return self._build_obs(), r, False, truncated, self._info(state)

    # ── RL mob phase ──────────────────────────────────────────────────────────

    def _run_rl_mob_phase(self, action, state, rl: str, opp: str):
        pool = state.pool_A if rl == "A" else state.pool_B
        reset_units_for_new_mob_phase(rl)

        # Champion despair trigger (same as existing mob phases)
        try:
            from engine.ddm_p4_human import (
                maybe_trigger_despair_champion,
                maybe_trigger_despair_champion_A,
            )
            if rl == "A":
                maybe_trigger_despair_champion_A(state, "A", lambda s: HQ_POS[s])
            else:
                maybe_trigger_despair_champion(state, "B", lambda s: HQ_POS[s])
        except Exception:
            pass

        opp_hq = HQ_POS.get(opp) or (0, WIDTH // 2)

        # Sort units by distance to enemy HQ (closest = highest threat = slot 0)
        # Matches the sort order used in _build_obs so action[i] → obs unit slot i
        units = [u for u in UNITS[rl] if getattr(u, "hp", 0) > 0]
        units.sort(key=lambda u: manhattan(u.row, u.col, opp_hq[0], opp_hq[1]))

        for slot, cmd in enumerate(action):
            if slot >= len(units):
                break
            self._exec_cmd(int(cmd), units[slot], state, pool, rl, opp, opp_hq)

    def _exec_cmd(self, cmd: int, unit, state, pool, rl: str, opp: str, opp_hq: tuple):
        if cmd == 0:  # pass
            return

        if cmd == 3:  # attack only (no move)
            if not unit.has_attacked:
                self._try_attack(unit, state, pool, rl, opp)
                unit.has_attacked = True
            return

        if cmd == 4:  # ability
            if not unit.has_attacked and unit.has_ability:
                try:
                    if use_unit_ability(state, unit, rl):
                        unit.ability_uses_this_turn += 1
                except Exception:
                    pass
            return

        # cmd 1 or 2: resolve move target then move + attack
        if cmd == 1:
            target = opp_hq
        else:  # cmd == 2: hunt nearest enemy
            nearest = find_enemy_in_range(rl, unit.row, unit.col, rng=HEIGHT + WIDTH)
            target  = (nearest.row, nearest.col) if nearest else opp_hq

        if not unit.has_moved:
            move_pts = int(pool.get("MOVE", 0))
            for _ in range(move_pts):
                if not self._step_unit(unit, target[0], target[1], state.board):
                    break
                pool["MOVE"] = max(0, pool.get("MOVE", 0) - 1)
            unit.has_moved = True

        if not unit.has_attacked:
            self._try_attack(unit, state, pool, rl, opp)
            unit.has_attacked = True

    def _try_attack(self, unit, state, pool, rl: str, opp: str):
        if pool.get("ATK", 0) <= 0:
            return
        # Priority 1: adjacent enemy unit
        adj = find_enemy_adjacent(rl, unit.row, unit.col)
        if adj and getattr(adj, "hp", 0) > 0:
            apply_damage_to_unit(state, adj, unit.atk, source_tag="rl")
            pool["ATK"] = max(0, pool.get("ATK", 0) - 1)
            return
        # Priority 2: adjacent enemy HQ
        opp_hq = HQ_POS.get(opp)
        if opp_hq and manhattan(unit.row, unit.col, opp_hq[0], opp_hq[1]) == 1:
            state.damage_hq(opp, unit.atk, tag="rl", attacker_pos=(unit.row, unit.col))
            pool["ATK"] = max(0, pool.get("ATK", 0) - 1)

    @staticmethod
    def _step_unit(unit, target_r: int, target_c: int, board) -> bool:
        """Move unit one cell toward target. Returns True if it moved."""
        dr = target_r - unit.row
        dc = target_c - unit.col
        if dr == 0 and dc == 0:
            return False

        if abs(dr) >= abs(dc):
            primary   = (unit.row + (1 if dr > 0 else -1), unit.col)
            secondary = (unit.row, unit.col + (1 if dc > 0 else (-1 if dc < 0 else 0)))
        else:
            primary   = (unit.row, unit.col + (1 if dc > 0 else -1))
            secondary = (unit.row + (1 if dr > 0 else (-1 if dr < 0 else 0)), unit.col)

        for nr, nc in (primary, secondary):
            if not (0 <= nr < HEIGHT and 0 <= nc < WIDTH):
                continue
            cell = board[nr][nc]
            if cell in (P1_QG, P2_QG):
                continue
            occupant, _ = get_unit_at(nr, nc)
            if occupant is None:
                unit.row, unit.col = nr, nc
                return True
        return False

    # ── Reward ────────────────────────────────────────────────────────────────

    def _take_snap(self, state, rl: str, opp: str):
        opp_hq = HQ_POS.get(opp, (0, WIDTH // 2))
        my_hq  = HQ_POS.get(rl,  (HEIGHT - 1, WIDTH // 2))
        self._snap = {
            "opp_hq_hp":         state.hq_B_hp if rl == "A" else state.hq_A_hp,
            "min_dist_enemy_hq": _rl_min_dist_to_hq(rl,  opp_hq),
            "hq_threats":        _rl_count_threats(opp, my_hq, radius=2),
        }

    def _reward(self, state, rl: str, opp: str, terminal: bool) -> float:
        opp_hq = HQ_POS.get(opp, (0, WIDTH // 2))
        my_hq  = HQ_POS.get(rl,  (HEIGHT - 1, WIDTH // 2))
        pool   = state.pool_A if rl == "A" else state.pool_B

        opp_hp_now = state.hq_B_hp if rl == "A" else state.hq_A_hp
        dmg_qg     = max(0.0, float(self._snap.get("opp_hq_hp", opp_hp_now)) - opp_hp_now)

        ctx = {
            "dmg_qg":                 dmg_qg,
            "mate_threat":            _rl_adjacent_to_hq(rl,  opp_hq),
            "kills_enemy":            0,
            "losses_self":            0,
            "my_hq_reachable":        _rl_adjacent_to_hq(opp, my_hq),
            "new_infiltrator":        False,
            "intercept_kill":         False,
            "hq_threats_start":       float(self._snap.get("hq_threats", 0)),
            "hq_threats_end":         float(_rl_count_threats(opp, my_hq, radius=2)),
            "min_dist_enemy_hq_start": float(self._snap.get("min_dist_enemy_hq", 99)),
            "min_dist_enemy_hq_end":  float(_rl_min_dist_to_hq(rl, opp_hq)),
            "void_action":            False,
            "pass_avoidable":         False,
            "unused_pool_total":      float(sum(pool.get(k, 0) for k in ("ATK","DEF","MOVE","CAP"))),
            "terminal":               _rl_terminal_for_player(state, rl) if terminal else None,
            "pass_forced":            False,
        }

        reward, _ = compute_reward_12(ctx, self.reward_cfg)
        return float(reward)

    # ── Observation ───────────────────────────────────────────────────────────

    def _build_obs(self) -> np.ndarray:
        state = self.state
        rl    = self.rl_side
        opp   = self.opp_side
        obs   = np.zeros(OBS_SIZE, dtype=np.float32)
        i     = 0

        # ── Scalars (20) ──────────────────────────────────────────────────────

        my_qg  = state.hq_A_hp if rl == "A" else state.hq_B_hp
        opp_qg = state.hq_B_hp if rl == "A" else state.hq_A_hp
        obs[i] = max(0.0, my_qg  / _HQ_MAX);  i += 1
        obs[i] = max(0.0, opp_qg / _HQ_MAX);  i += 1

        my_pool  = state.pool_A if rl == "A" else state.pool_B
        opp_pool = state.pool_B if rl == "A" else state.pool_A
        for k in ("ATK", "DEF", "MOVE", "CAP"):
            obs[i] = min(1.0, my_pool.get(k, 0)  / _POOL_MAX); i += 1
        for k in ("ATK", "DEF", "MOVE", "CAP"):
            obs[i] = min(1.0, opp_pool.get(k, 0) / _POOL_MAX); i += 1

        # Champion states — one-hot (dormant / deployed / dead)
        my_cs  = state.champion_A_state if rl == "A" else state.champion_B_state
        opp_cs = state.champion_B_state if rl == "A" else state.champion_A_state
        for cs in (my_cs, opp_cs):
            obs[i]   = 1.0 if cs == "dormant"  else 0.0; i += 1
            obs[i]   = 1.0 if cs == "deployed" else 0.0; i += 1
            obs[i]   = 1.0 if cs == "dead"     else 0.0; i += 1

        obs[i] = min(1.0, self._round / max(1, self.max_rounds)); i += 1

        # Territory
        my_tile  = P1_TILE if rl == "A" else P2_TILE
        opp_tile = P2_TILE if rl == "A" else P1_TILE
        total    = HEIGHT * WIDTH
        my_cnt   = sum(1 for r in range(HEIGHT) for c in range(WIDTH)
                       if state.board[r][c] == my_tile)
        opp_cnt  = sum(1 for r in range(HEIGHT) for c in range(WIDTH)
                       if state.board[r][c] == opp_tile)
        my_hq_r  = (HQ_POS.get(rl) or (HEIGHT - 1, WIDTH // 2))[0]
        my_half  = range(HEIGHT // 2, HEIGHT) if my_hq_r >= HEIGHT // 2 else range(HEIGHT // 2)
        invasion = sum(1 for r in my_half for c in range(WIDTH)
                       if state.board[r][c] == opp_tile)
        obs[i] = my_cnt  / total;                      i += 1
        obs[i] = opp_cnt / total;                      i += 1
        obs[i] = invasion / max(1, total // 2);        i += 1
        # Running total: 2+8+6+1+3 = 20 ✓

        # ── Units (320) ───────────────────────────────────────────────────────

        opp_hq = HQ_POS.get(opp) or (0 if opp == "B" else HEIGHT - 1, WIDTH // 2)

        for side in (rl, opp):
            alive = [u for u in UNITS[side] if getattr(u, "hp", 0) > 0]
            # Closest to enemy HQ first — action[slot] maps to this ordering
            alive.sort(key=lambda u: manhattan(u.row, u.col, opp_hq[0], opp_hq[1]))

            for slot in range(N_MAX):
                if slot < len(alive):
                    u = alive[slot]
                    obs[i] = u.row / (HEIGHT - 1);                           i += 1
                    obs[i] = u.col / (WIDTH  - 1);                           i += 1
                    obs[i] = max(0.0, min(1.0, u.hp / _HP_MAX));             i += 1
                    obs[i] = min(1.0, u.atk / 10.0);                         i += 1
                    obs[i] = min(1.0, getattr(u, "defense", 0) / 10.0);      i += 1
                    obs[i] = (getattr(u, "level", 1) - 1) / 4.0;             i += 1
                    obs[i] = 1.0 if getattr(u, "is_champion", False) else 0.0; i += 1
                    obs[i] = 1.0 if u.has_moved    else 0.0;                 i += 1
                    obs[i] = 1.0 if u.has_attacked else 0.0;                 i += 1
                    obs[i] = 1.0;                                             i += 1  # alive
                else:
                    i += N_UNIT_FEATS  # zero-padded dead slot

        assert i == OBS_SIZE, f"obs size mismatch: {i} != {OBS_SIZE}"
        return obs

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _terminal(self, state) -> bool:
        return state.hq_A_hp <= 0 or state.hq_B_hp <= 0

    def _info(self, state) -> dict:
        return {
            "hq_A":      state.hq_A_hp,
            "hq_B":      state.hq_B_hp,
            "round":     self._round,
            "units_A":   len(UNITS["A"]),
            "units_B":   len(UNITS["B"]),
            "faction_rl":  getattr(self, "_fid_rl",  None),
            "champion_rl": getattr(self, "_ch_rl",   None),
            "faction_opp": getattr(self, "_fid_opp", None),
            "champion_opp":getattr(self, "_ch_opp",  None),
        }

    def _get_opp_fn(self):
        # RL opponent : opponent="rl:<agent>" → wrap un PPO model en phase_mobs-compatible
        if self.opponent.startswith("rl:"):
            agent_name = self.opponent[3:]
            # Cache le wrapper sur self pour éviter de re-load à chaque tour
            cached_name = getattr(self, "_rl_opp_cached_name", None)
            if cached_name != agent_name:
                model = _load_rl_opponent_model(agent_name)
                self._rl_opp_fn = _make_rl_opponent_fn(model, self)
                self._rl_opp_cached_name = agent_name
            return self._rl_opp_fn

        global _PROFILE_FNS
        if _PROFILE_FNS is None:
            _PROFILE_FNS = _build_profile_fns()
        return _PROFILE_FNS.get(self.opponent, phase_mobs_ai)

    def render(self):
        pass  # visual output suppressed in RL mode
