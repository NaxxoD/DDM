"""
ddm_p4_loop.py  (allégé — refacto 2026-02)
Point d'entrée principal : parse_cli_args, _main_iaia, main().

Architecture après refacto :
  ddm_p4_loop.py      ← ici (main + iaia + CLI)
    └─ ddm_p4_turn.py    (play_turn + roll_dice_for_player)
         ├─ ddm_p4_ai.py     (phase_mobs_ai + pick_champion_letter)
         ├─ ddm_p4_human.py  (phase_mobs_human + despair + setup_ability)
         ├─ ddm_p4_human_gui.py  (phase_mobs_gui — lit command.json)
         ├─ ddm_p4_rl.py     (hooks RL optionnels)
         └─ ddm_p4_stats.py  (DDMStatsTracker + attach_stats_tracker)
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional, Tuple

from .ddm_p1_core import (
    GameState, UNITS, HQ_POS,
    log, canon_log, clear_screen, init_logger, load_factions_data,
    choose_faction, choose_faction_for_player, choose_faction_for_ai,
    build_default_ai_profile,
)
from .ddm_p2_board_dice import (
    create_board, create_starter_dice,
    build_standard_dice_bag, build_custom_dice_bag, build_random_dice_bag,
    build_extended_dice_bag, build_from_indices_bag,
    render_ui,
)
from .ddm_p3_mechanics import compute_invocation
from .ddm_p4_stats import DDMStatsTracker, attach_stats_tracker
from .ddm_p4_ai import pick_champion_letter
from .ddm_p4_turn import play_turn
from .ddm_p4_rl import _rl_enabled

# Import optionnel update_panel (GUI externe, peut être absent)
try:
    from .ddm_p1_core import update_panel
except ImportError:
    def update_panel(*_a, **_kw):
        pass

AI_VS_AI_MODE: bool = False


# ----------------------------------------------------------------------
#  HELPERS
# ----------------------------------------------------------------------

def _utc_now_iso() -> str:
    try:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return str(datetime.utcnow())


def current_run_id() -> Optional[str]:
    try:
        try:
            from . import ddm_p1_core as P1
        except ImportError:
            import importlib, sys
            pkg = __name__.rsplit(".", 1)[0] if "." in __name__ else None
            P1 = importlib.import_module(f"{pkg}.ddm_p1_core" if pkg else "ddm_p1_core")
        lf = getattr(P1, "LOG_FILE", None)
        if not lf:
            return None
        base = os.path.basename(str(lf))
        m = re.match(r"run_(\d{8}_\d{6}(?:_\d{5})?)", base)
        return m.group(1) if m else None
    except Exception:
        return None


def must_hq(side: str) -> Tuple[int, int]:
    pos = HQ_POS.get(side)
    if pos is None:
        raise RuntimeError(f"HQ_POS['{side}'] non initialisé (init board manquante)")
    return pos


def _stats_path() -> str:
    p = os.environ.get("DDM_STATS_PATH")
    if p:
        return p
    try:
        base = os.path.dirname(__file__)
        return os.path.join(base, "..", "data", "faction_stats.json")
    except Exception:
        return os.path.join("data", "faction_stats.json")


def log_game_summary(state_or_winner, *args):
    if hasattr(state_or_winner, "hq_A_hp") and hasattr(state_or_winner, "hq_B_hp"):
        state = state_or_winner
        rounds = 0
        if len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], int):
            rounds = max(args[0], args[1]) - 1
        else:
            rounds = int(getattr(state, "turn", 0) or 0)

        if state.hq_A_hp <= 0 and state.hq_B_hp <= 0:
            winner, reason = "D", "double_hq_destroyed"
        elif state.hq_A_hp <= 0:
            winner, reason = "B", "HQ_A_destroyed"
        elif state.hq_B_hp <= 0:
            winner, reason = "A", "HQ_B_destroyed"
        else:
            winner, reason = "D", "ended_without_winner"

        try:
            if getattr(state, "stats", None) is not None:
                state.stats.finish_game(winner, int(rounds), reason)
        except Exception:
            pass
        try:
            canon_log("SUMMARY_END", winner=winner, rounds=int(rounds), reason=reason)
        except Exception:
            pass
        print(f"SUMMARY_END winner={winner} rounds={int(rounds)} reason={reason}")
        return

    winner = state_or_winner
    rounds = args[0] if args else 0
    reason = args[1] if len(args) > 1 else "unknown"
    if isinstance(winner, str) and winner.lower() == "draw":
        winner = "D"
    try:
        canon_log("SUMMARY_END", winner=winner, rounds=int(rounds), reason=reason)
    except Exception:
        pass
    try:
        log(f"SUMMARY_END winner={winner} rounds={int(rounds)} reason={reason}")
    except Exception:
        print(f"SUMMARY_END winner={winner} rounds={int(rounds)} reason={reason}")


def _get_factions_data() -> list:
    try:
        try:
            from . import ddm_p1_core as P1
        except ImportError:
            import importlib
            pkg = __name__.rsplit(".", 1)[0] if "." in __name__ else None
            P1 = importlib.import_module(f"{pkg}.ddm_p1_core" if pkg else "ddm_p1_core")
        if not getattr(P1, "FACTIONS_DATA", None):
            P1.load_factions_data()
        return getattr(P1, "FACTIONS_DATA", None) or []
    except Exception:
        return []


# ----------------------------------------------------------------------
#  CLI ARGS
# ----------------------------------------------------------------------

def parse_cli_args(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--mode", choices=["iaia", "hvia", "hvh", "gui"], default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--bag", type=int, default=None)
    ap.add_argument("--bag-type", choices=["S", "E", "P"], default="S")
    ap.add_argument("--max-rounds", type=int, default=None)
    ap.add_argument("--faction-a", type=int, default=None)
    ap.add_argument("--faction-b", type=int, default=None)
    ap.add_argument("--champion-a", type=str, default=None)
    ap.add_argument("--champion-b", type=str, default=None)
    ap.add_argument("--start", choices=["A", "B", "alternate", "random"], default=None)
    ap.add_argument("--sideflip", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    return args


def _build_bags(args, base_catalog, bag_size, for_ai_b=False):
    """Construit les sacs A et B selon --bag-type."""
    import json as _json
    bag_type = getattr(args, "bag_type", "S")
    if bag_type == "E":
        bag_a = build_extended_dice_bag(base_catalog, bag_size)
        bag_b = build_extended_dice_bag(base_catalog, bag_size)
    elif bag_type == "P":
        raw_a = os.environ.get("DDM_DICE_INDICES_A", "")
        raw_b = os.environ.get("DDM_DICE_INDICES_B", "")
        indices_a = _json.loads(raw_a) if raw_a else None
        indices_b = _json.loads(raw_b) if raw_b else None
        bag_a = build_from_indices_bag(base_catalog, indices_a) if indices_a else build_standard_dice_bag(base_catalog, bag_size)
        if for_ai_b:
            bag_b = build_random_dice_bag(base_catalog, bag_size, "IA B") if not indices_b else build_from_indices_bag(base_catalog, indices_b)
        else:
            bag_b = build_from_indices_bag(base_catalog, indices_b) if indices_b else build_standard_dice_bag(base_catalog, bag_size)
    else:
        bag_a = build_standard_dice_bag(base_catalog, bag_size)
        bag_b = build_standard_dice_bag(base_catalog, bag_size)
    return bag_a, bag_b


def _attach_draft_rosters(state):
    """Lit DDM_DRAFT_ROSTER_A/B et attache les listes de noms sur le state."""
    import json as _json
    raw_a = os.environ.get("DDM_DRAFT_ROSTER_A", "")
    raw_b = os.environ.get("DDM_DRAFT_ROSTER_B", "")
    state.draft_roster_A = _json.loads(raw_a) if raw_a else None
    state.draft_roster_B = _json.loads(raw_b) if raw_b else None


# ----------------------------------------------------------------------
#  IA vs IA (autoruns)
# ----------------------------------------------------------------------

def _main_iaia(args):
    os.environ.setdefault("DDM_LOG_CANON", "FULL")
    global AI_VS_AI_MODE
    AI_VS_AI_MODE = True
    from . import ddm_p1_core as _p1c
    _p1c.AI_VS_AI_MODE = True

    winner = "?"
    reason = "unknown"
    rounds = 0
    turn_A = 1
    turn_B = 1
    state = None

    _gui_spectator_pre = (os.environ.get("DDM_GUI_CONNECTED", "0") == "1")
    if _gui_spectator_pre:
        from .ddm_snapshot import SNAPSHOT_DIR as _SDIR
        import time as _ti
        _SDIR.mkdir(parents=True, exist_ok=True)
        _ready_f = _SDIR / "renderer_ready.json"
        _quit_f  = _SDIR / "renderer_quit.json"
        # Nettoie les signaux d'une session précédente
        for _f in (_ready_f, _quit_f):
            try: _f.unlink()
            except FileNotFoundError: pass
        print("[IAIA] En attente du renderer (renderer_ready.json)...")
        _deadline = _ti.time() + 30.0
        while _ti.time() < _deadline:
            if _ready_f.exists():
                print("[IAIA] Renderer connecté — démarrage de la partie.")
                break
            _ti.sleep(0.2)
        else:
            print("[IAIA] Timeout renderer — démarrage quand même.")

    try:
        if args.seed is not None:
            random.seed(int(args.seed))

        factions = _get_factions_data()
        if not factions:
            raise RuntimeError("FACTIONS_DATA vide après load_factions_data()")

        fid_A = int(args.faction_a) if args.faction_a is not None else int(
            random.choice([int(f.get("id")) for f in factions
                           if isinstance(f, dict) and f.get("id") is not None])
        )
        fid_B = int(args.faction_b) if args.faction_b is not None else int(
            random.choice([int(f.get("id")) for f in factions
                           if isinstance(f, dict) and f.get("id") is not None
                           and int(f.get("id")) != fid_A] or [fid_A])
        )

        champ_A_letter = pick_champion_letter(fid_A, factions, args.champion_a or None)
        champ_B_letter = pick_champion_letter(fid_B, factions, args.champion_b or None)

        faction_A_info = choose_faction(fid_A, champ_A_letter)
        faction_B_info = choose_faction(fid_B, champ_B_letter)

        bag_size = int(args.bag) if args.bag else 11
        board = create_board()
        state = GameState(board, faction_A_info, faction_B_info)
        _attach_draft_rosters(state)

        attach_stats_tracker(
            state, mode="iaia",
            run_id=current_run_id() or "iaia",
            bag_size=bag_size,
            seed=getattr(args, "seed", None),
            factionA=faction_A_info.get("name"),
            factionB=faction_B_info.get("name"),
            champA=champ_A_letter,
            champB=champ_B_letter,
            sideflip=int(bool(getattr(args, "sideflip", False))),
        )
        state.bag_size = bag_size

        log(f"FACTIONS: A={fid_A} champ={champ_A_letter} | B={fid_B} champ={champ_B_letter}")
        log(f"HQ_POS: A={must_hq('A')} B={must_hq('B')}")

        base_catalog = create_starter_dice()
        dice_bag_A, dice_bag_B = _build_bags(args, base_catalog, bag_size, for_ai_b=False)

        max_rounds = int(args.max_rounds) if args.max_rounds else 500
        run_id = current_run_id()

        _gui_spectator = (os.environ.get("DDM_GUI_CONNECTED", "0") == "1")
        _TURN_DELAY = 1.5   # secondes entre tours en spectateur
        _END_HOLD   = 60.0  # secondes de maintien après snapshot final

        def _snap(active: str, final_winner: str = ""):
            if not _gui_spectator:
                return
            try:
                from .ddm_snapshot import write_snapshot as _ws
                from .ddm_p1_core import UNITS as _U
                _ws(state, state.board, _U,
                    max(turn_A, turn_B), active,
                    dice_bag_A=dice_bag_A, dice_bag_B=dice_bag_B,
                    extra={"winner": final_winner} if final_winner else {})
            except Exception as _e:
                print(f"[IAIA] Snapshot erreur : {_e}")
            if final_winner:
                print(f"[IAIA] Fin de partie — winner={final_winner}. "
                      f"En attente de renderer_quit.json...")
                import time as _t
                from .ddm_snapshot import SNAPSHOT_DIR as _SD2
                _qf = _SD2 / "renderer_quit.json"
                _dl = _t.time() + 120.0
                while _t.time() < _dl:
                    if _qf.exists():
                        try: _qf.unlink()
                        except Exception: pass
                        break
                    _t.sleep(0.3)
            else:
                import time as _t; _t.sleep(_TURN_DELAY)

        starter_arg = getattr(args, "start", None) or "A"
        if starter_arg == "random":
            starter = random.choice(["A", "B"])
        elif starter_arg == "alternate":
            starter = "A"
        else:
            starter = starter_arg

        while True:
            if max(turn_A, turn_B) > max_rounds:
                reason = "max_rounds"
                winner = "A" if state.hq_A_hp > state.hq_B_hp else (
                    "B" if state.hq_B_hp > state.hq_A_hp else "D"
                )
                canon_log("GAME_END", winner=winner, reason="max_rounds")
                print(f"GAME_END winner={winner} reason=max_rounds")
                print(f"SUMMARY_END winner={winner} rounds={max_rounds} reason=max_rounds")
                if _rl_enabled():
                    try:
                        from .ddm_p4_rl import rl_finalize_turn
                        for side in ("A", "B"):
                            ctx = getattr(state, "rl_turn_ctx", None)
                            if isinstance(ctx, dict):
                                ctx["terminal"] = "draw"
                            rl_finalize_turn(state, side, must_hq("A"), must_hq("B"),
                                             ended=True, run_id=run_id)
                    except Exception:
                        pass
                break

            if starter == "A":
                cont, turn_A, turn_B = play_turn(
                    state, 1, dice_bag_A, dice_bag_B, turn_A, turn_B,
                    must_hq_fn=must_hq, run_id=run_id, ai_vs_ai=True,
                )
                _snap("B")
                if not cont:
                    break
                cont, turn_A, turn_B = play_turn(
                    state, 2, dice_bag_A, dice_bag_B, turn_A, turn_B,
                    must_hq_fn=must_hq, run_id=run_id, ai_vs_ai=True,
                )
                _snap("A")
                if not cont:
                    break
            else:
                cont, turn_A, turn_B = play_turn(
                    state, 2, dice_bag_A, dice_bag_B, turn_A, turn_B,
                    must_hq_fn=must_hq, run_id=run_id, ai_vs_ai=True,
                )
                _snap("A")
                if not cont:
                    break
                cont, turn_A, turn_B = play_turn(
                    state, 1, dice_bag_A, dice_bag_B, turn_A, turn_B,
                    must_hq_fn=must_hq, run_id=run_id, ai_vs_ai=True,
                )
                _snap("B")
                if not cont:
                    break

        if winner == "?":
            if state.hq_A_hp <= 0 and state.hq_B_hp <= 0:
                winner, reason = "draw", "double_hq_destroyed"
            elif state.hq_A_hp <= 0:
                winner, reason = "B", "HQ_A_destroyed"
            elif state.hq_B_hp <= 0:
                winner, reason = "A", "HQ_B_destroyed"
            else:
                winner, reason = "draw", "ended_without_winner"

        # Print stdout markers pour parsing externe (autoruns, llm_matrix, etc).
        # Le print max_rounds est déjà fait ci-dessus ; ici c'est pour HQ destroyed.
        if reason != "max_rounds":
            _r = max(turn_A, turn_B) - 1
            print(f"GAME_END winner={winner} reason={reason}")
            print(f"SUMMARY_END winner={winner} rounds={_r} reason={reason}")

        _snap("A", final_winner=winner)

        rounds = max(turn_A, turn_B) - 1
        return 0

    except KeyboardInterrupt:
        winner, reason = "none", "keyboard_interrupt"
        try:
            log("GAME_END: winner=none reason=keyboard_interrupt")
        except Exception:
            pass
        rounds = max(turn_A, turn_B) - 1
        return 0

    except Exception as e:
        try:
            log(f"CRASH_END type={type(e).__name__} msg={e}")
        except Exception:
            pass
        try:
            traceback.print_exc()
        except Exception:
            pass
        winner = "?"
        reason = "exception"
        rounds = max(turn_A, turn_B) - 1
        return 1

    finally:
        try:
            if rounds <= 0:
                rounds = max(turn_A, turn_B) - 1
            if state is not None and getattr(state, "stats", None) is not None:
                state.stats.finish_game(winner, rounds, reason)
            log(f"SUMMARY_END winner={winner} rounds={rounds} reason={reason}")
        except Exception:
            pass


# ----------------------------------------------------------------------
#  GUI MODE — joueur humain via renderer Pygame + command.json
# ----------------------------------------------------------------------

def _main_gui(args):
    """
    Mode GUI : bypass total des input() CLI.
    Factions sélectionnées via --faction-a / --faction-b (défaut : random).
    Le joueur A joue via le renderer Pygame (command.json).
    Le joueur B est contrôlé par l'IA.
    """
    os.environ["DDM_MODE"] = "gui"
    print("=== DDM — Mode GUI (renderer Pygame) ===")

    factions = _get_factions_data()
    if not factions:
        raise RuntimeError("FACTIONS_DATA vide")

    fid_A = int(args.faction_a) if args.faction_a is not None else int(
        random.choice([int(f["id"]) for f in factions if f.get("id") is not None])
    )
    fid_B = int(args.faction_b) if args.faction_b is not None else int(
        random.choice([int(f["id"]) for f in factions
                       if f.get("id") is not None and int(f["id"]) != fid_A] or [fid_A])
    )

    champ_A = pick_champion_letter(fid_A, factions, args.champion_a or None)
    champ_B = pick_champion_letter(fid_B, factions, args.champion_b or None)

    faction_A_info = choose_faction(fid_A, champ_A)
    faction_B_info = choose_faction(fid_B, champ_B)

    bag_size = int(args.bag) if args.bag else 11
    board = create_board()
    state = GameState(board, faction_A_info, faction_B_info)
    state.bag_size = bag_size
    _attach_draft_rosters(state)

    attach_stats_tracker(
        state, mode="gui",
        run_id=current_run_id() or "gui",
        bag_size=bag_size,
        factionA=faction_A_info.get("name"),
        factionB=faction_B_info.get("name"),
        champA=champ_A, champB=champ_B,
    )

    log(f"FACTIONS: A={fid_A} champ={champ_A} | B={fid_B} champ={champ_B}")
    log(f"HQ_POS: A={must_hq('A')} B={must_hq('B')}")
    print(f"  Joueur A : {faction_A_info['name']} — Champion : {state.hero_A['name']}")
    print(f"  IA     B : {faction_B_info['name']} — Champion : {state.hero_B['name']}")
    print("  En attente du renderer Pygame (command.json)...")

    base_catalog = create_starter_dice()
    dice_bag_A, dice_bag_B = _build_bags(args, base_catalog, bag_size, for_ai_b=True)

    turn_A = 1
    turn_B = 1
    run_id = current_run_id()

    try:
        while True:
            # Tour joueur A (humain via GUI)
            cont, turn_A, turn_B = play_turn(
                state, 1, dice_bag_A, dice_bag_B, turn_A, turn_B,
                must_hq_fn=must_hq, run_id=run_id, ai_vs_ai=False,
            )
            if not cont:
                break
            # Tour joueur B (IA)
            cont, turn_A, turn_B = play_turn(
                state, 2, dice_bag_A, dice_bag_B, turn_A, turn_B,
                must_hq_fn=must_hq, run_id=run_id, ai_vs_ai=False,
            )
            if not cont:
                break
    except KeyboardInterrupt:
        print("\nPartie interrompue.")
        log("GAME_INTERRUPTED_BY_USER")

    log_game_summary(state, turn_A, turn_B, dice_bag_A, dice_bag_B)


# ----------------------------------------------------------------------
#  MAIN (mode console interactif)
# ----------------------------------------------------------------------

def main():
    clear_screen()
    init_logger()
    load_factions_data()

    args = parse_cli_args()
    print(f"DEBUG mode={args.mode}")

    if args.mode == "iaia":
        try:
            return _main_iaia(args)
        except Exception as e:
            log(f"CRASH_END type={type(e).__name__} msg={e}")
            raise

    if args.mode == "gui":
        try:
            return _main_gui(args)
        except Exception as e:
            log(f"CRASH_END type={type(e).__name__} msg={e}")
            raise

    print("=== PROTO DDM — Mode Console (QG séparé, traps, IA améliorée) ===\n")

    # Sélection de factions
    fid_A, champ_A_letter = choose_faction_for_player()
    faction_A_info = choose_faction(fid_A, champ_A_letter)

    fid_B, champ_B_letter = choose_faction_for_ai(fid_A)
    faction_B_info = choose_faction(fid_B, champ_B_letter)

    try:
        update_panel(
            faction_A_info["name"],
            faction_A_info["champion"]["visuel"] if faction_A_info["champion"] else "",
            "",
        )
    except Exception:
        pass

    bag_size = 11
    board = create_board()
    state = GameState(board, faction_A_info, faction_B_info)

    attach_stats_tracker(
        state, mode=(args.mode or "hvia"),
        run_id=current_run_id() or "console",
        bag_size=bag_size,
        seed=getattr(args, "seed", None),
        factionA=faction_A_info.get("name"),
        factionB=faction_B_info.get("name"),
        champA=champ_A_letter,
        champB=champ_B_letter,
        sideflip=int(bool(getattr(args, "sideflip", False))),
    )
    state.bag_size = bag_size

    log(f"FACTIONS: A={fid_A} champ={champ_A_letter} | B={fid_B} champ={champ_B_letter}")
    log(f"HQ_POS: A={must_hq('A')} B={must_hq('B')}")

    print("\nFactions sélectionnées :")
    print(f"  Joueur A : {state.faction_A['name']} — Champion : {state.hero_A['name']}")
    print(f"  IA B     : {state.faction_B['name']} — Champion : {state.hero_B['name']}")

    # Configuration des dés
    base_catalog = create_starter_dice()
    print("\nChoix de la taille du sac de dés :")
    print("  [1] 11 dés (rapide)")
    print("  [2] 22 dés (sac étendu)")
    choice = input("Mode ? (1/2, Enter=1) : ").strip()
    bag_size = 22 if choice == "2" else 11
    state.bag_size = bag_size
    try:
        if getattr(state, "stats", None) is not None:
            state.stats.set_run_meta(bag=bag_size)
    except Exception:
        pass

    print("\nConfiguration du sac :")
    print("  [A] Sac standard (core)")
    print("  [B] Construire un sac personnalisé (core + étendu)")
    mode_sac = input("Choix ? (A/B, Enter=A) : ").strip().upper() or "A"

    if mode_sac == "B":
        dice_bag_A = build_custom_dice_bag(base_catalog, bag_size, "Joueur A", state.faction_A)
        same_for_ai = input("Utiliser le même sac pour l'IA ? (O/N, Enter=O) : ").strip().upper()
        if same_for_ai in ("", "O", "OUI", "Y", "YES"):
            dice_bag_B = list(dice_bag_A)
        else:
            dice_bag_B = build_random_dice_bag(base_catalog, bag_size, "IA B")
    else:
        dice_bag_A = build_standard_dice_bag(base_catalog, bag_size)
        dice_bag_B = build_standard_dice_bag(base_catalog, bag_size)

    turn_A = 1
    turn_B = 1
    run_id = current_run_id()

    try:
        while True:
            cont, turn_A, turn_B = play_turn(
                state, 1, dice_bag_A, dice_bag_B, turn_A, turn_B,
                must_hq_fn=must_hq, run_id=run_id, ai_vs_ai=False,
            )
            if not cont:
                break
            cont, turn_A, turn_B = play_turn(
                state, 2, dice_bag_A, dice_bag_B, turn_A, turn_B,
                must_hq_fn=must_hq, run_id=run_id, ai_vs_ai=False,
            )
            if not cont:
                break
    except KeyboardInterrupt:
        print("\nFin de la démo (interruption clavier).")
        log("GAME_INTERRUPTED_BY_USER")

    log_game_summary(state, turn_A, turn_B, dice_bag_A, dice_bag_B)
    print("\nRésumé de fin de partie :")
    print(f"  Tours Joueur A : {turn_A - 1}")
    print(f"  Tours IA B     : {turn_B - 1}")
    print(f"  QG A HP        : {state.hq_A_hp}/{state.hq_A_hp_max}")
    print(f"  QG B HP        : {state.hq_B_hp}/{state.hq_B_hp_max}")
    print(f"  Unités A       : {len(UNITS['A'])}")
    print(f"  Unités B       : {len(UNITS['B'])}")


if __name__ == "__main__":
    main()
