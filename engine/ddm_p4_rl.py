"""
ddm_p4_rl.py
Hooks Reinforcement Learning (optionnel — actif si DDM_RL=1).
Extrait de ddm_p4_loop.py lors du refacto 2026-02.

Dépendance desktop : rl/ddm_reward_v2.py (absent sur laptop = fallbacks neutres).
"""
from __future__ import annotations

import os
import time
from typing import Optional, Tuple

from .ddm_p1_core import (
    GameState, UNITS, log, _RL_QG_DMG_PENDING,
)
from .ddm_p3_mechanics import manhattan

# --- Import RL optionnel ---
try:
    from rl.ddm_reward_v2 import RewardCfg, RLLogger, compute_reward_12
except ImportError:
    RewardCfg = None      # type: ignore
    RLLogger = None       # type: ignore
    def compute_reward_12(*_a, **_k):  # type: ignore
        return 0.0, {}


# --- Helpers internes ---

def _rl_enabled() -> bool:
    return os.environ.get("DDM_RL", "0") == "1"


def _rl_pool_total(pool: dict) -> int:
    return int(sum(int(pool.get(k, 0) or 0) for k in ("MOVE", "ATK", "DEF", "CAP")))


def _rl_min_dist_to_hq(owner_char: str, hq_pos: Tuple[int, int]) -> int:
    try:
        hr, hc = hq_pos
        units = UNITS.get(owner_char, [])
        if not units:
            return 99
        return min(manhattan(u.row, u.col, hr, hc) for u in units)
    except Exception:
        return 99


def _rl_count_threats(attacker_char: str, target_hq_pos: Tuple[int, int], radius: int = 2) -> int:
    try:
        hr, hc = target_hq_pos
        units = UNITS.get(attacker_char, [])
        return sum(1 for u in units if manhattan(u.row, u.col, hr, hc) <= radius)
    except Exception:
        return 0


def _rl_adjacent_to_hq(owner_char: str, hq_pos: Tuple[int, int]) -> bool:
    try:
        hr, hc = hq_pos
        units = UNITS.get(owner_char, [])
        return any(manhattan(u.row, u.col, hr, hc) == 1 for u in units)
    except Exception:
        return False


def _rl_ally_intercept(owner_char: str, opp_char: str,
                        my_hq_pos: Tuple[int, int], height: int) -> bool:
    """
    Retourne True si au moins un ennemi a franchi la ligne médiane vers notre QG
    ET qu'une unité alliée est positionnée entre cet ennemi et notre QG
    (distance ennemi→QG > distance allié→QG sur le même axe).
    """
    try:
        mid = height // 2
        my_units  = UNITS.get(owner_char, [])
        opp_units = UNITS.get(opp_char, [])
        hq_r, hq_c = my_hq_pos

        # Infiltrateurs : ennemis dans notre moitié
        if owner_char == "A":
            infiltrators = [e for e in opp_units if e.hp > 0 and e.row > mid]
        else:
            infiltrators = [e for e in opp_units if e.hp > 0 and e.row < mid]

        if not infiltrators:
            return False

        # Pour chaque infiltrateur, vérifier qu'un allié est "entre" lui et le QG
        for inf in infiltrators:
            dist_inf = manhattan(inf.row, inf.col, hq_r, hq_c)
            for ally in my_units:
                if ally.hp <= 0:
                    continue
                dist_ally = manhattan(ally.row, ally.col, hq_r, hq_c)
                # L'allié est entre l'infiltrateur et le QG
                if dist_ally < dist_inf:
                    return True
        return False
    except Exception:
        return False


def _rl_terminal_for_player(state: GameState, player_char: str):
    try:
        if state.hq_A_hp > 0 and state.hq_B_hp > 0:
            return None
        my_hp = state.hq_A_hp if player_char == "A" else state.hq_B_hp
        opp_hp = state.hq_B_hp if player_char == "A" else state.hq_A_hp
        if opp_hp <= 0 and my_hp > 0:
            return "win"
        if my_hp <= 0 and opp_hp > 0:
            return "loss"
        if my_hp <= 0 and opp_hp <= 0:
            return "draw"
        return None
    except Exception:
        return None


# --- API publique ---

def rl_init_turn_ctx(state: GameState, player_char: str, turn_idx: int,
                     run_id: Optional[str] = None) -> None:
    """Initialise le contexte RL pour le tour courant. No-op si RL désactivé."""
    if not _rl_enabled():
        return
    try:
        opp = "B" if player_char == "A" else "A"
        ctx = {
            "enabled": True,
            "run_id": run_id,
            "game_id": getattr(state, "game_id", None),
            "turn_idx": int(turn_idx),
            "player": player_char,
            "opponent": opp,
            "dmg_qg": 0,
            "kills_enemy": 0,
            "losses_self": 0,
            "passed": False,
            "pass_avoidable": False,
            "useful_action_existed": False,
        }
        setattr(state, "rl_turn_ctx", ctx)

        # Mémoire inter-tours — persistante sur la durée de la partie par camp
        # Réinitialisée si game_id change (nouvelle partie)
        mem_attr = f"rl_memory_{player_char}"
        existing_mem = getattr(state, mem_attr, None)
        existing_gid = (existing_mem or {}).get("game_id")
        current_gid  = ctx.get("game_id")
        if existing_mem is None or existing_gid != current_gid:
            setattr(state, mem_attr, {
                "game_id"            : current_gid,
                "infiltrators_seen"  : set(),   # ids ennemis déjà détectés → one-shot
                "ally_intercept_prev": False,    # ally_intercept tour N-1 → option 2
                "aggro_seq"          : 0,        # tours offensifs consécutifs de l'adversaire
                "kill_turns"         : [],       # tours où l'adversaire a tué une de nos unités
            })

        if getattr(state, "rl_cfg", None) is None and RewardCfg is not None:
            setattr(state, "rl_cfg", RewardCfg())
        # Logger : recréer si run_id change (nouvelle partie dans la même session)
        existing_logger = getattr(state, "rl_logger", None)
        existing_rid = getattr(existing_logger, "run_id", None) if existing_logger else None
        effective_rid = run_id or os.environ.get("DDM_RL_RUN_ID") or None
        if RLLogger is not None and (existing_logger is None or existing_rid != effective_rid):
            setattr(state, "rl_logger", RLLogger(run_id=effective_rid))
    except Exception:
        return


def rl_after_roll_snapshot(state: GameState, player_char: str,
                            hq_A_pos: Tuple[int, int], hq_B_pos: Tuple[int, int]) -> None:
    """Snapshot des métriques après le lancer de dés."""
    if not _rl_enabled():
        return
    try:
        ctx = getattr(state, "rl_turn_ctx", None)
        if not (isinstance(ctx, dict) and ctx.get("enabled")):
            return
        opp = ctx.get("opponent") or ("B" if player_char == "A" else "A")
        pool = state.pool_A if player_char == "A" else state.pool_B
        ctx["start_pool_total"] = _rl_pool_total(pool)
        units_now = UNITS.get(player_char, [])
        ctx["units_count"] = len(units_now)
        ctx["useful_action_existed"] = bool(
            ctx["start_pool_total"] > 0 and ctx["units_count"] > 0
        )
        opp_hq = hq_B_pos if player_char == "A" else hq_A_pos
        my_hq = hq_A_pos if player_char == "A" else hq_B_pos
        ctx["min_dist_enemy_hq_start"] = _rl_min_dist_to_hq(player_char, opp_hq)
        ctx["hq_threats_start"] = _rl_count_threats(opp, my_hq, radius=2)
        # Snapshot HP QG adverse (pour delta dmg_qg en fin de tour)
        ctx["opp_hq_hp_start"] = state.hq_B_hp if player_char == "A" else state.hq_A_hp
        # Vider le pending dmg au début du tour (accumulation propre)
        _RL_QG_DMG_PENDING.clear()
    except Exception:
        return


def rl_finalize_turn(state: GameState, player_char: str,
                     hq_A_pos: Tuple[int, int], hq_B_pos: Tuple[int, int],
                     ended: bool = False,
                     run_id: Optional[str] = None) -> None:
    """Calcule la récompense et écrit le record JSONL. Ne doit jamais crasher la partie."""
    try:
        ctx = getattr(state, "rl_turn_ctx", None)
        if not (isinstance(ctx, dict) and ctx.get("enabled")):
            return

        opp = ctx.get("opponent") or ("B" if player_char == "A" else "A")
        pool = state.pool_A if player_char == "A" else state.pool_B

        opp_hq = hq_B_pos if player_char == "A" else hq_A_pos
        my_hq = hq_A_pos if player_char == "A" else hq_B_pos

        # Calcul dmg_qg : delta HP QG adverse depuis début du tour
        opp_hq_hp_now = state.hq_B_hp if player_char == "A" else state.hq_A_hp
        opp_hq_hp_start = float(ctx.get("opp_hq_hp_start", opp_hq_hp_now) or opp_hq_hp_now)
        ctx["dmg_qg"] = max(0, opp_hq_hp_start - opp_hq_hp_now)
        # Fallback : pending global (cas où snapshot manqué)
        if ctx["dmg_qg"] == 0 and _RL_QG_DMG_PENDING.get("char") == player_char:
            ctx["dmg_qg"] = float(_RL_QG_DMG_PENDING.get("dmg", 0) or 0)
        _RL_QG_DMG_PENDING.clear()

        end_total = _rl_pool_total(pool)
        ctx["unused_pool_total"] = end_total
        ctx["min_dist_enemy_hq_end"] = _rl_min_dist_to_hq(player_char, opp_hq)
        ctx["hq_threats_end"] = _rl_count_threats(opp, my_hq, radius=2)
        ctx["mate_threat"] = _rl_adjacent_to_hq(player_char, opp_hq)
        ctx["my_hq_reachable"] = _rl_adjacent_to_hq(opp, my_hq)
        # ally_intercept : un allié protège notre QG d'un infiltrateur
        try:
            from .ddm_p1_core import HEIGHT as _HEIGHT
        except Exception:
            _HEIGHT = 19
        ally_intercept_now = _rl_ally_intercept(player_char, opp, my_hq, _HEIGHT)
        ctx["ally_intercept"] = ally_intercept_now

        # --- Mémoire inter-tours ---
        mem = getattr(state, f"rl_memory_{player_char}", {})

        # Détection nouveaux infiltrateurs (one-shot)
        mid = _HEIGHT // 2
        opp_units_now = UNITS.get(opp, [])
        if player_char == "A":
            infiltrators_now = {id(e) for e in opp_units_now if e.hp > 0 and e.row > mid}
        else:
            infiltrators_now = {id(e) for e in opp_units_now if e.hp > 0 and e.row < mid}

        seen = mem.get("infiltrators_seen", set())
        new_infiltrators = infiltrators_now - seen
        ctx["new_infiltrator"] = len(new_infiltrators) > 0 and ally_intercept_now
        mem["infiltrators_seen"] = seen | infiltrators_now  # marquer comme vus

        # Interception réussie : kill ce tour ET ally_intercept était True le tour d'avant
        ctx["intercept_kill"] = (
            ctx.get("kills_enemy", 0) > 0
            and mem.get("ally_intercept_prev", False)
        )

        # Pattern offensif adverse : séquence de kills sur nos unités
        if ctx.get("losses_self", 0) > 0:
            mem["kill_turns"] = (mem.get("kill_turns") or [])[-9:] + [ctx.get("turn_idx", 0)]
            mem["aggro_seq"] = mem.get("aggro_seq", 0) + 1
        else:
            mem["aggro_seq"] = max(0, mem.get("aggro_seq", 0) - 1)

        ctx["aggro_seq"]      = mem.get("aggro_seq", 0)
        ctx["frozen_front"]   = mem.get("frozen_front", False)
        ctx["trident_active"] = mem.get("trident_active", False)
        ctx["turns_since_dmg"]= mem.get("turns_since_dmg", 0)
        # Reset trident_active après lecture (one-shot par détection)
        mem["trident_active"] = False
        setattr(state, f"rl_memory_{player_char}", mem)

        # Mettre à jour ally_intercept_prev APRÈS avoir lu l'état
        mem["ally_intercept_prev"] = ally_intercept_now
        setattr(state, f"rl_memory_{player_char}", mem)

        start_total = float(ctx.get("start_pool_total", 0) or 0)
        spent = start_total - end_total
        actions_done = int(ctx.get("actions_executed", -1))  # -1 = inconnu (HvIA)
        dmg_or_kill = (int(ctx.get("dmg_qg", 0) or 0)
                       + int(ctx.get("kills_enemy", 0) or 0))
        # void_action : aucune action exécutée alors que pool + ennemis existaient
        # On utilise actions_executed si dispo (IAIA), sinon fallback spent
        if actions_done >= 0:
            ctx["void_action"] = bool(
                actions_done == 0
                and start_total > 0
                and not ctx.get("pass_forced", False)
                and not ctx.get("mate_threat", False)
            )
        else:
            # Fallback HvIA : ancienne logique (spent+progress)
            ctx["void_action"] = bool(
                start_total > 0 and spent <= 0 and dmg_or_kill == 0
                and not ctx.get("mate_threat", False)
            )
        ctx["terminal"] = _rl_terminal_for_player(state, player_char)

        cfg = getattr(state, "rl_cfg", None)
        r, breakdown = compute_reward_12(ctx, cfg)

        logger = getattr(state, "rl_logger", None)
        if logger is None:
            logger = RLLogger(run_id=run_id or None)
            setattr(state, "rl_logger", logger)

        record = {
            "ts": time.time(),
            "run_id": ctx.get("run_id") or getattr(logger, "run_id", None),
            "game_id": ctx.get("game_id"),
            "turn_idx": ctx.get("turn_idx"),
            "player": player_char,
            "opponent": opp,
            "faction_A": getattr(state, "hero_A", {}).get("faction", "?"),
            "faction_B": getattr(state, "hero_B", {}).get("faction", "?"),
            "champion_A": getattr(state, "hero_A", {}).get("name", "?"),
            "champion_B": getattr(state, "hero_B", {}).get("name", "?"),
            "reward": r,
            "breakdown": breakdown,
            "features": {
                "dmg_qg": ctx.get("dmg_qg", 0),
                "kills_enemy": ctx.get("kills_enemy", 0),
                "losses_self": ctx.get("losses_self", 0),
                "mate_threat": ctx.get("mate_threat", False),
                "my_hq_reachable": ctx.get("my_hq_reachable", False),
                "hq_threats_start": ctx.get("hq_threats_start", 0),
                "hq_threats_end": ctx.get("hq_threats_end", 0),
                "min_dist_enemy_hq_start": ctx.get("min_dist_enemy_hq_start", 99),
                "min_dist_enemy_hq_end": ctx.get("min_dist_enemy_hq_end", 99),
                "unused_pool_total": ctx.get("unused_pool_total", 0),
                "useful_action_existed": ctx.get("useful_action_existed", False),
                "pass_forced": ctx.get("pass_forced", False),
                "pass_avoidable": ctx.get("pass_avoidable", False),
                "void_action": ctx.get("void_action", False),
                "units_count": ctx.get("units_count", 0),
                "ally_intercept": ctx.get("ally_intercept", False),
                "new_infiltrator": ctx.get("new_infiltrator", False),
                "intercept_kill": ctx.get("intercept_kill", False),
                "aggro_seq": ctx.get("aggro_seq", 0),
                "frozen_front": ctx.get("frozen_front", False),
                "trident_active": ctx.get("trident_active", False),
                "turns_since_dmg": ctx.get("turns_since_dmg", 0),
                "terminal": ctx.get("terminal"),
            },
            "hq": {"A": state.hq_A_hp, "B": state.hq_B_hp},
            "pool": dict(pool),
        }
        logger.write(record)
    except Exception:
        return
