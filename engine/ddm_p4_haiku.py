"""
ddm_p4_haiku.py
Phase mobs — Agent Haiku-style

Philosophie : attrition, focus fire sur blessés, abilities intelligentes.
Interface identique à phase_mobs_ai : retourne True/False (False = QG détruit).

Mode select : préférence faction/champion hardcodée + mini bandit RL via haiku_prefs.json
  - 85% du temps : joue la préférence courante
  - 15% : explore une autre faction aléatoire
  - Si une faction explorée dépasse la préférence sur min_games → devient nouvelle préférence
"""
from __future__ import annotations

import json
import random as _random
import heapq as _heapq
from pathlib import Path
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
)
from .ddm_p4_human import (
    maybe_trigger_despair_champion,
    maybe_trigger_despair_champion_A,
)

_CAND_STEPS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

# ─── PROFILE BEHAVIOR (Haiku = Égyptiens / Serapia) ──────────────────────────
# Interview style : patient early game, accept defensive position. When enemy
# HQ falls below ~30%, switch to "spike vengeance" mode (= mécanique active
# Égypte du moteur). Le scoring d'attaque double sa préférence pour QG après
# trigger.
NATURAL_FACTION_ID = 7   # Égypte — la mécanique spike est tied à cette identité
SPIKE_HP_RATIO  = 0.30   # ratio enemy HQ HP / max → trigger spike vengeance
EARLY_GAME_PATIENCE_TURNS = 4  # avant ce tour, pas d'attaque QG si pas kill_shot


def _is_natural_faction(state, owner: str) -> bool:
    """Retourne True si le profil joue sa faction préférée (mécanique distinctive active).
    Sur faction non-naturelle, le profil fallback sur logique base attrition."""
    fac = (state.faction_A if owner == "A" else state.faction_B) or {}
    try:
        return int(fac.get("id", -1)) == NATURAL_FACTION_ID
    except (ValueError, TypeError):
        return False

# ─── Préférences & mini bandit ────────────────────────────────────────────────

PREFS_PATH = Path(__file__).parent.parent / "data" / "haiku_prefs.json"

DEFAULT_PREFS = {
    "preferred"              : {"faction": 3, "champion": "D"},  # Légions / Venina
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
    """Enregistre le résultat d'une partie et met à jour la préférence si nécessaire."""
    prefs = load_prefs()
    key   = f"{faction_id}_{champion}"
    hist  = prefs.setdefault("history", {})
    entry = hist.setdefault(key, {"wins": 0, "losses": 0, "games": 0})
    entry["games"] += 1
    if won:
        entry["wins"] += 1
    else:
        entry["losses"] += 1

    # Vérifier si une faction explorée dépasse la préférence courante
    pref_key  = "{faction}_{champion}".format(**prefs["preferred"])
    pref_wr   = _winrate(hist.get(pref_key, {}))
    min_games = prefs.get("min_games_before_switch", 20)

    for k, v in hist.items():
        if k == pref_key or v["games"] < min_games:
            continue
        if _winrate(v) > pref_wr + 0.10:   # +10% WR pour switcher
            parts = k.split("_", 1)
            if len(parts) == 2:
                prefs["preferred"] = {"faction": int(parts[0]), "champion": parts[1]}
                log(f"HAIKU_PREF_SWITCH: new={k} wr={_winrate(v):.2f} old_wr={pref_wr:.2f}")
            break

    save_prefs(prefs)


def _winrate(entry: dict) -> float:
    g = entry.get("games", 0)
    return entry.get("wins", 0) / g if g > 0 else 0.5


def get_claude_faction_pref(faction_ids: list) -> tuple[int, str]:
    """
    Retourne (faction_id, champion_letter) selon le mode bandit.
    Appelable depuis le loop avant init GameState.
    """
    prefs = load_prefs()
    if _random.random() < prefs.get("exploration_rate", 0.15) and len(faction_ids) > 1:
        # Exploration : faction aléatoire différente de la préférence
        pref_fid = prefs["preferred"]["faction"]
        choices  = [f for f in faction_ids if f != pref_fid]
        fid      = _random.choice(choices) if choices else pref_fid
        champ    = _random.choice(["A", "B", "C", "D", "E"])
        log(f"HAIKU_EXPLORE: faction={fid} champion={champ}")
        return fid, champ

    p = prefs["preferred"]
    log(f"HAIKU_SELECT: faction={p['faction']} champion={p['champion']}")
    return p["faction"], p["champion"]


# ─── Scoring des cibles ───────────────────────────────────────────────────────

def score_enemy(unit, attacker_atk: int, enemy_hq_r: int, enemy_hq_c: int,
                spike_active: bool = False) -> float:
    """
    Score une cible ennemie pour priorisation d'attaque.
    Priorités : kill potentiel > blessé > proche QG ennemi.
    En spike mode (Égypte vengeance), boost les cibles qui menacent notre QG.
    """
    hp_max       = getattr(unit, "hp_max", unit.hp) or unit.hp
    hp_ratio     = unit.hp / max(hp_max, 1)
    kill_shot    = attacker_atk >= unit.hp
    hq_proximity = 1.0 / (manhattan(unit.row, unit.col, enemy_hq_r, enemy_hq_c) + 1)

    score  = 200.0 if kill_shot else 0.0     # kill en 1 coup : priorité absolue
    score += (1.0 - hp_ratio) * 60.0         # plus l'ennemi est bas, plus il est prioritaire
    score += hq_proximity * 25.0             # menace QG = dangereux à laisser vivre
    if spike_active:
        score *= 1.4                          # en spike : tout devient urgent
    return score


# ─── Abilities intelligentes ─────────────────────────────────────────────────

def _try_ability_smart(state, unit, owner: str, enemy_hq_r: int, enemy_hq_c: int) -> bool:
    """
    Tente l'ability de l'unité avec ciblage contextuel selon l'etype.
    Retourne True si l'ability a été utilisée.
    """
    etype    = (unit.ability_effects or {}).get("type") or ""
    ab_range = getattr(unit, "ability_range", None) or (unit.ability_effects or {}).get("range", 2) or 2

    # Heal / HoT → seulement si une alliée est blessée
    if etype in ("heal", "hot", "heal_self"):
        allies = [u for u in UNITS[owner] if u.hp > 0]
        if not allies:
            return False
        most_wounded = min(allies, key=lambda u: u.hp / max(getattr(u, "hp_max", u.hp), 1))
        hp_max = getattr(most_wounded, "hp_max", most_wounded.hp) or most_wounded.hp
        if most_wounded.hp / hp_max > 0.80:
            log(f"HAIKU_STRAT_{owner} ability_skip unit={unit.name} reason=allies_healthy")
            return False
        log(f"HAIKU_STRAT_{owner} ability=heal target={most_wounded.name} hp={most_wounded.hp}")

    # Buff défensif → seulement si menace à portée 3
    elif etype in ("buff_def", "buff_def_and_counter", "armor_break"):
        if not find_enemy_in_range(owner, unit.row, unit.col, rng=3):
            log(f"HAIKU_STRAT_{owner} ability_skip unit={unit.name} reason=no_threat_nearby")
            return False

    # Offensif → seulement si cible valide en portée
    elif etype in (
        "damage", "ranged_damage", "direct_damage", "true_damage",
        "poison", "apply_status", "debuff_atk", "execute_crit", "aoe_damage",
    ):
        targets = _enemies_in_range(owner, unit.row, unit.col, ab_range)
        if not targets:
            log(f"HAIKU_STRAT_{owner} ability_skip unit={unit.name} reason=no_target")
            return False
        # Prioriser la cible la plus proche du kill
        best = max(targets, key=lambda e: score_enemy(e, unit.atk, enemy_hq_r, enemy_hq_c))
        log(f"HAIKU_STRAT_{owner} ability={etype} unit={unit.name} target={best.name} hp={best.hp}")

    try:
        ok = use_unit_ability(state, unit, owner)
    except Exception:
        ok = False
    return ok


def _enemies_in_range(owner: str, row: int, col: int, rng: int):
    """Retourne tous les ennemis dans la portée Manhattan donnée."""
    enemy = "B" if owner == "A" else "A"
    return [
        e for e in UNITS[enemy]
        if e.hp > 0 and manhattan(e.row, e.col, row, col) <= rng
    ]


# ─── Pathfinding (A* réutilisé depuis ddm_p4_ai) ─────────────────────────────

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

    # Remonter le chemin
    if (tgt_r, tgt_c) in _prev or (tgt_r, tgt_c) == (unit.row, unit.col):
        node = (tgt_r, tgt_c)
        while _prev.get(node) != (unit.row, unit.col) and node in _prev:
            node = _prev[node]
        if node != (unit.row, unit.col):
            nr, nc = node
            other, _ = get_unit_at(nr, nc)
            if other is None and is_walkable(nr, nc):
                return node

    # Fallback greedy
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

def phase_mobs_haiku(state: GameState, owner: str, must_hq_fn) -> bool:
    """
    Phase unités — Agent Haiku-style.
    Retourne True pour continuer, False si un QG est détruit.
    """
    rng = getattr(state, "rng", None) or _random

    units     = UNITS[owner]
    enemy     = "B" if owner == "A" else "A"
    pool      = state.pool_A if owner == "A" else state.pool_B
    champ_state = state.champion_A_state if owner == "A" else state.champion_B_state

    print(pool_to_str(pool))

    if not units:
        return True
    if pool["MOVE"] <= 0 and pool["ATK"] <= 0:
        log(f"HAIKU_END_PHASE_{owner} reason=no_pool")
        return True

    reset_units_for_new_mob_phase(owner)

    enemy_hq_r, enemy_hq_c = must_hq_fn(enemy)
    my_hq_r,    my_hq_c    = must_hq_fn(owner)
    enemy_units = UNITS[enemy]
    _actions    = 0

    print(f"\n=== Phase unités (Claude {owner}) ===")
    log(f"HAIKU_START_PHASE_{owner}")

    # ── 1. Abilities (CAP) ──────────────────────────────────────────────────
    if pool.get("CAP", 0) > 0:
        # Trier : d'abord les heal (urgence), puis les offensifs
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
        used = 0
        for u in candidates:
            if pool.get("CAP", 0) <= 0 or used >= 1:
                break
            if _try_ability_smart(state, u, owner, enemy_hq_r, enemy_hq_c):
                used += 1
                _actions += 1

    # ── Désespoir champion ───────────────────────────────────────────────────
    if owner == "A":
        maybe_trigger_despair_champion_A(state, must_hq_fn)
    else:
        maybe_trigger_despair_champion(state, must_hq_fn)

    # ── 2. Mouvement ─────────────────────────────────────────────────────────
    if pool["MOVE"] > 0:
        for _ in range(20):
            if pool["MOVE"] <= 0:
                break
            moved = False

            for u in list(units):
                if pool["MOVE"] <= 0:
                    break
                if u.hp <= 0 or u.has_moved or getattr(u, "immovable", False):
                    continue

                # ── Combo Égypte : Statue du Disque Solaire ──────────────────
                # Passif Ancrage : si Statue ne bouge pas → +1 DEF.
                # On la skip sauf si elle doit absolument avancer (QG exposé).
                _STATUE = "Statue du Disque Solaire"
                _CHAMP  = "Champion du Disque Solaire"
                if u.name == _STATUE:
                    alive_enemies_statue = [e for e in enemy_units if e.hp > 0]
                    enemy_hq_hp_statue   = state.hq_A_hp if enemy == "A" else state.hq_B_hp
                    hq_max_hp_statue     = state.hq_A_hp_max if enemy == "A" else state.hq_B_hp_max
                    hq_ratio_statue      = enemy_hq_hp_statue / max(hq_max_hp_statue, 1)
                    if alive_enemies_statue and hq_ratio_statue > 0.25:
                        # Ancrage : rester immobile, +1 DEF passif
                        log(f"HAIKU_STRAT_{owner} move_skip unit={u.name} reason=ancrage_passif")
                        print(f"[Claude {owner}] {u.name} reste immobile [ancrage_passif]")
                        u.has_moved = True  # consomme le droit de mouvement sans bouger
                        continue

                # ── Combo Égypte : Champion du Disque Solaire ────────────────
                # Aura du Disque : Champion gagne +1 ATK/DEF si adjacent/range1 de la Statue.
                # Priorité : rester proche de la Statue si elle est en jeu, sinon QG.
                _statue_unit = None
                if u.name == _CHAMP:
                    _statue_unit = next(
                        (a for a in units if a.name == _STATUE and a.hp > 0), None
                    )

                # ── Cible de mouvement ────────────────────────────────────────
                alive_enemies = [e for e in enemy_units if e.hp > 0]
                enemy_hq_hp   = state.hq_A_hp if enemy == "A" else state.hq_B_hp
                hq_max_hp     = state.hq_A_hp_max if enemy == "A" else state.hq_B_hp_max
                hq_ratio      = enemy_hq_hp / max(hq_max_hp, 1)

                # Priorité QG : toujours (rush constant), sauf si Champion doit rejoindre Statue
                force_hq = True

                if _statue_unit is not None:
                    # Champion se positionne adjacent/range1 de la Statue si pas déjà dans l'aura
                    dist_to_statue = manhattan(u.row, u.col, _statue_unit.row, _statue_unit.col)
                    if dist_to_statue > 1:
                        tgt_r, tgt_c = _statue_unit.row, _statue_unit.col
                        reason = f"target=Statue aura dist={dist_to_statue}"
                        force_hq = False

                if force_hq:
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

                log(f"HAIKU_STRAT_{owner} move unit={u.name} from=({old_r},{old_c}) to={step} {reason}")
                print(f"[Claude {owner}] {u.name} ({old_r},{old_c}) → {step}  [{reason}]")

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

    # ── 3. Attaque ───────────────────────────────────────────────────────────
    # Spike trigger : Égypte vengeance quand QG ennemi < 30% HP.
    # Gate par faction naturelle : sur non-Égypte, fallback attrition pure.
    natural = _is_natural_faction(state, owner)
    enemy_hq_hp_now = state.hq_A_hp if enemy == "A" else state.hq_B_hp
    enemy_hq_max    = getattr(state, f"hq_{enemy}_hp_max", 35) or 35
    spike_active    = natural and (enemy_hq_hp_now / max(enemy_hq_max, 1)) < SPIKE_HP_RATIO
    is_early_game   = natural and state.turn < EARLY_GAME_PATIENCE_TURNS

    if spike_active:
        log(f"HAIKU_STRAT_{owner} spike_active enemy_hq_ratio={enemy_hq_hp_now/enemy_hq_max:.2f}")

    if pool["ATK"] > 0:
        for u in list(units):
            if pool["ATK"] <= 0:
                break
            if u.hp <= 0 or u.has_attacked:
                continue

            enemy_adj     = find_enemy_adjacent(owner, u.row, u.col)
            hq_adjacent   = manhattan(u.row, u.col, enemy_hq_r, enemy_hq_c) == 1

            if enemy_adj is None and not hq_adjacent:
                continue

            # Choix : QG ou unité adjacente ?
            # Hiérarchie pré-spike : 1) QG kill shot  2) unité (attrition)  3) skip QG si patient
            # Hiérarchie post-spike : 1) QG kill shot  2) QG focus  3) unité kill shot
            enemy_hq_hp  = state.hq_A_hp if enemy == "A" else state.hq_B_hp
            hq_kill_shot = hq_adjacent and (u.atk >= enemy_hq_hp)

            if hq_kill_shot:
                target_unit, target_hq = None, True
                reason = "hq_kill_shot"
            elif spike_active and hq_adjacent:
                # Spike vengeance : push QG hard
                target_unit, target_hq = None, True
                reason = "hq_focus_spike"
            elif is_early_game and hq_adjacent and enemy_adj is not None:
                # Early game patient : préfère taper unité que QG sans kill shot
                target_unit, target_hq = enemy_adj, False
                reason = f"early_unit_focus target={enemy_adj.name}"
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
                state.damage_hq(enemy, u.atk, tag=f"claude_{owner}", attacker_pos=(u.row, u.col))
                mem = getattr(state, f"rl_memory_{owner}", {})
                mem["last_dmg_turn"] = state.turn
                setattr(state, f"rl_memory_{owner}", mem)
                print(f"[Claude {owner}] {u.name} frappe QG {enemy} !")
                log(f"HAIKU_STRAT_{owner} atk=QG unit={u.name} dmg={u.atk}")
            else:
                apply_damage_to_unit(state, target_unit, u.atk + _bonus,
                                     source_tag=f"claude_{owner}", attacker=u)
                print(f"[Claude {owner}] {u.name} → {target_unit.name} "
                      f"({u.atk + _bonus} dmg)  [{reason}]")
                log(f"HAIKU_STRAT_{owner} {reason} dmg={u.atk + _bonus}")
                try:
                    from .ddm_snapshot import log_append as _la
                    _la(state, f"[ATK] {owner} {u.name} → {target_unit.name} (-{u.atk + _bonus})")
                except Exception:
                    pass

            pool["ATK"] -= 1
            u.has_attacked = True
            _actions      += 1

            # Vérif fin de partie
            if state.hq_A_hp <= 0 and enemy == "A":
                log(f"HAIKU_GAME_END winner={owner} reason=HQ_A")
                return False
            if state.hq_B_hp <= 0 and enemy == "B":
                log(f"HAIKU_GAME_END winner={owner} reason=HQ_B")
                return False

    # ── Fin de phase ─────────────────────────────────────────────────────────
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

    log(f"HAIKU_END_PHASE_{owner} pass_type={pass_type} actions={_actions} "
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
