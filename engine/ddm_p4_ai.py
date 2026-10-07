"""
ddm_p4_ai.py
Phase mobs IA + logique de sélection de faction/champion pour l'IA.
Extrait de ddm_p4_loop.py lors du refacto 2026-02.
"""
from __future__ import annotations

import random as _random
import heapq as _heapq
from typing import Optional

from .ddm_p1_core import (
    GameState, UNITS, HEIGHT, WIDTH, P1_TILE, P2_TILE,
    log, build_default_ai_profile, apply_champion_modifier, get_game_phase,
)
from .ddm_p2_board_dice import pool_to_str
from .ddm_p3_mechanics import (
    apply_damage_to_unit, trigger_trap_on_enter,
    use_unit_ability, get_unit_at,
    find_enemy_adjacent, find_enemy_in_range,
    manhattan, reset_units_for_new_mob_phase,
    get_passive_atk_bonus,
    resolve_attack_redirect, get_atk_cost_surcharge, consume_atk_cost_surcharge,
)
from .ddm_p4_human import (
    maybe_trigger_despair_champion,
    maybe_trigger_despair_champion_A,
)

# Directions candidates autour d'un QG
_CAND_STEPS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


# ----------------------------------------------------------------------
#  SÉLECTION CHAMPION / FACTION IA
# ----------------------------------------------------------------------

def pick_champion_letter(faction_id: int, factions_data: list,
                         preferred: Optional[str] = None) -> str:
    """Retourne une lettre de champion valide pour la faction donnée."""
    fac = None
    for f in factions_data:
        if int(f.get("id", -1)) == int(faction_id):
            fac = f
            break
    champs = (fac.get("champions") if isinstance(fac, dict) else []) or []
    letters = [c.get("lettre") for c in champs if isinstance(c, dict) and c.get("lettre")]
    if preferred and preferred in letters:
        return preferred
    if letters:
        return _random.choice(letters)
    return "A"


# ----------------------------------------------------------------------
#  PHASE MOBS IA
# ----------------------------------------------------------------------

def phase_mobs_ai(state: GameState, owner: str, must_hq_fn) -> bool:
    """
    Phase unités pour l'IA contrôlant le camp `owner` ('A' ou 'B').
    Retourne True pour continuer la partie, False si un QG est détruit.
    """
    rng = getattr(state, "rng", None) or getattr(state, "random", None) or _random

    units = UNITS[owner]
    if owner == "A":
        pool = state.pool_A
        enemy = "B"
        profile = state.ai_profile_A
        if profile is None:
            profile = build_default_ai_profile(state.faction_A.get("name"))
            champ_A = state.faction_A.get("champion") or {}
            profile = apply_champion_modifier(
                profile,
                state.faction_A.get("name", ""),
                champ_A.get("lettre", "A")
            )
            state.ai_profile_A = profile
    else:
        pool = state.pool_B
        enemy = "A"
        profile = state.ai_profile_B
        if profile is None:
            profile = build_default_ai_profile(state.faction_B.get("name"))
            champ_B = state.faction_B.get("champion") or {}
            profile = apply_champion_modifier(
                profile,
                state.faction_B.get("name", ""),
                champ_B.get("lettre", "A")
            )
            state.ai_profile_B = profile

    print(pool_to_str(pool))

    if not units:
        return True
    if pool["MOVE"] <= 0 and pool["ATK"] <= 0:
        print(f"[IA {owner}] Plus de MOVE/ATK. Fin de phase mobs.")
        log(f"END_PHASE_MOBS_{owner} (no pool)")
        return True

    reset_units_for_new_mob_phase(owner)

    phase = get_game_phase(state, profile)
    _actions_executed = 0   # actions réelles ce tour (move, atk, skill)

    def in_bounds(r, c):
        return 0 <= r < HEIGHT and 0 <= c < WIDTH

    def is_walkable(r, c):
        return state.board[r][c] in (P1_TILE, P2_TILE)

    enemy_hq_row, enemy_hq_col = must_hq_fn(enemy)
    my_hq_row, my_hq_col = must_hq_fn(owner)
    enemy_units = UNITS[enemy]

    # --- Menaces et défense proactive ---
    my_hq_hp  = state.hq_A_hp  if owner == "A" else state.hq_B_hp
    my_hq_max = (state.hq_A_hp_max if owner == "A" else state.hq_B_hp_max) or 35
    my_hp_ratio = max(0.0, my_hq_hp / my_hq_max)

    # Infiltrateurs : ennemis ayant traversé la ligne médiane vers notre QG
    mid = HEIGHT // 2
    # Pour A (QG en bas), danger si ennemi en dessous du milieu
    # Pour B (QG en haut), danger si ennemi au-dessus du milieu
    if owner == "A":
        infiltrators = [e for e in enemy_units if e.hp > 0 and e.row > mid]
    else:
        infiltrators = [e for e in enemy_units if e.hp > 0 and e.row < mid]

    # Menaces directes adjacentes au QG
    hq_threats = [
        e for e in enemy_units
        if e.hp > 0 and manhattan(e.row, e.col, my_hq_row, my_hq_col) <= 3
    ]

    defenders = set()
    emergency_def = False
    rear_guards   = set()

    # Urgence défensive selon QG HP
    def_urgency = 1.0 - my_hp_ratio   # 0.0 QG intact → 1.0 QG détruit

    # 1) Défense d'urgence — ennemi adjacent au QG
    if hq_threats:
        emergency_def = True
        candidates = sorted(
            [u for u in units if u.hp > 0],
            key=lambda u: (
                manhattan(u.row, u.col, my_hq_row, my_hq_col),
                -(u.defense + getattr(u, "temp_def", 0)),
                -u.hp,
            ),
        )
        n_def = 2 if def_urgency >= 0.4 else 1
        defenders = set(candidates[:n_def])
        emergency_def = True
        print(f"[IA {owner}] URGENCE DEF : {len(defenders)} unité(s) désignées QG.")
        log(f"EMERGENCY_DEF_{owner}: threats={len(hq_threats)} defenders={len(defenders)} hp_ratio={my_hp_ratio:.2f}")

    # 2) Garde arrière probabiliste — dépend du profil faction, pas déterministe
    # L'IA peut décider seule quelle unité garder — le RL découvrira l'optimal
    if not emergency_def:
        n_units_alive = len([u for u in units if u.hp > 0])
        aggro_w = profile.get("aggro_weight", 1.0)

        # Seuil minimal d'unités avant d'envisager un garde
        guard_threshold = 3 if aggro_w <= 1.0 else 4  # factions agressives patientent plus

        # Probabilité de désigner un garde — inversement proportionnelle à l'agressivité
        # aggro=0.85 (Égypte) → p≈44%  |  aggro=1.0 (Humains) → p≈30%  |  aggro=1.5 (Orcs) → p=0%
        p_guard = max(0.0, (1.0 - aggro_w) * 0.6)

        # Bonus probabilité si des infiltrateurs sont déjà dans notre moitié
        if infiltrators:
            p_guard = min(1.0, p_guard + 0.25 * len(infiltrators))

        if n_units_alive >= guard_threshold and rng.random() < p_guard:
            # Sélection ALÉATOIRE parmi les candidats — le RL apprend quelle unité est optimale
            guard_candidates = [u for u in units if u.hp > 0 and u not in defenders]
            if guard_candidates:
                chosen = rng.choice(guard_candidates)
                rear_guards = {chosen}
                print(f"[IA {owner}] GARDE ARRIÈRE : {chosen.name} désigné (p={p_guard:.2f} infiltrators={len(infiltrators)}).")
                log(f"REAR_GUARD_{owner}: unit={chosen.name} p={p_guard:.2f} infiltrators={len(infiltrators)} n_units={n_units_alive}")

    print(f"\n=== Phase unités (IA {owner}) ===")
    log(f"START_PHASE_MOBS_{owner}")

    # --- Abilities via TRAP (coûts définis en TRAP dans le JSON) ---
    if pool.get("CAP", 0) > 0:
        candidates = [
            u for u in units
            if getattr(u, "has_ability", False) and u.ability_uses_this_turn < u.ability_max_per_turn
            and not getattr(u, "skip_next_turn", False)
            and not getattr(u, "stunned", 0)
        ]
        rng.shuffle(candidates)
        used = 0
        for u in candidates:
            if pool.get("CAP", 0) <= 0 or used >= 1:
                break

            # Pré-filtre décisionnel : ne pas tenter une ability offensive si aucune cible valide
            etype    = (u.ability_effects or {}).get("type") or (u.ability_effects or {}).get("effect_type")
            t_type   = getattr(u, "ability_target_type", None) or (u.ability_effects or {}).get("target_type") or "enemy"
            ab_range = getattr(u, "ability_range", None) or (u.ability_effects or {}).get("range", 2) or 2

            need_target = etype in (
                "damage", "ranged_damage", "direct_damage",
                "true_damage", "poison", "apply_status", "apply_debuff"
            ) and t_type in ("enemy", "auto_enemy", "enemy_only")

            need_threat = etype == "buff_def"  # buff défensif inutile sans menace proche

            if need_target:
                if not find_enemy_in_range(owner, u.row, u.col, rng=ab_range):
                    log(f"ABILITY_SKIP_{owner}: unit={u.name} type={etype} reason=no_target_in_range")
                    continue
            elif need_threat:
                if not find_enemy_in_range(owner, u.row, u.col, rng=5):
                    log(f"ABILITY_SKIP_{owner}: unit={u.name} type=buff_def reason=no_threat_nearby")
                    continue

            try:
                ok = use_unit_ability(state, u, owner)
            except Exception:
                ok = False
            if ok:
                used += 1

    # --- Désespoir champion ---
    if owner == "A":
        maybe_trigger_despair_champion_A(state, must_hq_fn)
    else:
        maybe_trigger_despair_champion(state, must_hq_fn)

    # --- Sleep Dash ---
    dash_attr = "sleep_dash_left_A" if owner == "A" else "sleep_dash_left_B"
    champ_state = state.champion_A_state if owner == "A" else state.champion_B_state
    setattr(state, dash_attr, 2 if champ_state == "dormant" else 0)
    log(f"SLEEP_DASH_INIT_{owner} left={getattr(state, dash_attr, 0)} champion_state={champ_state}")

    # --- Détection frozen front + assignation trident ---
    # Un frozen front se caractérise par : beaucoup d'unités ennemies dans notre moitié,
    # aucun dégât au QG adverse depuis plusieurs tours, et une large ligne de contact.
    mem_mv = getattr(state, f"rl_memory_{owner}", {})
    last_dmg_turn = mem_mv.get("last_dmg_turn", 0)
    turns_since_dmg = state.turn - last_dmg_turn

    # Ennemis vivants sur toute la largeur (colonnes distinctes) → front large
    enemy_cols = {e.col for e in enemy_units if e.hp > 0}
    front_width = len(enemy_cols)
    frozen_front = (turns_since_dmg >= 8 and front_width >= 5)
    # Stocker dans mémoire pour le tracker RL
    mem_mv["frozen_front"]     = frozen_front
    mem_mv["turns_since_dmg"]  = int(turns_since_dmg)
    mem_mv["front_width"]      = int(front_width)
    setattr(state, f"rl_memory_{owner}", mem_mv)

    # Assignation trident : LEFT / CENTER / RIGHT parmi les unités offensives
    # (exclut defenders et rear_guards)
    trident_roles = {}   # unit → ("left"|"center"|"right")
    if frozen_front:
        offensive = [u for u in units if u.hp > 0
                     and u not in defenders and u not in rear_guards]
        # Trier par colonne actuelle pour répartir naturellement
        offensive_sorted = sorted(offensive, key=lambda u: u.col)
        n_off = len(offensive_sorted)
        if n_off >= 3:
            # Premier tiers → flanc gauche, dernier tiers → flanc droit, milieu → center
            split = max(1, n_off // 3)
            for i, u in enumerate(offensive_sorted):
                if i < split:
                    trident_roles[id(u)] = "left"
                elif i >= n_off - split:
                    trident_roles[id(u)] = "right"
                else:
                    trident_roles[id(u)] = "center"
            log(f"TRIDENT_{owner}: frozen_front={frozen_front} width={front_width} "
                f"turns_since_dmg={turns_since_dmg} units={n_off}")
            print(f"[IA {owner}] PERCÉE TRIDENT : front figé depuis {turns_since_dmg} tours "
                  f"({n_off} unités réparties L/C/R)")
            # Mémoriser pour tracking RL
            mem_mv["trident_active"] = True
            setattr(state, f"rl_memory_{owner}", mem_mv)

    # Colonnes cibles par rôle (flancs décalés de ±3 par rapport au QG central)
    flank_offset = max(2, min(4, WIDTH // 5))
    trident_targets = {
        "left"  : (enemy_hq_row, max(0, enemy_hq_col - flank_offset)),
        "center": (enemy_hq_row, enemy_hq_col),
        "right" : (enemy_hq_row, min(WIDTH - 1, enemy_hq_col + flank_offset)),
    }

    # --- DÉPLACEMENT IA ---
    if pool["MOVE"] > 0:
        for _ in range(20):  # anti-boucle infinie
            if pool["MOVE"] <= 0:
                break
            moved_this_loop = False

            for u in list(units):
                if pool["MOVE"] <= 0:
                    break
                if u.hp <= 0 or u.has_moved:
                    continue

                # Escalade temporelle — défini ici pour tout le bloc mouvement
                max_rounds_mv  = getattr(state, "max_rounds", 120)
                urgency_mv     = min(1.0, state.turn / max_rounds_mv)
                ESCALADE_START = 0.65
                ESCALADE_MAX   = 0.85

                if emergency_def and u in defenders and hq_threats:
                    # Urgence : aller interceper la menace la plus proche
                    threat = min(hq_threats, key=lambda e: manhattan(u.row, u.col, e.row, e.col))
                    tgt_r, tgt_c = threat.row, threat.col
                elif u in rear_guards and infiltrators:
                    # Garde arrière : intercepter l'infiltrateur le plus proche du QG
                    threat = min(infiltrators, key=lambda e: manhattan(e.row, e.col, my_hq_row, my_hq_col))
                    tgt_r, tgt_c = threat.row, threat.col
                elif id(u) in trident_roles:
                    # Percée trident : viser le flanc assigné
                    role = trident_roles[id(u)]
                    tgt_r, tgt_c = trident_targets[role]
                else:
                    # Escalade temporelle % based
                    any_adj_hq = any(
                        manhattan(uu.row, uu.col, enemy_hq_row, enemy_hq_col) <= 2
                        for uu in units if uu.hp > 0
                    )
                    if urgency_mv >= ESCALADE_MAX:
                        # Mêlée finale : ignorer toutes les unités, foncer sur le QG
                        force_hq_push = True
                        if urgency_mv >= ESCALADE_MAX and state.turn % 5 == 0:
                            print(f"[IA {owner}] ESCALADE FINALE ({int(urgency_mv*100)}%) — rush QG")
                    elif urgency_mv >= ESCALADE_START:
                        # Pression forte : ignorer unités si personne au QG
                        force_hq_push = not any_adj_hq
                    else:
                        force_hq_push = False
                    target_unit = None if force_hq_push else find_enemy_in_range(owner, u.row, u.col, rng=4)
                    if target_unit is not None:
                        tgt_r, tgt_c = target_unit.row, target_unit.col
                    else:
                        tgt_r, tgt_c = enemy_hq_row, enemy_hq_col

                # --- Pathfinding adaptatif : mode selon profil + phase ---
                # aggressive : Dijkstra → A* → Greedy
                # balanced   : Dijkstra → A* → A*
                # defensive  : Dijkstra → Dijkstra → A*
                pf_mode_base = profile.get("pathfinding_mode", "balanced")
                if urgency_mv >= ESCALADE_MAX:
                    if pf_mode_base == "aggressive":
                        pf_algo = "greedy"
                    else:
                        pf_algo = "astar"
                elif urgency_mv >= ESCALADE_START:
                    if pf_mode_base == "defensive":
                        pf_algo = "dijkstra"
                    else:
                        pf_algo = "astar"
                else:
                    pf_algo = "dijkstra"

                def _tile_cost(r, c):
                    other, _ = get_unit_at(r, c)
                    if other is not None:
                        return 999
                    enemy_adj = sum(
                        1 for dr2, dc2 in _CAND_STEPS
                        if in_bounds(r + dr2, c + dc2)
                        and any(
                            eu.row == r + dr2 and eu.col == c + dc2
                            for eu in UNITS[enemy] if eu.hp > 0
                        )
                    )
                    return 1 + enemy_adj * 2

                best_step = None

                if pf_algo == "greedy":
                    # Greedy Manhattan pur — kamikaze, pas de calcul de coût
                    best_dist = manhattan(u.row, u.col, tgt_r, tgt_c)
                    for dr2, dc2 in _CAND_STEPS:
                        nr2, nc2 = u.row + dr2, u.col + dc2
                        if not in_bounds(nr2, nc2) or not is_walkable(nr2, nc2):
                            continue
                        other, _ = get_unit_at(nr2, nc2)
                        if other is not None:
                            continue
                        dist_new = manhattan(nr2, nc2, tgt_r, tgt_c)
                        if dist_new < best_dist:
                            best_step = (nr2, nc2)
                            best_dist = dist_new

                else:
                    # Dijkstra (pf_algo=="dijkstra") ou A* (pf_algo=="astar")
                    # A* ajoute l'heuristique manhattan dans la priorité du heap
                    _dist = {(u.row, u.col): 0}
                    _prev = {}
                    h_factor = 1 if pf_algo == "astar" else 0
                    _heap = [(h_factor * manhattan(u.row, u.col, tgt_r, tgt_c), 0, u.row, u.col)]
                    while _heap:
                        _, d, r, c = _heapq.heappop(_heap)
                        if d > _dist.get((r, c), 999):
                            continue
                        if (r, c) == (tgt_r, tgt_c):
                            break
                        for dr2, dc2 in _CAND_STEPS:
                            nr2, nc2 = r + dr2, c + dc2
                            if not in_bounds(nr2, nc2) or not is_walkable(nr2, nc2):
                                continue
                            cost = _tile_cost(nr2, nc2)
                            nd = d + cost
                            if nd < _dist.get((nr2, nc2), 999):
                                _dist[(nr2, nc2)] = nd
                                _prev[(nr2, nc2)] = (r, c)
                                h = h_factor * manhattan(nr2, nc2, tgt_r, tgt_c)
                                _heapq.heappush(_heap, (nd + h, nd, nr2, nc2))

                    if (tgt_r, tgt_c) in _prev or (tgt_r, tgt_c) == (u.row, u.col):
                        node = (tgt_r, tgt_c)
                        while _prev.get(node) != (u.row, u.col) and node in _prev:
                            node = _prev[node]
                        if node != (u.row, u.col) and node in _dist:
                            nr2, nc2 = node
                            other, _ = get_unit_at(nr2, nc2)
                            if other is None and is_walkable(nr2, nc2):
                                best_step = node

                    # Fallback greedy si aucun chemin trouvé (territoires non connectés)
                    if best_step is None:
                        best_dist = manhattan(u.row, u.col, tgt_r, tgt_c)
                        for dr2, dc2 in _CAND_STEPS:
                            nr2, nc2 = u.row + dr2, u.col + dc2
                            if not in_bounds(nr2, nc2) or not is_walkable(nr2, nc2):
                                continue
                            other, _ = get_unit_at(nr2, nc2)
                            if other is not None:
                                continue
                            dist_new = manhattan(nr2, nc2, tgt_r, tgt_c)
                            if dist_new < best_dist:
                                best_step = (nr2, nc2)
                                best_dist = dist_new

                if best_step is None:
                    continue

                # immovable : unité protégée par aura Sphinx
                if getattr(u, "immovable", False):
                    continue

                old_r, old_c = u.row, u.col
                dest = best_step
                dash_used = False

                # Tentative dash
                if (
                    champ_state == "dormant"
                    and getattr(state, dash_attr, 0) > 0
                    and not u.is_champion
                    and getattr(u, "level", 99) <= 2
                ):
                    dr = dest[0] - u.row
                    dc = dest[1] - u.col
                    nr2, nc2 = u.row + 2 * dr, u.col + 2 * dc
                    if in_bounds(nr2, nc2) and is_walkable(nr2, nc2):
                        other2, _ = get_unit_at(nr2, nc2)
                        if other2 is None:
                            if manhattan(nr2, nc2, tgt_r, tgt_c) <= manhattan(dest[0], dest[1], tgt_r, tgt_c):
                                dest = (nr2, nc2)
                                dash_used = True

                u.row, u.col = dest
                u.has_moved = True
                pool["MOVE"] -= 1

                if dash_used:
                    setattr(state, dash_attr, max(0, getattr(state, dash_attr, 0) - 1))
                    print(f"[IA {owner}] {u.name} DASH de ({old_r},{old_c}) vers {dest}. "
                          f"MOVE {owner} restant = {pool['MOVE']} | dash_left={getattr(state, dash_attr, 0)}")
                    log(f"SLEEP_DASH_USED_{owner}: unit={u.name} from=({old_r},{old_c}) "
                        f"to={dest} left={getattr(state, dash_attr, 0)}")
                else:
                    print(f"[IA {owner}] {u.name} se déplace de ({old_r},{old_c}) "
                          f"vers {dest}. MOVE {owner} restant = {pool['MOVE']}")

                log(f"MOVE_{owner}: unit={u.name} from=({old_r},{old_c}) to={dest} MOVE_left={pool['MOVE']}")
                try:
                    from .ddm_snapshot import log_append as _la
                    _la(state, f"[MOV] {owner} {u.name} ({old_r},{old_c}) → {dest}")
                except Exception:
                    pass
                _actions_executed += 1
                nr, nc = dest
                log(f"MOVE player={owner} from=({old_r},{old_c}) to=({nr},{nc}) unit={u.name}")
                trigger_trap_on_enter(state, u)
                moved_this_loop = True
                if pool["MOVE"] <= 0:
                    break

            if not moved_this_loop:
                break

    # --- ATTAQUE IA ---
    if pool["ATK"] > 0:
        style = profile.get("style", "balanced")
        aggro_base = profile.get("aggro_weight", 1.0)

        # Pression dynamique — basée sur l'état des QG, indépendante du timeout
        opp_hq_hp    = state.hq_B_hp if owner == "A" else state.hq_A_hp
        my_hq_hp     = state.hq_A_hp if owner == "A" else state.hq_B_hp
        opp_hq_max   = (state.hq_B_hp_max if owner == "A" else state.hq_A_hp_max) or 35
        my_hq_max    = (state.hq_A_hp_max if owner == "A" else state.hq_B_hp_max) or 35
        opp_hp_ratio = max(0.0, opp_hq_hp / opp_hq_max)   # 1.0=intact 0.0=détruit
        my_hp_ratio  = max(0.0, my_hq_hp  / my_hq_max)    # 1.0=intact 0.0=danger
        # Poids par faction+champion (définis dans apply_champion_modifier)
        uw_state     = profile.get("urgency_state_w", 0.25)
        uw_tempo     = profile.get("urgency_tempo_w", 0.20)
        # Abominations : logique variable selon l'état du jeu
        abom_mod     = profile.get("abom_champion_mod", "none")
        if abom_mod != "none":
            hp_gap = abs(opp_hp_ratio - my_hp_ratio)
            if abom_mod == "reduce_state":
                uw_state = 0.15 if hp_gap < 0.20 else 0.35
            elif abom_mod == "amplify_peaks":
                uw_state = 0.20 if hp_gap < 0.20 else 0.60
                uw_tempo = 0.50 if state.turn > 100 else 0.05
            elif abom_mod == "boost_state":
                uw_state = 0.15 if hp_gap < 0.20 else 0.55
            else:  # défaut Abominations
                uw_state = 0.15 if hp_gap < 0.20 else 0.50
                uw_tempo = 0.10 if state.turn <= 100 else 0.40
        # --- Logique dynamique Reptiliens : boost si adversaire isolé (aggro_seq) ---
        if profile.get("dynamic_aggro") and owner in ("A", "B"):
            mem_opp = getattr(state, f"rl_memory_{owner}", {})
            aggro_seq = mem_opp.get("aggro_seq", 0)
            # Si l'adversaire a perdu plusieurs unités consécutivement → Reptiliens frappent
            if aggro_seq >= 2:
                uw_state = min(uw_state + 0.08 * min(aggro_seq, 3), 0.50)

        # --- Logique variable Égypte : frappe quand QG adverse < 30% ---
        if profile.get("egypt_trigger"):
            if opp_hp_ratio <= 0.30:
                uw_state = min(uw_state * 3.0, 0.40)   # décuple la réactivité offensive
                uw_tempo = min(uw_tempo * 3.0, 0.20)   # et la pression tempo
            elif opp_hp_ratio <= 0.50:
                uw_state = min(uw_state * 1.8, 0.25)   # pression modérée à mi-chemin

        urgency_state = (1.0 - opp_hp_ratio) * uw_state    # opportunisme offensif
        urgency_def   = (1.0 - my_hp_ratio)  * uw_tempo    # pression défensive
        aggro         = aggro_base * (1.0 + urgency_state + urgency_def)
        log(f"AGGRO_DYN_{owner}: base={aggro_base:.2f} us={urgency_state:.2f} "
            f"ud={urgency_def:.2f} final={aggro:.2f} opp_hp={opp_hp_ratio:.2f}")

        def want_hq_focus(phase_name: str, has_enemy_adjacent: bool) -> bool:
            phase_scores = {"early": 0, "mid": 1, "late": 2, "overtime": 3}
            phase_score = phase_scores.get(phase_name, 1)
            base_threshold = 2
            adj = 0
            if aggro > 1.2:
                adj = -1
            elif aggro < 0.9:
                adj = +1
            threshold = max(0, min(3, base_threshold + adj))
            if not has_enemy_adjacent:
                return True
            return phase_score >= threshold

        for u in list(units):
            surcharge = get_atk_cost_surcharge(u)
            if pool["ATK"] <= surcharge:
                if surcharge > 0:
                    log(f"ATK_SKIP_{owner}: unit={u.name} surcharge={surcharge} ATK={pool['ATK']}")
                elif pool["ATK"] <= 0:
                    break
                continue
            if u.hp <= 0 or u.has_attacked:
                continue

            enemy_adj = find_enemy_adjacent(owner, u.row, u.col)
            enemy_hq_adjacent = (manhattan(u.row, u.col, enemy_hq_row, enemy_hq_col) == 1)

            if enemy_adj is None and not enemy_hq_adjacent:
                continue

            # Résolution des redirections (confusion / random / ally-redirect)
            if enemy_adj is not None:
                enemy_adj, _redirected = resolve_attack_redirect(state, u, owner, enemy_adj)

            if enemy_hq_adjacent and (enemy_adj is None or want_hq_focus(phase, enemy_adj is not None)):
                print(f"[IA {owner}] {u.name} frappe le QG {enemy} !")
                state.damage_hq(enemy, u.atk, tag=f"melee_{owner}", attacker_pos=(u.row, u.col))
                try:
                    from .ddm_snapshot import log_append as _la
                    qg_hp = state.hq_A_hp if enemy == "A" else state.hq_B_hp
                    _la(state, f"[ATK] {owner} {u.name} → QG {enemy} (-{u.atk}) HP={qg_hp}")
                except Exception:
                    pass
                _mem = getattr(state, f"rl_memory_{owner}", {})
                _mem["last_dmg_turn"] = state.turn
                setattr(state, f"rl_memory_{owner}", _mem)
            elif enemy_adj is not None:
                _bonus = get_passive_atk_bonus(state, u, enemy_adj)
                print(f"[IA {owner}] {u.name} attaque {enemy_adj.name} ({enemy_adj.owner}).")
                apply_damage_to_unit(state, enemy_adj, u.atk + _bonus, source_tag=f"melee_{owner}", attacker=u)
                try:
                    from .ddm_snapshot import log_append as _la
                    _la(state, f"[ATK] {owner} {u.name} → {enemy_adj.name} (-{u.atk + _bonus}) HP={enemy_adj.hp}")
                except Exception:
                    pass
            else:
                continue  # ni QG ni cible — skip sans consommer ATK

            surcharge_paid = consume_atk_cost_surcharge(u)
            pool["ATK"] -= 1 + surcharge_paid
            u.has_attacked = True
            _actions_executed += 1
            log(f"ATK_{owner}: unit={u.name} atk={u.atk} ATK_left={pool['ATK']}")

            if enemy == "A":
                if state.hq_A_hp <= 0:
                    print(f"\n*** QG A détruit ! IA côté {owner} gagne ! ***")
                    log(f"GAME_END: winner={owner} reason=HQ_A_destroyed")
                    try:
                        from .ddm_snapshot import log_append as _la
                        _la(state, f"[FIN] QG A détruit ! {owner} gagne !")
                    except Exception:
                        pass
                    return False
            else:
                if state.hq_B_hp <= 0:
                    print(f"\n*** QG B détruit ! IA côté {owner} gagne ! ***")
                    log(f"GAME_END: winner={owner} reason=HQ_B_destroyed")
                    try:
                        from .ddm_snapshot import log_append as _la
                        _la(state, f"[FIN] QG B détruit ! {owner} gagne !")
                    except Exception:
                        pass
                    return False

    # --- Fin de phase : classifier pass forcé vs volontaire ---
    move_left = pool.get("MOVE", 0) or 0
    atk_left  = pool.get("ATK", 0) or 0
    cap_left  = pool.get("CAP", 0) or 0
    any_pool_left = (move_left + atk_left + cap_left) > 0
    enemies_alive = [e for e in UNITS[enemy] if e.hp > 0]
    # pass_avoidable = AUCUNE action exécutée ce tour alors que pool + ennemis existaient
    if _actions_executed == 0 and any_pool_left and enemies_alive:
        pass_type = "voluntary_pool_left"   # vrai pass évitable
    elif any_pool_left:
        pass_type = "spent_pool"            # pool restant NORMAL après avoir joué ses unités
    else:
        pass_type = "no_resource"           # pool vide
    log(f"END_PHASE_MOBS_{owner} pass_type={pass_type} actions={_actions_executed} move_left={move_left} atk_left={atk_left} cap_left={cap_left}")
    try:
        ctx = getattr(state, "rl_turn_ctx", None)
        if isinstance(ctx, dict) and ctx.get("enabled") and not ctx.get("pass_forced", False):
            ctx["pass_avoidable"]    = (pass_type == "voluntary_pool_left")
            ctx["pass_forced"]       = (pass_type == "no_resource")
            ctx["actions_executed"]  = _actions_executed
    except Exception:
        pass
    return True
