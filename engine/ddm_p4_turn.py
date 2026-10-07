"""
ddm_p4_turn.py
Lancer de dés, invocation, play_turn.
Extrait de ddm_p4_loop.py lors du refacto 2026-02.
"""
from __future__ import annotations

import os
import re
import time
import pathlib
import random as _random
from typing import Tuple, Optional


# Pause file (signal du renderer Pygame). Si présent, le moteur bloque entre tours.
_PAUSE_PATH = pathlib.Path(__file__).parent / "snapshots" / "pause.json"


def _wait_if_paused():
    """Bloque tant que pause.json existe dans snapshots/ (créé par le renderer)."""
    if not _PAUSE_PATH.exists():
        return
    print("[ENGINE] Pause demandee par le renderer...")
    while _PAUSE_PATH.exists():
        time.sleep(0.25)
    print("[ENGINE] Reprise.")

from .ddm_p1_core import (
    GameState, UNITS, log, canon_log,
)
from .ddm_p2_board_dice import (
    render_ui, create_starter_dice, build_standard_dice_bag,
    add_to_pool,
)
from .ddm_p3_mechanics import (
    compute_invocation, end_turn_tick, manhattan,
    attempt_place_invocation,
)
from .ddm_p4_ai import phase_mobs_ai
from .ddm_p4_human import phase_mobs_human
from .ddm_p4_rl import rl_init_turn_ctx, rl_after_roll_snapshot, rl_finalize_turn, _rl_enabled


# ----------------------------------------------------------------------
#  Helpers dés (compat dict/classe Die)
# ----------------------------------------------------------------------

def _die_get(die, key, default=None):
    if isinstance(die, dict):
        return die.get(key, default)
    return getattr(die, key, default)


def _die_level_int(die) -> int:
    v = _die_get(die, "level", 0)
    if isinstance(v, int):
        return v
    if v is None:
        return 0
    s = str(v)
    m = re.search(r"\d+", s)
    return int(m.group()) if m else 0


def _roll_die_compat(die, rng):
    if hasattr(die, "roll") and callable(getattr(die, "roll")):
        try:
            return die.roll(rng)
        except TypeError:
            return die.roll()
    try:
        from .ddm_p2_board_dice import roll_die
        return roll_die(die, rng)
    except Exception:
        pass
    try:
        from .ddm_p2_board_dice import roll_die
        return roll_die(die)
    except Exception:
        return "MOVE"


def _make_dice_bag_compat(bag_size: int = 11):
    base = create_starter_dice()
    return build_standard_dice_bag(base, bag_size)


# ----------------------------------------------------------------------
#  LANCER DE DÉS
# ----------------------------------------------------------------------

def roll_dice_for_player(state: GameState, dice_bag: list, player_id: int) -> None:
    """Tire 3 dés, met à jour le pool, décide une invocation si ≥2 ⭐ et place la shape."""
    player_char = "A" if player_id == 1 else "B"
    pool = state.pool_A if player_id == 1 else state.pool_B
    rng = getattr(state, "rng", None) or getattr(state, "random", None) or _random

    log(f"ROLL_START player={player_char}")

    env_pr = os.environ.get("DDM_PRINT_ROLL", None)
    if env_pr is None:
        print_roll = (os.environ.get("DDM_AUTORUN", "0") != "1")
    else:
        print_roll = (env_pr == "1")

    rolls = []
    star_hits = []
    for _i in range(3):
        if not dice_bag:
            dice_bag.extend(_make_dice_bag_compat(getattr(state, "bag_size", 11)))
            log(f"BAG_REFILL player={player_char} reason=empty")

        die = rng.choice(dice_bag)
        dice_bag.remove(die)
        face = _roll_die_compat(die, rng)

        rolls.append((die, face))

        if face == "ATK":
            add_to_pool(pool, "ATK", 1)
        elif face == "DEF":
            add_to_pool(pool, "DEF", 1)
        elif face == "MOVE":
            add_to_pool(pool, "MOVE", 1)
        elif face == "CAP":
            add_to_pool(pool, "CAP", 1)

        if face == "STAR":
            star_hits.append((die, face))

        log(f"ROLL {player_char}: {_die_get(die,'name','?')}({_die_get(die,'level','?')}) -> {face}")

    stars = len(star_hits)

    if print_roll:
        print(f"\n=== Lancé de dés (Joueur {player_char}) ===")
        for die, face in rolls:
            print(f"- {_die_get(die,'name','?')} ({_die_get(die,'level','?')}) → {face}")
        print(f"Pool {player_char} après Lancé : ATK={pool.get('ATK',0)} MOVE={pool.get('MOVE',0)} "
              f"DEF={pool.get('DEF',0)} CAP={pool.get('CAP',0)}")

    # Log snapshot — lancer de dés
    try:
        from .ddm_snapshot import log_append as _la
        _la(state, f"[DÉS] Joueur {player_char} : " +
            " | ".join(f"{_die_get(d,'name','?')} Lv{_die_get(d,'level','?')} → {f}"
                       for d, f in rolls))
        pool_str = f"MOVE={pool.get('MOVE',0)} ATK={pool.get('ATK',0)} DEF={pool.get('DEF',0)} CAP={pool.get('CAP',0)}"
        _la(state, f"[POOL] {player_char} → {pool_str}")
    except Exception:
        pass

    # Stocke les dés lancés sur state pour sérialisation snapshot
    if player_id == 1:
        state.last_rolled_A = [d for d, f in rolls]
        state.last_faces_A  = [f for d, f in rolls]
    else:
        state.last_rolled_B = [d for d, f in rolls]
        state.last_faces_B  = [f for d, f in rolls]

    # --- STATE tag ---
    try:
        from .ddm_p1_core import HQ_POS, P1_TILE, P2_TILE, HEIGHT, WIDTH
        enemy = "B" if player_char == "A" else "A"
        qg_hp = state.hq_A_hp if player_char == "A" else state.hq_B_hp

        units_count = sum(1 for u in UNITS[player_char] if getattr(u, "hp", 0) > 0)

        hq_pos = HQ_POS.get(player_char)
        hq_r, hq_c = hq_pos if hq_pos else (0, 0)
        threat_qg = sum(
            1 for u in UNITS[enemy]
            if getattr(u, "hp", 0) > 0 and manhattan(u.row, u.col, hq_r, hq_c) <= 2
        )

        tile_ch = P1_TILE if player_char == "A" else P2_TILE
        rows = [r for r in range(HEIGHT) for c in range(WIDTH) if state.board[r][c] == tile_ch]
        ehq_pos = HQ_POS.get(enemy)
        ehq_r = ehq_pos[0] if ehq_pos else 0
        forward = 1 if ehq_r > hq_r else -1
        lane = ((max(rows) - hq_r) if forward == 1 else (hq_r - min(rows))) if rows else 0

        log(
            f"STATE_{player_char} stars={stars} qg_hp={qg_hp} units={units_count} "
            f"pool_move={pool.get('MOVE',0)} pool_atk={pool.get('ATK',0)} "
            f"pool_def={pool.get('DEF',0)} pool_cap={pool.get('CAP',0)}"
        )
        canon_log(
            "STATE",
            player=player_char, stars=stars, threat_qg=threat_qg, lane=lane,
            pool={k: pool.get(k, 0) for k in ("ATK", "DEF", "MOVE", "CAP")},
            units=units_count,
        )
    except Exception:
        pass

    # --- Invocation ---
    invoc_level, rule_name, info = compute_invocation(star_hits)

    if invoc_level is None:
        log(f"INVOKE_DECISION player={player_char} stars={stars} action=none")
        canon_log("INVOKE_DECISION", player=player_char, stars=stars, action="none")
        log(f"INVOC_NONE player={player_char} stars={stars}")
        state.pending_invoc_level = None   # efface tout résidu du tour précédent
        if print_roll:
            print("Pas assez d'étoiles pour invoquer.")
        try:
            from .ddm_snapshot import log_append as _la
            _la(state, f"[INVOC] {player_char} : pas assez d'étoiles ({stars}★)")
        except Exception:
            pass
        return

    log(f"INVOKE_DECISION player={player_char} stars={stars} action=invoke_L{invoc_level}")
    canon_log("INVOKE_DECISION", player=player_char, stars=stars, action=f"invoke_L{invoc_level}")

    # Mode GUI : délègue l'invocation au command_reader
    _ddm_mode = os.environ.get("DDM_MODE", "cli")
    if _ddm_mode == "gui" and player_id == 1:
        # Réinitialise moved/attacked AVANT le snapshot pour que le renderer voie l'état correct
        try:
            from .ddm_p3_mechanics import reset_units_for_new_mob_phase as _reset
            _reset(player_char)
        except Exception:
            pass
        # Écrire le snapshot ICI — avant le wait, pour que le renderer voie les dés
        try:
            from .ddm_snapshot import write_snapshot as _ws
            from .ddm_p1_core import UNITS as _UNITS
            _turn_num = getattr(state, "turn", 1)
            state.pending_invoc_level = invoc_level
            _ws(state, state.board, _UNITS, _turn_num, player_char,
                dice_bag_A=dice_bag if player_id == 1 else [],
                dice_bag_B=[] if player_id == 1 else dice_bag)
        except Exception as _e:
            print(f"[GUI] Snapshot pre-invoc erreur : {_e}")
        try:
            from .ddm_p4_human_gui import phase_invocation_gui
            success = phase_invocation_gui(state, player_id, dice_bag, star_hits, invoc_level)
        except Exception as e:
            print(f"[GUI] Erreur phase_invocation_gui : {e}")
            success = False
    else:
        success = attempt_place_invocation(state.board, player_id, invoc_level, state)

    # Toujours effacer le flag — l'invoc est terminée (succès ou échec)
    state.pending_invoc_level = None

    if not success:
        log(f"INVOKE_RESULT player={player_char} level={invoc_level} success=0")
        for d, _f in star_hits:
            dice_bag.append(d)
        log(f"INVOC_FAIL_RETURN_STAR player={player_char} stars_returned={stars}")
        try:
            from .ddm_snapshot import log_append as _la
            _la(state, f"[INVOC] {player_char} Lv{invoc_level} : échec (pas de place)")
        except Exception:
            pass
        return

    log(f"INVOKE_RESULT player={player_char} level={invoc_level} success=1")
    try:
        from .ddm_snapshot import log_append as _la
        _la(state, f"[INVOC] {player_char} Lv{invoc_level} invoqué ({stars}★)")
    except Exception:
        pass

    if star_hits:
        if rule_name == "rituel_noir":
            die_to_consume = max(star_hits, key=lambda t: _die_level_int(t[0]))[0]
        else:
            # Règle dure : ne jamais consommer le L5-Noir pour une invoc non-rituel
            # Le L5 est irremplaçable — le sacrifier ferme la porte aux élites pour toujours
            non_l5 = [t for t in star_hits if _die_level_int(t[0]) < 5]
            candidates = non_l5 if non_l5 else star_hits  # fallback si L5 seul dé étoile
            die_to_consume = min(candidates, key=lambda t: _die_level_int(t[0]))[0]
        for d, _f in star_hits:
            if d is not die_to_consume:
                dice_bag.append(d)
        log(f"INVOC_CONSUME player={player_char} rule={rule_name} consumed={_die_get(die_to_consume,'name','?')}")


# ----------------------------------------------------------------------
#  DISPATCH IA
# ----------------------------------------------------------------------

_AI_REGISTRY = {
    # Heuristique "haiku" = ancien "claude" renommé. Le vrai Claude API est sous claude_api.
    "haiku":   ("ddm_p4_haiku",   "phase_mobs_haiku"),
    "sonnet":  ("ddm_p4_sonnet",  "phase_mobs_sonnet"),
    "opus":    ("ddm_p4_opus",    "phase_mobs_opus"),
    "chatgpt": ("ddm_p4_chatgpt", "phase_mobs_chatgpt"),
    "mistral": ("ddm_p4_mistral", "phase_mobs_mistral"),
    "gemini":  ("ddm_p4_gemini",  "phase_mobs_gemini"),
    "grok":    ("ddm_p4_grok",    "phase_mobs_grok"),
    "deepseek":("ddm_p4_deepseek","phase_mobs_deepseek"),
    "qwen3":   ("ddm_p4_qwen3",   "phase_mobs_qwen3"),
    "glm":     ("ddm_p4_glm",     "phase_mobs_glm"),
    # claude_api : appel direct API Anthropic (nécessite ANTHROPIC_API_KEY)
    "claude_api": ("ddm_p4_claude_api", "phase_mobs_claude_api"),
}

# RL agents — chargés via PPO checkpoint, wrappés en phase_mobs compatible.
# Synchroniser avec rl/ddm_env.py:RL_AGENT_CKPT et rl/bracket.py:AGENT_CKPT.
_RL_AGENT_CKPT = {
    "jin":    "rl/checkpoints/v1.7/jin/jin_final.zip",
    "jio":    "rl/checkpoints/v2/v2b/jio/jio_final.zip",
    "cross":  "rl/checkpoints/v1.7/cross/cross_final.zip",
    "jaeha":  "rl/checkpoints/v1.7/jaeha/jaeha_final.zip",
    "neosia":       "rl/checkpoints/neosia/neosia/neosia_final.zip",
    "zenom":        "rl/checkpoints/zenom/zenom/zenom_final.zip",
    "zenom_frozen": "rl/checkpoints/zenom/zenom/zenom_frozen.zip",
}

# Cache des modèles RL (évite re-load à chaque tour)
_RL_MODEL_CACHE: dict = {}
_RL_ENV_CACHE = None  # DDMEnv réutilisé pour _build_obs / _run_rl_mob_phase


def _get_rl_env():
    """Lazy-create un DDMEnv réutilisable (sans reset) pour ses méthodes obs/action."""
    global _RL_ENV_CACHE
    if _RL_ENV_CACHE is None:
        from rl.ddm_env import DDMEnv
        _RL_ENV_CACHE = DDMEnv(opponent="greedy")  # opponent ignoré (on injecte le state)
    return _RL_ENV_CACHE


def _load_rl_model(agent_name: str):
    """Charge (et cache) un PPO model pour usage comme adversaire IA."""
    if agent_name in _RL_MODEL_CACHE:
        return _RL_MODEL_CACHE[agent_name]
    if agent_name not in _RL_AGENT_CKPT:
        raise ValueError(f"Agent RL inconnu : '{agent_name}'. Choices: {list(_RL_AGENT_CKPT)}")
    from stable_baselines3 import PPO
    ckpt = _RL_AGENT_CKPT[agent_name]
    model = PPO.load(ckpt, env=None)
    _RL_MODEL_CACHE[agent_name] = model
    return model


def _phase_mobs_rl(state: GameState, owner: str, must_hq_fn, agent_name: str) -> bool:
    """Phase mobs pilotée par un PPO. Compatible signature phase_mobs_X."""
    try:
        env = _get_rl_env()
        model = _load_rl_model(agent_name)
    except (ModuleNotFoundError, ImportError, FileNotFoundError, ValueError) as e:
        print(f"[RL] Fallback greedy — module/checkpoint indisponible : {e}")
        return phase_mobs_ai(state, owner, must_hq_fn)
    # Inject state engine dans l'env (réutilise ses méthodes _build_obs / _run_rl_mob_phase)
    env.state = state
    env.rl_side  = owner
    env.opp_side = "B" if owner == "A" else "A"
    try:
        obs = env._build_obs()
        action, _ = model.predict(obs, deterministic=True)
        env._run_rl_mob_phase(action, state, owner, env.opp_side)
    except Exception as e:
        print(f"[AI RL] Erreur phase_mobs_{agent_name} : {e} — fallback greedy")
        return phase_mobs_ai(state, owner, must_hq_fn)
    return True


def _resolve_profile(player_char: str, ai_vs_ai: bool) -> str:
    """Détermine le profil IA pour ce joueur.

    En HvIA (ai_vs_ai=False) : DDM_AI_PROFILE (un seul profil pour l'opponent).
    En IAvIA (ai_vs_ai=True) : DDM_AI_PROFILE_A et DDM_AI_PROFILE_B (un par côté).
    Fallback : DDM_AI_PROFILE puis "greedy".
    """
    if ai_vs_ai:
        var = f"DDM_AI_PROFILE_{player_char}"
        return os.environ.get(var,
               os.environ.get("DDM_AI_PROFILE", "greedy")).lower()
    return os.environ.get("DDM_AI_PROFILE", "greedy").lower()


def _dispatch_ai(state: GameState, player_char: str, must_hq_fn, ai_vs_ai: bool):
    """
    Appelle la bonne fonction de phase mobs selon le profil de ce joueur.

    En HvIA : un seul profil global (DDM_AI_PROFILE).
    En IAvIA : un profil par côté (DDM_AI_PROFILE_A, DDM_AI_PROFILE_B) → permet
    par exemple jaeha vs neosia, opus vs jio, claude_api vs grok, etc.

    Profils supportés :
      - greedy (défaut), 7 LLM heuristiques, claude_api (via _AI_REGISTRY)
      - 5 RL agents : jin, jio, cross, jaeha, neosia (via _RL_AGENT_CKPT)
    """
    profile = _resolve_profile(player_char, ai_vs_ai)

    # RL agents : chargement PPO + wrapper
    if profile in _RL_AGENT_CKPT:
        print(f"[AI {player_char}] Profil RL : {profile}")
        return _phase_mobs_rl(state, player_char, must_hq_fn, profile)

    # LLM heuristiques + claude_api : registry classique
    entry = _AI_REGISTRY.get(profile)
    if entry:
        module_name, fn_name = entry
        try:
            pkg = __name__.rsplit(".", 1)[0]
            import importlib
            mod = importlib.import_module(f".{module_name}", package=pkg)
            fn  = getattr(mod, fn_name)
            print(f"[AI {player_char}] Profil : {profile}")
            return fn(state, player_char, must_hq_fn)
        except Exception as e:
            print(f"[AI {player_char}] Erreur chargement profil '{profile}' : {e} — fallback greedy")

    return phase_mobs_ai(state, player_char, must_hq_fn)


# ----------------------------------------------------------------------
#  PLAY TURN
# ----------------------------------------------------------------------

def play_turn(state: GameState, player_id: int,
              dice_bag_A: list, dice_bag_B: list,
              turn_A: int, turn_B: int,
              must_hq_fn,
              run_id: Optional[str] = None,
              ai_vs_ai: bool = False) -> Tuple[bool, int, int]:
    """
    Joue un tour complet pour le joueur indiqué (1=A, 2=B).
    Retourne (continue_game, turn_A, turn_B).
    """
    # Pause synchrone : si le renderer a demandé pause, attend ici avant de jouer
    _wait_if_paused()

    player_char = "A" if player_id == 1 else "B"
    dice_bag = dice_bag_A if player_id == 1 else dice_bag_B

    turn_idx = turn_A + turn_B + 1
    try:
        state.turn_idx = turn_idx
    except Exception:
        pass

    if _rl_enabled():
        hq_A_pos = must_hq_fn("A")
        hq_B_pos = must_hq_fn("B")
        rl_init_turn_ctx(state, player_char, turn_idx, run_id=run_id)

    canon_log("TURN_START", turn=turn_idx, player=player_char)
    state.current_player = player_id
    state.turn = turn_A if player_id == 1 else turn_B

    # Vide le buffer log snapshot pour ce nouveau demi-tour
    try:
        from .ddm_snapshot import log_clear, log_append as _la
        log_clear(state)
        _la(state, f"=== Tour {state.turn} — Joueur {player_char} ===")
    except Exception:
        pass

    print("\n" + "=" * 72)
    print(f"=== TOUR {state.turn} — Joueur {player_char} ===")
    print("=" * 72)

    if player_id == 1 or ai_vs_ai:
        render_ui(state)

    # 1) Lancer de dés + invocation
    roll_dice_for_player(state, dice_bag, player_id)
    if _rl_enabled():
        rl_after_roll_snapshot(state, player_char, must_hq_fn("A"), must_hq_fn("B"))

    # 2) Phase mobs
    is_human = (player_id == 1 and not ai_vs_ai)
    if is_human:
        _ddm_mode_mobs = os.environ.get("DDM_MODE", "cli")
        if _ddm_mode_mobs == "gui":
            try:
                from .ddm_p4_human_gui import phase_mobs_gui
                _pool = state.pool_A if player_id == 1 else state.pool_B
                cont = phase_mobs_gui(state, player_id, _pool, must_hq_fn)
            except Exception as e:
                print(f"[GUI] Erreur phase_mobs_gui : {e}")
                cont = phase_mobs_ai(state, player_char, must_hq_fn)
        else:
            cont = phase_mobs_human(state, must_hq_fn)
    else:
        cont = _dispatch_ai(state, player_char, must_hq_fn, ai_vs_ai)

    if not cont:
        if _rl_enabled():
            rl_finalize_turn(state, player_char, must_hq_fn("A"), must_hq_fn("B"),
                             ended=True, run_id=run_id)
        canon_log("TURN_END", turn=turn_idx, player=player_char)
        return False, turn_A, turn_B

    # 3) Tick fin de tour
    end_turn_tick(state)

    # Reset moved/attacked pour que le snapshot de fin de tour soit propre
    # (évite que le renderer bloque les unités au tour suivant)
    try:
        from .ddm_p3_mechanics import reset_units_for_new_mob_phase as _reset
        _reset(player_char)
    except Exception:
        pass

    # --- Snapshot renderer ---
    try:
        from .ddm_snapshot import write_snapshot as _ws
        _ws(state, state.board, UNITS, turn_idx, player_char,
            dice_bag_A=dice_bag_A, dice_bag_B=dice_bag_B)
    except Exception:
        pass

    # Persiste le log du tour pour le renderer (replay IA)
    try:
        from .ddm_snapshot import _get_log
        if player_char == "B":
            state.last_log_B_turn = list(_get_log(state))
        else:
            state.last_log_A_turn = list(_get_log(state))
    except Exception:
        pass
    # -------------------------

    if _rl_enabled():
        rl_finalize_turn(state, player_char, must_hq_fn("A"), must_hq_fn("B"),
                         ended=False, run_id=run_id)

    if player_id == 1:
        turn_A += 1
    else:
        turn_B += 1

    canon_log("TURN_END", turn=turn_idx, player=player_char)
    return True, turn_A, turn_B
