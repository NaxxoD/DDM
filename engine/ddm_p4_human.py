"""
ddm_p4_human.py
Phase mobs joueur humain + déclenchement champion (despair) côté A et B.
Extrait de ddm_p4_loop.py lors du refacto 2026-02.
"""
from __future__ import annotations

from .ddm_p1_core import (
    GameState, Unit, UNITS, HEIGHT, WIDTH, P1_TILE, P2_TILE,
    log, build_default_ai_profile,
    parse_ability_from_action_speciale,
    get_game_phase,
)
from .ddm_p2_board_dice import (
    print_board_with_focus, pool_to_str, render_ui,
    EMPTY, P1_QG, P2_QG,
)
from .ddm_p3_mechanics import (
    apply_damage_to_unit, trigger_trap_on_enter,
    use_unit_ability, get_unit_at, find_enemy_adjacent,
    manhattan, reset_units_for_new_mob_phase,
    get_passive_atk_bonus,
)

# Directions candidates autour d'un QG
_CAND_STEPS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


# ----------------------------------------------------------------------
#  SETUP ABILITY CHAMPION
# ----------------------------------------------------------------------

def setup_champion_action_ability(state: GameState, champ_unit: Unit, owner_char: str) -> None:
    """Parse l'action_speciale du champion dans le JSON et l'attache à l'unité."""
    try:
        faction = state.faction_A if owner_char == "A" else state.faction_B
    except Exception:
        return
    champ_dict = (faction.get("champion") or {}) if isinstance(faction, dict) else {}
    action_text = (
        champ_dict.get("action")
        or champ_dict.get("action_speciale")
        or champ_dict.get("action_spéciale")
        or champ_dict.get("action_special")
    )
    if not action_text:
        return
    try:
        data = parse_ability_from_action_speciale(
            action_text, fallback_id=f"CHAMP_{owner_char}_ACTION"
        )
    except Exception:
        data = None
    if not data:
        return

    nice_name = action_text.split(":", 1)[0].strip()
    champ_unit.ability_id = data.get("id") or f"CHAMP_{owner_char}_ACTION"
    champ_unit.ability_name = nice_name or data.get("name") or "Action Champion"
    champ_unit.ability_cost = data.get("cost") or {}
    champ_unit.ability_range = data.get("range", None)
    champ_unit.ability_effects = data.get("effects") or {}
    if "target_type" in data:
        champ_unit.ability_target_type = data.get("target_type")
    log(f"CHAMPION_ACTION_READY_{owner_char} name={champ_unit.ability_name} cost={champ_unit.ability_cost}")


# ----------------------------------------------------------------------
#  DESPAIR CHAMPION — IA (B) et JOUEUR (A)
# ----------------------------------------------------------------------

def maybe_trigger_despair_champion(state: GameState, must_hq_fn) -> None:
    """Déclenche le champion B si QG en danger ou armée trop faible."""
    if state.champion_B_state != "dormant":
        return

    profile = state.ai_profile_B
    threshold = profile.get("despair_threshold", 0.45)
    phase = get_game_phase(state, profile)
    if phase == "early":
        threshold *= 1.1
    elif phase in ("late", "overtime"):
        threshold *= 0.9

    hp_ratio     = state.hq_B_hp / state.hq_B_hp_max if state.hq_B_hp_max > 0 else 0
    opp_hp_ratio = state.hq_A_hp / state.hq_A_hp_max if state.hq_A_hp_max > 0 else 0
    few_units    = len(UNITS["B"]) <= 2
    hq_r, hq_c  = must_hq_fn("B")
    enemy_near_hq = any(manhattan(u.row, u.col, hq_r, hq_c) <= 3 for u in UNITS["A"])

    # "few_units + enemy_near_hq" ne suffit pas si notre QG est intact et l'adversaire est entamé
    # → évite le pop prématuré quand on domine avec peu d'unités
    dominating = hp_ratio >= 0.8 and opp_hp_ratio <= 0.7
    trigger_few = few_units and enemy_near_hq and not dominating

    if not (hp_ratio <= threshold or trigger_few):
        return

    print("\n[IA] Mode DÉSESPOIR : le champion B entre en jeu !")
    log("DESPAIR_CHAMPION_TRIGGER_B")

    stats = state.hero_B
    hp = stats.get("hp", 20)
    atk = stats.get("atk", 7)
    defense = stats.get("def", 10)
    name = stats.get("name", "Champion B (Boss)")

    # Créer la zone protégée : 3 cases adjacentes au QG (côté intérieur)
    # B : QG en haut → cases en dessous du QG
    hq_r_b, hq_c_b = hq_r, hq_c
    fwd_b = 1 if hq_r_b <= HEIGHT // 2 else -1
    _zone_b = [(hq_r_b + fwd_b, hq_c_b),
               (hq_r_b + fwd_b, hq_c_b - 1),
               (hq_r_b + fwd_b, hq_c_b + 1)]
    for zr, zc in _zone_b:
        if 0 <= zr < HEIGHT and 0 <= zc < WIDTH and state.board[zr][zc] == EMPTY:
            state.board[zr][zc] = P2_TILE
    log(f"DESPAIR_ZONE_B: cases={_zone_b}")

    spawn_pos = None
    for zr, zc in _zone_b:
        if 0 <= zr < HEIGHT and 0 <= zc < WIDTH:
            other, _ = get_unit_at(zr, zc)
            if other is None:
                spawn_pos = (zr, zc)
                break
    for dr, dc in [(fwd_b, 0), (fwd_b, -1), (fwd_b, 1)]:
        if spawn_pos:
            break
        nr, nc = hq_r + dr, hq_c + dc
        if 0 <= nr < HEIGHT and 0 <= nc < WIDTH:
            other, _ = get_unit_at(nr, nc)
            if other is None:
                spawn_pos = (nr, nc)
    if spawn_pos is None:
        spawn_pos = (hq_r, hq_c)

    r, c = spawn_pos
    champ_unit = Unit("B", r, c, hp=hp, atk=atk, move=2,
                      name=name, defense=defense, is_champion=True, level=4)
    setup_champion_action_ability(state, champ_unit, "B")
    UNITS["B"].append(champ_unit)
    state.champion_B_state = "deployed"

    print(f"  -> Champion B spawn en (r={r}, c={c}) [HP={hp}, ATK={atk}, DEF={defense}]")
    log(f"SPAWN_CHAMPION_B: pos=({r},{c}) HP={hp} ATK={atk} DEF={defense}")


def maybe_trigger_despair_champion_A(state: GameState, must_hq_fn) -> None:
    """Déclenche le champion A (joueur) si QG en danger ou armée trop faible."""
    if state.champion_A_state != "dormant":
        return

    profile = state.ai_profile_A or build_default_ai_profile(state.faction_A.get("name"))
    threshold = profile.get("despair_threshold", 0.45)
    phase = get_game_phase(state, profile)
    if phase == "early":
        threshold *= 1.1
    elif phase in ("late", "overtime"):
        threshold *= 0.9

    hp_ratio     = state.hq_A_hp / state.hq_A_hp_max if state.hq_A_hp_max > 0 else 0
    opp_hp_ratio = state.hq_B_hp / state.hq_B_hp_max if state.hq_B_hp_max > 0 else 0
    few_units    = len(UNITS["A"]) <= 2
    hq_r, hq_c  = must_hq_fn("A")
    enemy_near_hq = any(manhattan(u.row, u.col, hq_r, hq_c) <= 3 for u in UNITS["B"])

    dominating   = hp_ratio >= 0.8 and opp_hp_ratio <= 0.7
    trigger_few  = few_units and enemy_near_hq and not dominating

    if not (hp_ratio <= threshold or trigger_few):
        return

    print("\n[Joueur] Mode DÉSESPOIR : votre champion entre en jeu !")
    log("DESPAIR_CHAMPION_TRIGGER_A")

    stats = state.hero_A
    hp = stats.get("hp", 20)
    atk = stats.get("atk", 7)
    defense = stats.get("def", 10)
    name = stats.get("name", "Champion A")

    # Créer la zone protégée : 3 cases adjacentes au QG (côté intérieur)
    # A : QG en bas → cases au-dessus du QG
    hq_r_a, hq_c_a = hq_r, hq_c
    fwd_a = 1 if hq_r_a <= HEIGHT // 2 else -1
    _zone_a = [(hq_r_a + fwd_a, hq_c_a),
               (hq_r_a + fwd_a, hq_c_a - 1),
               (hq_r_a + fwd_a, hq_c_a + 1)]
    for zr, zc in _zone_a:
        if 0 <= zr < HEIGHT and 0 <= zc < WIDTH and state.board[zr][zc] == EMPTY:
            state.board[zr][zc] = P1_TILE
    log(f"DESPAIR_ZONE_A: cases={_zone_a}")

    spawn_pos = None
    for zr, zc in _zone_a:
        if 0 <= zr < HEIGHT and 0 <= zc < WIDTH:
            other, _ = get_unit_at(zr, zc)
            if other is None:
                spawn_pos = (zr, zc)
                break
    for dr, dc in [(fwd_a, 0), (fwd_a, -1), (fwd_a, 1)]:
        if spawn_pos:
            break
        nr, nc = hq_r + dr, hq_c + dc
        if 0 <= nr < HEIGHT and 0 <= nc < WIDTH:
            other, _ = get_unit_at(nr, nc)
            if other is None:
                spawn_pos = (nr, nc)
    if spawn_pos is None:
        spawn_pos = (hq_r, hq_c)

    r, c = spawn_pos
    champ_unit = Unit("A", r, c, hp=hp, atk=atk, move=2,
                      name=name, defense=defense, is_champion=True, level=4)
    setup_champion_action_ability(state, champ_unit, "A")
    UNITS["A"].append(champ_unit)
    state.champion_A_state = "deployed"

    print(f"  -> Champion A spawn en (r={r}, c={c}) [HP={hp}, ATK={atk}, DEF={defense}]")
    log(f"SPAWN_CHAMPION_A: pos=({r},{c}) HP={hp} ATK={atk} DEF={defense}")


# ----------------------------------------------------------------------
#  PHASE MOBS — JOUEUR HUMAIN (A)
# ----------------------------------------------------------------------

def phase_mobs_human(state: GameState, must_hq_fn) -> bool:
    """Phase unités pour le joueur humain (camp A). Retourne False si QG détruit."""
    units = UNITS["A"]
    pool = state.pool_A
    player_char = "A"

    print("Pool " + pool_to_str(pool))

    if not units:
        return True
    if pool["MOVE"] <= 0 and pool["ATK"] <= 0:
        print("Plus de MOVE/ATK. Fin de phase mobs.")
        log("END_PHASE_MOBS_A (no pool)")
        return True

    reset_units_for_new_mob_phase("A")

    def in_bounds(r, c):
        return 0 <= r < HEIGHT and 0 <= c < WIDTH

    def is_walkable(r, c):
        return state.board[r][c] in (P1_TILE, P2_TILE)

    def list_enemies_adjacent(u: Unit):
        return [v for v in UNITS["B"] if manhattan(u.row, u.col, v.row, v.col) == 1]

    print("\n=== Phase unités (Joueur A) ===")
    log("START_PHASE_MOBS_A")

    maybe_trigger_despair_champion_A(state, must_hq_fn)

    state.sleep_dash_left_A = 2 if state.champion_A_state == "dormant" else 0
    log(f"SLEEP_DASH_INIT_A left={state.sleep_dash_left_A} champion_state={state.champion_A_state}")
    dash_attr = "sleep_dash_left_A"

    mapping = {"z": (-1, 0), "w": (-1, 0), "s": (1, 0), "q": (0, -1), "a": (0, -1), "d": (0, 1)}

    while True:
        if pool["MOVE"] <= 0 and pool["ATK"] <= 0:
            print("Plus de MOVE/ATK. Fin de phase mobs.")
            log("END_PHASE_MOBS_A (exhausted)")
            return True

        render_ui(state)
        print(f"Pool MOVE={pool.get('MOVE',0)} ATK={pool.get('ATK',0)} "
              f"DEF={pool.get('DEF',0)} CAP={pool.get('CAP',0)}")
        print("[m]ove  [a]ttaquer  [s]kill    [q]uitter phase")

        action = input("Action ? ").strip().lower()

        # --- QUITTER ---
        if action in ("q", ""):
            log("END_PHASE_MOBS_A (player_quit)")
            try:
                ctx = getattr(state, "rl_turn_ctx", None)
                if isinstance(ctx, dict) and ctx.get("enabled"):
                    ctx["pass_avoidable"] = bool(
                        (pool.get("MOVE", 0) or 0) > 0 or (pool.get("ATK", 0) or 0) > 0
                    )
            except Exception:
                pass
            return True

        # --- DÉPLACEMENT ---
        elif action == "m":
            if pool["MOVE"] <= 0:
                print("Pas de MOVE disponible.")
                continue
            if not units:
                print("Aucune unité à déplacer.")
                continue

            print("\nUnités disponibles pour déplacement :")
            for idx, u in enumerate(units):
                print(f"  [{idx}] {u.name} "
                      f"({'Champ' if getattr(u,'is_champion',False) else 'Lv'+str(getattr(u,'level','?'))}) "
                      f"en (r={u.row}, c={u.col}) (HP={u.hp}, ATK={u.atk}, DEF={u.defense}+{u.temp_def})")

            ch = input("Indice de l'unité (Enter pour annuler) : ").strip()
            if ch == "":
                continue
            try:
                idx_u = int(ch)
            except ValueError:
                print("Indice invalide.")
                continue
            if not (0 <= idx_u < len(units)):
                print("Indice invalide.")
                continue

            u = units[idx_u]
            if u.has_moved:
                print("Cette unité a déjà bougé ce tour.")
                continue

            print_board_with_focus(state, u)
            print("Direction (ZQSD / WADS) ou X pour annuler :")
            print("  Astuce: 'zz/dd/qq/ss' = dash droit (2 cases / 1 MOVE / -1 dash) si champion dort.")
            print("         'zd/dz/zq/qz/sd/ds/...' = dash tournant (2 pas / 1 MOVE + -1 dash) si champion dort.")
            d_raw = input("  > ").strip().lower()
            if not d_raw or d_raw == "x":
                continue

            if len(d_raw) == 1:
                steps_dirs = [d_raw]
                want_dash = False
            elif len(d_raw) == 2:
                steps_dirs = [d_raw[0], d_raw[1]]
                want_dash = True
            else:
                print("Direction invalide (1 ou 2 lettres).")
                continue

            if any(c not in mapping for c in steps_dirs):
                print("Direction invalide.")
                continue

            dash = False
            dash_mode = None
            if want_dash:
                if state.champion_A_state != "dormant" or getattr(state, dash_attr, 0) <= 0:
                    print("Dash indisponible (champion réveillé / plus de dash).")
                    continue
                if u.is_champion or getattr(u, "level", 99) > 2:
                    print("Dash réservé aux unités Lv1–Lv2 (hors champion).")
                    continue
                dash = True
                dash_mode = "straight" if steps_dirs[0] == steps_dirs[1] else "corner"

            path = []
            cur_r, cur_c = u.row, u.col
            for c in steps_dirs:
                dr, dc = mapping[c]
                cur_r, cur_c = cur_r + dr, cur_c + dc
                path.append((cur_r, cur_c))

            ok_path = True
            for (nr, nc) in path:
                if not in_bounds(nr, nc):
                    print("Hors plateau.")
                    ok_path = False
                    break
                if not is_walkable(nr, nc):
                    if not (u.is_champion and (nr, nc) == must_hq_fn("A")):
                        print("Case non marchable.")
                        ok_path = False
                        break
                other, _ = get_unit_at(nr, nc)
                if other is not None:
                    print("Case occupée.")
                    ok_path = False
                    break
            if not ok_path:
                continue

            nr, nc = path[-1]
            old_r, old_c = u.row, u.col
            u.row, u.col = nr, nc
            u.has_moved = True
            pool["MOVE"] -= 1

            if dash:
                setattr(state, dash_attr, max(0, getattr(state, dash_attr, 0) - 1))
                left = getattr(state, dash_attr, 0)
                mode = dash_mode or "dash"
                print(f"  -> DASH {mode} en (r={nr}, c={nc}). MOVE restant = {pool['MOVE']} | dash_left={left}")
                log(f"SLEEP_DASH_USED_A unit={u.name} from=({old_r},{old_c}) to=({nr},{nc}) mode={mode} left={left}")
            else:
                print(f"  -> Déplacement en (r={nr}, c={nc}). MOVE restant = {pool['MOVE']}")

            log(f"MOVE A: unit={u.name} from=({old_r},{old_c}) to=({nr},{nc}) MOVE_left={pool['MOVE']}")
            log(f"MOVE player=A from=({old_r},{old_c}) to=({nr},{nc}) unit={u.name}")
            trigger_trap_on_enter(state, u)

        # --- ATTAQUE ---
        elif action == "a":
            if pool["ATK"] <= 0:
                print("Pas d'ATK disponible.")
                continue
            if not units:
                print("Aucune unité pour attaquer.")
                continue

            print("\nUnités pouvant attaquer :")
            for idx, u in enumerate(units):
                print(f"  [{idx}] {u.name} "
                      f"({'Champ' if getattr(u,'is_champion',False) else 'Lv'+str(getattr(u,'level','?'))}) "
                      f"en (r={u.row}, c={u.col}) (HP={u.hp}, ATK={u.atk})")

            ch = input("Indice de l'unité (Enter pour annuler) : ").strip()
            if ch == "":
                continue
            try:
                idx_u = int(ch)
            except ValueError:
                print("Indice invalide.")
                continue
            if not (0 <= idx_u < len(units)):
                print("Indice invalide.")
                continue

            u = units[idx_u]
            if u.has_attacked:
                print("Cette unité a déjà attaqué ce tour.")
                continue

            enemies = list_enemies_adjacent(u)
            enemy_hq_r, enemy_hq_c = must_hq_fn("B")
            hq_adjacent = (manhattan(u.row, u.col, enemy_hq_r, enemy_hq_c) == 1)

            if not enemies and not hq_adjacent:
                print("Aucune cible adjacente (unités ou QG).")
                continue

            if enemies:
                print("\nCibles possibles :")
                for idx_t, v in enumerate(enemies):
                    print(f"  [{idx_t}] {v.name} (B) en (r={v.row}, c={v.col}) HP={v.hp}")
                if hq_adjacent:
                    print(f"  [H] QG B (HP={state.hq_B_hp})")
                ch_t = input("Cible (indice ou H) : ").strip().lower()
                if ch_t == "":
                    continue
                if ch_t == "h" and hq_adjacent:
                    state.damage_hq("B", u.atk, tag="melee_A", attacker_pos=(u.row, u.col))
                else:
                    try:
                        idx_t = int(ch_t)
                    except ValueError:
                        print("Choix invalide.")
                        continue
                    if not (0 <= idx_t < len(enemies)):
                        print("Choix invalide.")
                        continue
                    _bonus = get_passive_atk_bonus(state, u, enemies[idx_t])
                    if _bonus:
                        print(f"     [PASSIF] +{_bonus} ATK pour cette attaque.")
                    apply_damage_to_unit(state, enemies[idx_t], u.atk + _bonus, source_tag="melee_A", attacker=u)
            else:
                state.damage_hq("B", u.atk, tag="melee_A", attacker_pos=(u.row, u.col))

            u.has_attacked = True
            pool["ATK"] -= 1
            log(f"ATK A: unit={u.name} atk={u.atk} ATK_left={pool['ATK']}")

            if state.hq_B_hp <= 0:
                print("\n*** QG B détruit ! Joueur A gagne ! ***")
                log("GAME_END: winner=A reason=HQ_B_destroyed")
                return False

        # --- SKILL ---
        elif action == "s":
            candidates = [
                (idx, u) for idx, u in enumerate(units)
                if u.has_ability and u.ability_uses_this_turn < u.ability_max_per_turn
            ]
            if not candidates:
                print("Aucune capacité disponible ce tour.")
                continue

            print("\nUnités avec capacité :")
            for idx_u, u in candidates:
                print(f"  [{idx_u}] {u.name} "
                      f"({'Champ' if getattr(u,'is_champion',False) else 'Lv'+str(getattr(u,'level','?'))}) "
                      f"— {u.ability_name} (coût {u.ability_cost}) en (r={u.row}, c={u.col})")

            ch = input("Indice de l'unité qui utilise sa capacité (Enter pour annuler) : ").strip()
            if ch == "":
                continue
            try:
                idx_u = int(ch)
            except ValueError:
                print("Indice invalide.")
                continue
            if idx_u not in [i for (i, _) in candidates]:
                print("Indice invalide.")
                continue
            use_unit_ability(state, units[idx_u], "A")

        else:
            print("Action inconnue.")
            continue
