# =============================================================================
# ddm_p4_human_gui.py — Phase de jeu humain en mode GUI
# =============================================================================

import os
import time

from .ddm_command_reader import wait_for_command, apply_invocation, _clear_command, COMMAND_PATH
from .ddm_p1_core import UNITS, HQ_POS, log
from .ddm_p2_board_dice import (
    P1_QG, P2_QG, P1_TILE, P2_TILE, HEIGHT, WIDTH, in_bounds
)
from .ddm_p3_mechanics import (
    compute_invocation, attempt_place_invocation,
    get_unit_at, manhattan, apply_damage_to_unit, remove_unit,
    on_attacked_passive, reset_units_for_new_mob_phase,
    use_unit_ability, on_hq_attacked,
    resolve_attack_redirect, get_atk_cost_surcharge, consume_atk_cost_surcharge,
)

TIMEOUT_MOBS = 180.0
WALKABLE = {P1_TILE, P2_TILE}  # QG non traversables


def _log(state, msg):
    try:
        from .ddm_snapshot import log_append
        log_append(state, msg)
    except Exception:
        pass


def _snapshot(state, player_char):
    try:
        from .ddm_snapshot import write_snapshot as _ws
        _ws(state, state.board, UNITS,
            getattr(state, "turn", 1), player_char,
            dice_bag_A=[], dice_bag_B=[])
    except Exception as e:
        print(f"[GUI] Snapshot erreur : {e}")


def _attacked(u) -> bool:
    """Lecture défensive — Unit utilise has_attacked."""
    return bool(getattr(u, "has_attacked", False) or getattr(u, "attacked", False))

def _moved(u) -> bool:
    """Lecture défensive — Unit utilise has_moved."""
    return bool(getattr(u, "has_moved", False) or getattr(u, "moved", False))

def _set_moved(u):
    """Marque l'unité comme ayant bougé (sur les deux attributs)."""
    u.has_moved = True
    try: u.moved = True
    except: pass

def _set_attacked(u):
    """Marque l'unité comme ayant attaqué (sur les deux attributs)."""
    u.has_attacked = True
    try: u.attacked = True
    except: pass

def _def(u) -> int:
    """DEF défensive — Unit utilise defense + temp_def."""
    base = (getattr(u, "defense", None)
            or getattr(u, "def_base", None)
            or getattr(u, "def_", None)
            or 0)
    return int(base) + int(getattr(u, "temp_def", 0))

def _flush_stale_commands():
    """Supprime un command.json résiduel — mais jamais un end_phase valide."""
    try:
        if not COMMAND_PATH.exists():
            return
        import json as _json
        with open(COMMAND_PATH, "r", encoding="utf-8") as f:
            cmd = _json.load(f)
        if cmd.get("action") == "end_phase":
            return  # le moteur doit le lire
        _clear_command()
    except Exception:
        pass


def phase_invocation_gui(state, player_id, dice_bag, star_hits, invoc_level):
    player_char = "A" if player_id == 1 else "B"

    while True:
        print(f"[GUI] J{player_char} — En attente de la commande d'invocation L{invoc_level}...")
        _log(state, f"[GUI] En attente invocation L{invoc_level}...")
        _flush_stale_commands()
        cmd = wait_for_command(player_char, timeout=120.0)
        if cmd is None:
            print(f"[GUI] Timeout — invocation annulée")
            return False

        if cmd.get("action") != "invoke":
            print(f"[GUI] Action inattendue : {cmd.get('action')}")
            return False

        if apply_invocation(cmd, state, player_id):
            _log(state, f"[INVOC] J{player_char} Lv{invoc_level} invoqué via GUI")
            return True

        # Placement refusé — re-signaler le renderer et laisser réessayer
        _log(state, f"[INVOC] {player_char} Lv{invoc_level} : échec — choisissez une autre position")
        state.pending_invoc_level = invoc_level
        try:
            from .ddm_snapshot import write_snapshot as _ws
            from .ddm_p1_core import UNITS as _U
            _ws(state, state.board, _U, getattr(state, "turn", 1), player_char,
                dice_bag_A=dice_bag if player_id == 1 else [],
                dice_bag_B=[] if player_id == 1 else dice_bag)
        except Exception as _e:
            print(f"[GUI] Snapshot retry erreur : {_e}")


def phase_mobs_gui(state, player_id, pool, must_hq_fn):
    player_char = "A" if player_id == 1 else "B"
    enemy = "B" if player_char == "A" else "A"

    print(f"[GUI] J{player_char} — Phase mobs "
            f"(MOVE={pool.get('MOVE',0)} ATK={pool.get('ATK',0)} CAP={pool.get('CAP',0)})")

    reset_units_for_new_mob_phase(player_char)
    _flush_stale_commands()
    _snapshot(state, player_char)

    while True:
        if state.hq_A_hp <= 0 or state.hq_B_hp <= 0:
            return False

        # Vérifie si au moins une unité peut encore agir
        units = UNITS.get(player_char, [])
        move_left = pool.get("MOVE", 0)
        atk_left  = pool.get("ATK", 0)
        cap_left  = pool.get("CAP", 0)

        can_act = any(
            (move_left > 0 and not _moved(u)) or
            (atk_left  > 0 and not _attacked(u)) or
            cap_left  > 0
            for u in units if u.hp > 0
        )

        if not can_act:
            print(f"[GUI] Aucune action possible — fin phase mobs")
            _log(state, f"[MOV] JA fin automatique (aucune action possible)")
            break

        cmd = wait_for_command(player_char, timeout=TIMEOUT_MOBS)
        if cmd is None:
            print(f"[GUI] Timeout — fin automatique phase mobs")
            break

        action = cmd.get("action")

        if action == "end_phase":
            print(f"[GUI] Fin de phase demandée")
            _log(state, f"[MOV] JA fin volontaire")
            break
        elif action == "move":
            _handle_move(cmd, state, pool, player_char)
        elif action == "attack":
            _handle_attack(cmd, state, pool, player_char, enemy, must_hq_fn)
        elif action == "cap":
            _handle_cap(cmd, state, pool, player_char)
        else:
            print(f"[GUI] Action inconnue : {action}")
            continue

        _snapshot(state, player_char)

        if state.hq_A_hp <= 0 or state.hq_B_hp <= 0:
            return False

    return True


def _find_unit(state, player_char, cmd):
    name = cmd.get("unit_name", "")
    for u in UNITS.get(player_char, []):
        if u.hp > 0 and u.name == name:
            return u
    return None


def _find_enemy(state, enemy_char, cmd):
    name = cmd.get("target_name", "")
    for u in UNITS.get(enemy_char, []):
        if u.hp > 0 and u.name == name:
            return u
    return None


def _handle_move(cmd, state, pool, player_char):
    u = _find_unit(state, player_char, cmd)
    if not u:
        print(f"[GUI] MOVE : unité introuvable ({cmd.get('unit_name')})")
        return
    if _moved(u):
        print(f"[GUI] MOVE : {u.name} a déjà bougé ce tour")
        return

    to_col, to_row = cmd.get("to", [u.col, u.row])
    dist = manhattan(u.row, u.col, to_row, to_col)

    if dist == 0: return
    if pool.get("MOVE", 0) < dist:
        print(f"[GUI] MOVE : MOVE insuffisant ({pool.get('MOVE',0)} < {dist})")
        return
    if not in_bounds(state.board, to_row, to_col): return
    if state.board[to_row][to_col] not in WALKABLE: return
    occupant_result = get_unit_at(to_row, to_col)
    # get_unit_at retourne (unit, owner_char) ou (None, None)
    occupant = occupant_result[0] if isinstance(occupant_result, tuple) else occupant_result
    if occupant and getattr(occupant, "hp", 0) > 0: return

    old_r, old_c = u.row, u.col
    u.row = to_row; u.col = to_col
    _set_moved(u)
    pool["MOVE"] = pool.get("MOVE", 0) - dist

    print(f"[GUI] MOVE {u.name} ({old_r},{old_c})→({to_row},{to_col}) MOVE={pool['MOVE']}")
    log(f"MOV_GUI unit={u.name} from=({old_r},{old_c}) to=({to_row},{to_col})")
    _log(state, f"[MOV] JA {u.name} ({old_r},{old_c})→({to_row},{to_col})")


def _handle_attack(cmd, state, pool, player_char, enemy_char, must_hq_fn):
    u = _find_unit(state, player_char, cmd)
    if not u:
        print(f"[GUI] ATK : attaquant introuvable"); return
    surcharge = get_atk_cost_surcharge(u)
    if pool.get("ATK", 0) <= surcharge:
        msg = f"pool ATK épuisé" if not surcharge else f"pool ATK insuffisant (surcharge +{surcharge})"
        print(f"[GUI] ATK : {msg}"); return
    if _attacked(u):
        print(f"[GUI] ATK : {u.name} a déjà attaqué ce tour"); return

    target = _find_enemy(state, enemy_char, cmd)

    # Résolution des redirections avant toute validation
    if target is not None:
        target, _redirected = resolve_attack_redirect(state, u, player_char, target)

    if not target:
        hq_r, hq_c = must_hq_fn(enemy_char)
        if manhattan(u.row, u.col, hq_r, hq_c) == 1:
            atk = u.atk + getattr(u, "temp_atk", 0)
            if enemy_char == "B":
                raw = max(0, atk - state.get_hq_effective_def('B'))
                state.hq_B_hp = max(0, state.hq_B_hp - raw)
                _log(state, f"[ATK] JA {u.name}→QG B -{raw}HP")
            else:
                raw = max(0, atk - state.get_hq_effective_def('A'))
                state.hq_A_hp = max(0, state.hq_A_hp - raw)
                _log(state, f"[ATK] JA {u.name}→QG A -{raw}HP")
            _set_attacked(u)
            surcharge_paid = consume_atk_cost_surcharge(u)
            pool["ATK"] = pool.get("ATK", 0) - 1 - surcharge_paid
            on_hq_attacked(state, enemy_char, u)
        return

    if manhattan(u.row, u.col, target.row, target.col) != 1:
        print(f"[GUI] ATK : {target.name} pas adjacent"); return

    atk_val = u.atk + getattr(u, "temp_atk", 0)
    def_val = _def(target)
    dmg     = max(0, atk_val - def_val)

    on_attacked_passive(state, target, u, dmg)
    apply_damage_to_unit(state, target, dmg, u, "attack")
    _set_attacked(u)
    surcharge_paid = consume_atk_cost_surcharge(u)
    pool["ATK"] = pool.get("ATK", 0) - 1 - surcharge_paid

    print(f"[GUI] ATK {u.name}→{target.name} {atk_val}-{def_val}={dmg} HP={target.hp}")
    log(f"ATK_GUI unit={u.name} target={target.name} dmg={dmg}")
    _log(state, f"[ATK] JA {u.name}→{target.name} -{dmg}HP")

    if target.hp <= 0:
        remove_unit(target, state)
        _log(state, f"[ATK] {target.name} éliminé")
        return

    # Contre-attaque désactivée — à implémenter en Phase 4 après validation


def _handle_cap(cmd, state, pool, player_char):
    u = _find_unit(state, player_char, cmd)
    if not u:
        print(f"[GUI] CAP : unité introuvable"); return
    if pool.get("CAP", 0) <= 0:
        print(f"[GUI] CAP : pool CAP épuisé"); return
    tr = cmd.get("target_row"); tc = cmd.get("target_col")
    target_pos = (int(tr), int(tc)) if tr is not None and tc is not None else None
    success = use_unit_ability(state, u, player_char, target_pos=target_pos)
    if success:
        pool["CAP"] = pool.get("CAP", 0) - 1
        _log(state, f"[CAP] JA {u.name} capacité utilisée")
    else:
        print(f"[GUI] CAP : capacité non applicable pour {u.name}")
