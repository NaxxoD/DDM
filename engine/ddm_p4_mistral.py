"""
ddm_p4_mistral.py
Phase mobs — Agent Mistral Équilibre-style

Philosophie : jeu calculé et technique, optimisation des ressources (pool),
précision et gestion des risques. Positionnement tactique coordonné.

Source : Mistral Équilibre (lite) — profil collecté via prompt_standard.md
  Faction    : 4 — Cyborgs — Système Oméga
  Champion   : B — Analyste du Code
  Style      : optimisation ressources, unités bien placées, contrôle précis
  Évite      : Fractaux Oniriques (chaos perturbe la précision)
  Voulu      : Orcs (counter rush brut par calcul)

Différences vs Claude bot :
  - Mouvement : score positionnel hybride (QG pressure + flanking + défense)
    au lieu de force_hq aveugle
  - Risk management : 1 défenseur redirigé si QG allié menacé
  - Abilities : utilise tout le pool CAP disponible (pas cappé à 1)
  - Pool optimization : second pass si MOVE résiduel après boucle principale
"""
from __future__ import annotations

import json
import random as _random
import heapq as _heapq
from pathlib import Path

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
)
from .ddm_p4_human import (
    maybe_trigger_despair_champion,
    maybe_trigger_despair_champion_A,
)

_CAND_STEPS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

# ─── Préférences & mini bandit ────────────────────────────────────────────────

PREFS_PATH = Path(__file__).parent.parent / "data" / "mistral_prefs.json"

DEFAULT_PREFS = {
    "preferred"              : {"faction": 4, "champion": "B"},  # Cyborgs / Analyste du Code
    "history"                : {},
    "exploration_rate"       : 0.15,
    "min_games_before_switch": 20,
}


def load_prefs() -> dict:
    if PREFS_PATH.exists():
        try:
            return json.loads(PREFS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(DEFAULT_PREFS)


def save_prefs(prefs: dict):
    try:
        PREFS_PATH.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def record_result(faction_id: int, champion: str, won: bool):
    prefs = load_prefs()
    key   = f"{faction_id}_{champion}"
    hist  = prefs.setdefault("history", {})
    entry = hist.setdefault(key, {"wins": 0, "losses": 0, "games": 0})
    entry["games"] += 1
    if won:
        entry["wins"] += 1
    else:
        entry["losses"] += 1

    pref_key  = "{faction}_{champion}".format(**prefs["preferred"])
    pref_wr   = _winrate(hist.get(pref_key, {}))
    min_games = prefs.get("min_games_before_switch", 20)

    for k, v in hist.items():
        if k == pref_key or v["games"] < min_games:
            continue
        if _winrate(v) > pref_wr + 0.10:
            parts = k.split("_", 1)
            if len(parts) == 2:
                prefs["preferred"] = {"faction": int(parts[0]), "champion": parts[1]}
                log(f"MISTRAL_PREF_SWITCH: new={k} wr={_winrate(v):.2f} old_wr={pref_wr:.2f}")
            break

    save_prefs(prefs)


def _winrate(entry: dict) -> float:
    g = entry.get("games", 0)
    return entry.get("wins", 0) / g if g > 0 else 0.5


def get_mistral_faction_pref(faction_ids: list) -> tuple[int, str]:
    prefs = load_prefs()
    if _random.random() < prefs.get("exploration_rate", 0.15) and len(faction_ids) > 1:
        pref_fid = prefs["preferred"]["faction"]
        choices  = [f for f in faction_ids if f != pref_fid]
        fid      = _random.choice(choices) if choices else pref_fid
        champ    = _random.choice(["A", "B", "C", "D", "E"])
        log(f"MISTRAL_EXPLORE: faction={fid} champion={champ}")
        return fid, champ

    p = prefs["preferred"]
    log(f"MISTRAL_SELECT: faction={p['faction']} champion={p['champion']}")
    return p["faction"], p["champion"]


# ─── Scoring des cibles (attaque) ─────────────────────────────────────────────

def score_enemy(unit, attacker_atk: int, enemy_hq_r: int, enemy_hq_c: int) -> float:
    """
    Score une cible ennemie pour priorisation d'attaque.
    Priorités : kill potentiel > blessé > proche QG ennemi.
    Identique à Claude — l'attaque reste une logique universelle.
    """
    hp_max       = getattr(unit, "hp_max", unit.hp) or unit.hp
    hp_ratio     = unit.hp / max(hp_max, 1)
    kill_shot    = attacker_atk >= unit.hp
    hq_proximity = 1.0 / (manhattan(unit.row, unit.col, enemy_hq_r, enemy_hq_c) + 1)

    score  = 200.0 if kill_shot else 0.0
    score += (1.0 - hp_ratio) * 60.0
    score += hq_proximity * 25.0
    return score


# ─── Scoring positionnel (mouvement) ─────────────────────────────────────────

def score_position(pos_r: int, pos_c: int, unit,
                   enemy_hq_r: int, enemy_hq_c: int,
                   enemy_units: list, ally_units: list) -> float:
    """
    Score tactique d'une position pour le mouvement.

    Composantes :
      - QG pressure  : proximité du QG ennemi (objectif principal)
      - ATK reach    : ennemis attaquables depuis cette case
      - Flanking     : alliés proches = coordination
    """
    dist_to_enemy_qg = manhattan(pos_r, pos_c, enemy_hq_r, enemy_hq_c)

    # QG pressure
    qg_score = 40.0 / (dist_to_enemy_qg + 1)
    if dist_to_enemy_qg == 1:
        qg_score += 30.0

    # Reach : ennemis adjacents depuis cette position
    reach_score = sum(
        15.0 for e in enemy_units
        if e.hp > 0 and manhattan(pos_r, pos_c, e.row, e.col) == 1
    )

    # Flanking : alliés à portée 2
    flank_score = sum(
        6.0 for a in ally_units
        if a.hp > 0 and a is not unit and manhattan(pos_r, pos_c, a.row, a.col) <= 2
    )

    return qg_score + reach_score + flank_score


# ─── Abilities intelligentes ─────────────────────────────────────────────────

def _try_ability_smart(state, unit, owner: str, enemy_hq_r: int, enemy_hq_c: int) -> bool:
    """
    Tente l'ability. Identique à Claude bot — logique de ciblage universelle.
    """
    etype    = (unit.ability_effects or {}).get("type") or ""
    ab_range = getattr(unit, "ability_range", None) or (unit.ability_effects or {}).get("range", 2) or 2

    if etype in ("heal", "hot", "heal_self"):
        allies = [u for u in UNITS[owner] if u.hp > 0]
        if not allies:
            return False
        most_wounded = min(allies, key=lambda u: u.hp / max(getattr(u, "hp_max", u.hp), 1))
        hp_max = getattr(most_wounded, "hp_max", most_wounded.hp) or most_wounded.hp
        if most_wounded.hp / hp_max > 0.80:
            log(f"MISTRAL_STRAT_{owner} ability_skip unit={unit.name} reason=allies_healthy")
            return False
        log(f"MISTRAL_STRAT_{owner} ability=heal target={most_wounded.name} hp={most_wounded.hp}")

    elif etype in ("buff_def", "buff_def_and_counter", "armor_break"):
        if not find_enemy_in_range(owner, unit.row, unit.col, rng=3):
            log(f"MISTRAL_STRAT_{owner} ability_skip unit={unit.name} reason=no_threat_nearby")
            return False

    elif etype in (
        "damage", "ranged_damage", "direct_damage", "true_damage",
        "poison", "apply_status", "debuff_atk", "execute_crit", "aoe_damage",
    ):
        targets = _enemies_in_range(owner, unit.row, unit.col, ab_range)
        if not targets:
            log(f"MISTRAL_STRAT_{owner} ability_skip unit={unit.name} reason=no_target")
            return False
        best = max(targets, key=lambda e: score_enemy(e, unit.atk, enemy_hq_r, enemy_hq_c))
        log(f"MISTRAL_STRAT_{owner} ability={etype} unit={unit.name} target={best.name} hp={best.hp}")

    try:
        ok = use_unit_ability(state, unit, owner)
    except Exception:
        ok = False
    return ok


def _enemies_in_range(owner: str, row: int, col: int, rng: int):
    enemy = "B" if owner == "A" else "A"
    return [
        e for e in UNITS[enemy]
        if e.hp > 0 and manhattan(e.row, e.col, row, col) <= rng
    ]


# ─── Pathfinding (A*) ────────────────────────────────────────────────────────

def _astar_step(state, unit, tgt_r: int, tgt_c: int):
    """Retourne la prochaine case vers (tgt_r, tgt_c) via A*, ou None."""
    def in_bounds(r, c):
        return 0 <= r < HEIGHT and 0 <= c < WIDTH

    def is_walkable(r, c):
        return state.board[r][c] in (P1_TILE, P2_TILE)

    def tile_cost(r, c):
        other, _ = get_unit_at(r, c)
        return 999 if other is not None else 1

    _dist = {(unit.row, unit.col): 0}
    _prev = {}
    _heap = [(manhattan(unit.row, unit.col, tgt_r, tgt_c), 0, unit.row, unit.col)]

    while _heap:
        _, d, r, c = _heapq.heappop(_heap)
        if d > _dist.get((r, c), 999):
            continue
        if (r, c) == (tgt_r, tgt_c):
            break
        for dr, dc in _CAND_STEPS:
            nr, nc = r + dr, c + dc
            if not in_bounds(nr, nc) or not is_walkable(nr, nc):
                continue
            nd = d + tile_cost(nr, nc)
            if nd < _dist.get((nr, nc), 999):
                _dist[(nr, nc)] = nd
                _prev[(nr, nc)] = (r, c)
                _heapq.heappush(_heap, (nd + manhattan(nr, nc, tgt_r, tgt_c), nd, nr, nc))

    if (tgt_r, tgt_c) in _prev or (tgt_r, tgt_c) == (unit.row, unit.col):
        node = (tgt_r, tgt_c)
        while _prev.get(node) != (unit.row, unit.col) and node in _prev:
            node = _prev[node]
        if node != (unit.row, unit.col):
            nr, nc = node
            other, _ = get_unit_at(nr, nc)
            if other is None and is_walkable(nr, nc):
                return node

    best, best_d = None, manhattan(unit.row, unit.col, tgt_r, tgt_c)
    for dr, dc in _CAND_STEPS:
        nr, nc = unit.row + dr, unit.col + dc
        if not in_bounds(nr, nc) or not is_walkable(nr, nc):
            continue
        other, _ = get_unit_at(nr, nc)
        if other is not None:
            continue
        d = manhattan(nr, nc, tgt_r, tgt_c)
        if d < best_d:
            best, best_d = (nr, nc), d
    return best


# ─── Phase principale ─────────────────────────────────────────────────────────

def phase_mobs_mistral(state: GameState, owner: str, must_hq_fn) -> bool:
    """
    Phase unités — Agent Mistral Équilibre-style.
    Retourne True pour continuer, False si un QG est détruit.
    """
    units   = UNITS[owner]
    enemy   = "B" if owner == "A" else "A"
    pool    = state.pool_A if owner == "A" else state.pool_B

    print(pool_to_str(pool))

    if not units:
        return True
    if pool["MOVE"] <= 0 and pool["ATK"] <= 0:
        log(f"MISTRAL_END_PHASE_{owner} reason=no_pool")
        return True

    reset_units_for_new_mob_phase(owner)

    enemy_hq_r, enemy_hq_c = must_hq_fn(enemy)
    my_hq_r,    my_hq_c    = must_hq_fn(owner)
    enemy_units = UNITS[enemy]
    _actions    = 0

    print(f"\n=== Phase unités (Mistral {owner}) ===")
    log(f"MISTRAL_START_PHASE_{owner}")

    # ── 1. Abilities — utilise tout le pool CAP (optimisation ressources) ───────
    if pool.get("CAP", 0) > 0:
        def ability_priority(u):
            etype = (u.ability_effects or {}).get("type") or ""
            if etype in ("heal", "hot"): return 0
            if etype in ("damage", "ranged_damage", "execute_crit"): return 1
            return 2

        candidates = sorted(
            [u for u in units
             if getattr(u, "has_ability", False)
             and u.ability_uses_this_turn < u.ability_max_per_turn
             and not getattr(u, "skip_next_turn", False)
             and not getattr(u, "stunned", 0)],
            key=ability_priority,
        )
        # Mistral : utilise TOUT le CAP disponible (pas de cap à 1)
        for u in candidates:
            if pool.get("CAP", 0) <= 0:
                break
            if _try_ability_smart(state, u, owner, enemy_hq_r, enemy_hq_c):
                _actions += 1

    # ── Désespoir champion ───────────────────────────────────────────────────────
    if owner == "A":
        maybe_trigger_despair_champion_A(state, must_hq_fn)
    else:
        maybe_trigger_despair_champion(state, must_hq_fn)

    # ── 2. Mouvement — scoring positionnel + risk management ─────────────────────
    if pool["MOVE"] > 0:

        # Risk management : QG menacé seulement si ennemi adjacent (dist ≤ 1)
        enemies_near_my_hq = [
            e for e in enemy_units
            if e.hp > 0 and manhattan(e.row, e.col, my_hq_r, my_hq_c) <= 1
        ]
        hq_threatened = len(enemies_near_my_hq) > 0

        # Si QG menacé : assigner le défenseur le plus proche du QG allié
        defender_uid = None
        if hq_threatened:
            alive_allies = [u for u in units if u.hp > 0 and not u.has_moved
                            and not getattr(u, "immovable", False)]
            if alive_allies:
                defender = min(alive_allies,
                               key=lambda u: manhattan(u.row, u.col, my_hq_r, my_hq_c))
                defender_uid = id(defender)
                log(f"MISTRAL_STRAT_{owner} defender={defender.name} reason=hq_threatened")

        for _ in range(20):
            if pool["MOVE"] <= 0:
                break
            moved = False

            for u in list(units):
                if pool["MOVE"] <= 0:
                    break
                if u.hp <= 0 or u.has_moved or getattr(u, "immovable", False):
                    continue

                # Défenseur : retourne protéger le QG allié si ennemi adjacent
                if id(u) == defender_uid:
                    tgt_r, tgt_c = my_hq_r, my_hq_c
                    reason = f"defend_QG threats={len(enemies_near_my_hq)}"

                # Tous les autres : rush QG ennemi (pression constante)
                else:
                    enemy_hq_hp = state.hq_A_hp if enemy == "A" else state.hq_B_hp
                    tgt_r, tgt_c = enemy_hq_r, enemy_hq_c
                    reason = f"target=QG hp={enemy_hq_hp}"

                step = _astar_step(state, u, tgt_r, tgt_c)
                if step is None:
                    continue

                old_r, old_c = u.row, u.col
                u.row, u.col = step
                u.has_moved  = True
                pool["MOVE"] -= 1
                _actions     += 1

                log(f"MISTRAL_STRAT_{owner} move unit={u.name} from=({old_r},{old_c}) to={step} {reason}")
                print(f"[Mistral {owner}] {u.name} ({old_r},{old_c}) → {step}  [{reason}]")

                try:
                    from .ddm_snapshot import log_append as _la
                    _la(state, f"[MOV] {owner} {u.name} ({old_r},{old_c}) → {step}")
                except Exception:
                    pass

                trigger_trap_on_enter(state, u)
                moved = True
                if pool["MOVE"] <= 0:
                    break

            if not moved:
                break

    # ── 3. Attaque ───────────────────────────────────────────────────────────────
    if pool["ATK"] > 0:
        for u in list(units):
            if pool["ATK"] <= 0:
                break
            if u.hp <= 0 or u.has_attacked:
                continue

            enemy_adj   = find_enemy_adjacent(owner, u.row, u.col)
            hq_adjacent = manhattan(u.row, u.col, enemy_hq_r, enemy_hq_c) == 1

            if enemy_adj is None and not hq_adjacent:
                continue

            # Hiérarchie : 1) QG kill shot  2) unité kill shot  3) focus QG
            enemy_hq_hp  = state.hq_A_hp if enemy == "A" else state.hq_B_hp
            hq_kill_shot = hq_adjacent and (u.atk >= enemy_hq_hp)

            if hq_kill_shot:
                target_unit, target_hq = None, True
                reason = "hq_kill_shot"
            elif hq_adjacent and enemy_adj is not None and u.atk >= enemy_adj.hp:
                target_unit = enemy_adj
                target_hq   = False
                reason      = f"unit_kill_shot target={enemy_adj.name}"
            elif hq_adjacent:
                target_unit, target_hq = None, True
                reason = "hq_focus"
            else:
                target_unit, target_hq = enemy_adj, False
                reason = f"atk target={enemy_adj.name} hp={enemy_adj.hp}"

            _bonus = get_passive_atk_bonus(state, u, target_unit) if target_unit else 0

            if target_hq:
                state.damage_hq(enemy, u.atk, tag=f"mistral_{owner}", attacker_pos=(u.row, u.col))
                mem = getattr(state, f"rl_memory_{owner}", {})
                mem["last_dmg_turn"] = state.turn
                setattr(state, f"rl_memory_{owner}", mem)
                print(f"[Mistral {owner}] {u.name} frappe QG {enemy} !")
                log(f"MISTRAL_STRAT_{owner} atk=QG unit={u.name} dmg={u.atk}")
            else:
                apply_damage_to_unit(state, target_unit, u.atk + _bonus,
                                     source_tag=f"mistral_{owner}", attacker=u)
                print(f"[Mistral {owner}] {u.name} → {target_unit.name} "
                      f"({u.atk + _bonus} dmg)  [{reason}]")
                log(f"MISTRAL_STRAT_{owner} {reason} dmg={u.atk + _bonus}")
                try:
                    from .ddm_snapshot import log_append as _la
                    _la(state, f"[ATK] {owner} {u.name} → {target_unit.name} (-{u.atk + _bonus})")
                except Exception:
                    pass

            pool["ATK"] -= 1
            u.has_attacked = True
            _actions      += 1

            if state.hq_A_hp <= 0 and enemy == "A":
                log(f"MISTRAL_GAME_END winner={owner} reason=HQ_A")
                return False
            if state.hq_B_hp <= 0 and enemy == "B":
                log(f"MISTRAL_GAME_END winner={owner} reason=HQ_B")
                return False

    # ── Fin de phase ─────────────────────────────────────────────────────────────
    move_l = pool.get("MOVE", 0)
    atk_l  = pool.get("ATK", 0)
    cap_l  = pool.get("CAP", 0)
    any_left = (move_l + atk_l + cap_l) > 0
    alive_e  = [e for e in UNITS[enemy] if e.hp > 0]

    if _actions == 0 and any_left and alive_e:
        pass_type = "voluntary_pool_left"
    elif any_left:
        pass_type = "spent_pool"
    else:
        pass_type = "no_resource"

    log(f"MISTRAL_END_PHASE_{owner} pass_type={pass_type} actions={_actions} "
        f"move_left={move_l} atk_left={atk_l} cap_left={cap_l}")

    try:
        ctx = getattr(state, "rl_turn_ctx", None)
        if isinstance(ctx, dict) and ctx.get("enabled") and not ctx.get("pass_forced", False):
            ctx["pass_avoidable"]   = (pass_type == "voluntary_pool_left")
            ctx["pass_forced"]      = (pass_type == "no_resource")
            ctx["actions_executed"] = _actions
    except Exception:
        pass

    return True
