"""
ddm_p4_sonnet.py
Phase mobs — Agent Sonnet 4.6

Philosophie : arbre de décision par tour, efficacité ressources maximale.
Ne jamais gaspiller un ATK ou MOVE. Cibler en priorité les menaces sur notre
propre QG (neutralisation défensive) avant l'opportunisme offensif.
CAP sélective : utilisée uniquement si kill-enabling ou si la cible est
la menace la plus critique en portée.

Source : Claude Sonnet 4.6 — Faction 4 / Champion B (Analyste du Code)
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

PREFS_PATH = Path(__file__).parent.parent / "data" / "sonnet_prefs.json"

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


def _winrate(entry: dict) -> float:
    g = entry.get("games", 0)
    return entry.get("wins", 0) / g if g > 0 else 0.5


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
                log(f"SONNET_PREF_SWITCH: new={k} wr={_winrate(v):.2f} old_wr={pref_wr:.2f}")
            break

    save_prefs(prefs)


def get_sonnet_faction_pref(faction_ids: list) -> tuple[int, str]:
    prefs = load_prefs()
    if _random.random() < prefs.get("exploration_rate", 0.15) and len(faction_ids) > 1:
        pref_fid = prefs["preferred"]["faction"]
        choices  = [f for f in faction_ids if f != pref_fid]
        fid      = _random.choice(choices) if choices else pref_fid
        champ    = _random.choice(["A", "B", "C", "D", "E"])
        log(f"SONNET_EXPLORE: faction={fid} champion={champ}")
        return fid, champ

    p = prefs["preferred"]
    log(f"SONNET_SELECT: faction={p['faction']} champion={p['champion']}")
    return p["faction"], p["champion"]


# ─── Scoring des cibles (threat-weighted) ────────────────────────────────────

def score_enemy(unit, attacker_atk: int,
                enemy_hq_r: int, enemy_hq_c: int,
                my_hq_r: int, my_hq_c: int) -> float:
    """
    Score une cible ennemie — philosophie Sonnet :
    Priorité 1 : kill shot (ne pas laisser une menace survivre)
    Priorité 2 : menace sur notre QG (neutralisation défensive)
    Priorité 3 : proximité QG adverse (valeur offensive)
    Priorité 4 : blessé (léger bonus, pas la priorité principale)
    """
    hp_max       = getattr(unit, "hp_max", unit.hp) or unit.hp
    hp_ratio     = unit.hp / max(hp_max, 1)
    kill_shot    = attacker_atk >= unit.hp

    # Menace sur notre QG : ennemi proche = urgence
    def_threat   = 1.0 / (manhattan(unit.row, unit.col, my_hq_r, my_hq_c) + 1)
    # Valeur offensive : ennemi proche de leur QG = bonus
    off_prox     = 1.0 / (manhattan(unit.row, unit.col, enemy_hq_r, enemy_hq_c) + 1)

    score  = 250.0 if kill_shot else 0.0   # kill : priorité absolue
    score += def_threat * 80.0             # neutraliser les menaces sur notre QG
    score += off_prox   * 20.0             # bonus offensif secondaire
    score += (1.0 - hp_ratio) * 30.0      # légère préférence pour les blessés
    return score


# ─── CAP sélective ───────────────────────────────────────────────────────────

_CAP_THREAT_THRESHOLD = 2   # distance max pour considérer une cible "menace critique"


def _should_use_cap(unit, owner: str, enemy_hq_r, enemy_hq_c,
                    my_hq_r, my_hq_c) -> bool:
    """
    Utilise CAP seulement si :
    - L'ability permet un kill shot sur une cible adjacente
    - OU la cible la plus proche est à portée ET menace notre QG (dist ≤ threshold)
    """
    ab_range = getattr(unit, "ability_range", None) or \
               (unit.ability_effects or {}).get("range", 2) or 2
    enemy    = "B" if owner == "A" else "A"
    targets  = [
        e for e in UNITS[enemy]
        if e.hp > 0 and manhattan(e.row, e.col, unit.row, unit.col) <= ab_range
    ]
    if not targets:
        return False

    for t in targets:
        # Kill shot → toujours utile
        if unit.atk >= t.hp:
            return True
        # Menace critique sur notre QG
        if manhattan(t.row, t.col, my_hq_r, my_hq_c) <= _CAP_THREAT_THRESHOLD:
            return True

    return False


def _enemies_in_range(owner: str, row: int, col: int, rng: int):
    enemy = "B" if owner == "A" else "A"
    return [
        e for e in UNITS[enemy]
        if e.hp > 0 and manhattan(e.row, e.col, row, col) <= rng
    ]


# ─── Pathfinding A* ──────────────────────────────────────────────────────────

def _astar_step(state, unit, tgt_r: int, tgt_c: int):
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

def phase_mobs_sonnet(state: GameState, owner: str, must_hq_fn) -> bool:
    """
    Phase unités — Agent Sonnet 4.6.
    Philosophie : threat-weighted targeting, CAP sélective, force_hq.
    """
    rng = getattr(state, "rng", None) or _random

    units       = UNITS[owner]
    enemy       = "B" if owner == "A" else "A"
    pool        = state.pool_A if owner == "A" else state.pool_B
    champ_state = state.champion_A_state if owner == "A" else state.champion_B_state

    print(pool_to_str(pool))

    if not units:
        return True
    if pool["MOVE"] <= 0 and pool["ATK"] <= 0:
        log(f"SONNET_END_PHASE_{owner} reason=no_pool")
        return True

    reset_units_for_new_mob_phase(owner)

    enemy_hq_r, enemy_hq_c = must_hq_fn(enemy)
    my_hq_r,    my_hq_c    = must_hq_fn(owner)
    enemy_units = UNITS[enemy]
    _actions    = 0

    print(f"\n=== Phase unités (Sonnet {owner}) ===")
    log(f"SONNET_START_PHASE_{owner}")

    # ── 1. Abilities (CAP) — sélectif ────────────────────────────────────────
    if pool.get("CAP", 0) > 0:
        candidates = [
            u for u in units
            if getattr(u, "has_ability", False)
            and u.ability_uses_this_turn < u.ability_max_per_turn
            and not getattr(u, "skip_next_turn", False)
            and not getattr(u, "stunned", 0)
            and _should_use_cap(u, owner, enemy_hq_r, enemy_hq_c, my_hq_r, my_hq_c)
        ]
        # Trier par valeur de menace : unité avec la meilleure cible en premier
        used = 0
        for u in candidates:
            if pool.get("CAP", 0) <= 0 or used >= 1:
                break
            ab_range = getattr(u, "ability_range", None) or \
                       (u.ability_effects or {}).get("range", 2) or 2
            targets  = _enemies_in_range(owner, u.row, u.col, ab_range)
            if not targets:
                continue
            best_t = max(targets, key=lambda e: score_enemy(
                e, u.atk, enemy_hq_r, enemy_hq_c, my_hq_r, my_hq_c))
            log(f"SONNET_STRAT_{owner} ability unit={u.name} target={best_t.name} "
                f"threat_dist={manhattan(best_t.row, best_t.col, my_hq_r, my_hq_c)}")
            try:
                ok = use_unit_ability(state, u, owner)
            except Exception:
                ok = False
            if ok:
                used += 1
                _actions += 1

    # ── Désespoir champion ───────────────────────────────────────────────────
    if owner == "A":
        maybe_trigger_despair_champion_A(state, must_hq_fn)
    else:
        maybe_trigger_despair_champion(state, must_hq_fn)

    # ── 2. Mouvement — force_hq ───────────────────────────────────────────────
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

                tgt_r, tgt_c = enemy_hq_r, enemy_hq_c
                enemy_hq_hp  = state.hq_A_hp if enemy == "A" else state.hq_B_hp
                reason       = f"target=QG hp={enemy_hq_hp}"

                step = _astar_step(state, u, tgt_r, tgt_c)
                if step is None:
                    continue

                old_r, old_c = u.row, u.col
                u.row, u.col = step
                u.has_moved  = True
                pool["MOVE"] -= 1
                _actions     += 1

                log(f"SONNET_STRAT_{owner} move unit={u.name} from=({old_r},{old_c}) to={step} {reason}")
                print(f"[Sonnet {owner}] {u.name} ({old_r},{old_c}) → {step}  [{reason}]")

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

    # ── 3. Attaque — threat-weighted ─────────────────────────────────────────
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

            enemy_hq_hp  = state.hq_A_hp if enemy == "A" else state.hq_B_hp
            hq_kill_shot = hq_adjacent and (u.atk >= enemy_hq_hp)

            # Hiérarchie Sonnet :
            # 1) QG kill shot (fin de partie)
            # 2) Unité ennemie si score menace > valeur QG (neutralisation prioritaire)
            # 3) QG par défaut (force_hq)
            if hq_kill_shot:
                target_unit, target_hq = None, True
                reason = "hq_kill_shot"
            elif enemy_adj is not None:
                unit_score = score_enemy(
                    enemy_adj, u.atk, enemy_hq_r, enemy_hq_c, my_hq_r, my_hq_c)
                # Attaque QG si adjacent ET score unité n'est pas un kill critique
                if hq_adjacent and not (u.atk >= enemy_adj.hp):
                    target_unit, target_hq = None, True
                    reason = "hq_focus"
                else:
                    target_unit, target_hq = enemy_adj, False
                    reason = f"threat_target={enemy_adj.name} score={unit_score:.0f}"
            else:
                target_unit, target_hq = None, True
                reason = "hq_focus"

            _bonus = get_passive_atk_bonus(state, u, target_unit) if target_unit else 0

            if target_hq:
                state.damage_hq(enemy, u.atk, tag=f"sonnet_{owner}", attacker_pos=(u.row, u.col))
                mem = getattr(state, f"rl_memory_{owner}", {})
                mem["last_dmg_turn"] = state.turn
                setattr(state, f"rl_memory_{owner}", mem)
                print(f"[Sonnet {owner}] {u.name} frappe QG {enemy} !")
                log(f"SONNET_STRAT_{owner} atk=QG unit={u.name} dmg={u.atk}")
            else:
                apply_damage_to_unit(state, target_unit, u.atk + _bonus,
                                     source_tag=f"sonnet_{owner}", attacker=u)
                print(f"[Sonnet {owner}] {u.name} → {target_unit.name} "
                      f"({u.atk + _bonus} dmg)  [{reason}]")
                log(f"SONNET_STRAT_{owner} {reason} dmg={u.atk + _bonus}")
                try:
                    from .ddm_snapshot import log_append as _la
                    _la(state, f"[ATK] {owner} {u.name} → {target_unit.name} (-{u.atk + _bonus})")
                except Exception:
                    pass

            pool["ATK"] -= 1
            u.has_attacked = True
            _actions      += 1

            if state.hq_A_hp <= 0 and enemy == "A":
                log(f"SONNET_GAME_END winner={owner} reason=HQ_A")
                return False
            if state.hq_B_hp <= 0 and enemy == "B":
                log(f"SONNET_GAME_END winner={owner} reason=HQ_B")
                return False

    # ── Fin de phase ─────────────────────────────────────────────────────────
    move_l   = pool.get("MOVE", 0)
    atk_l    = pool.get("ATK", 0)
    cap_l    = pool.get("CAP", 0)
    any_left = (move_l + atk_l + cap_l) > 0
    alive_e  = [e for e in UNITS[enemy] if e.hp > 0]

    if _actions == 0 and any_left and alive_e:
        pass_type = "voluntary_pool_left"
    elif any_left:
        pass_type = "spent_pool"
    else:
        pass_type = "no_resource"

    log(f"SONNET_END_PHASE_{owner} pass_type={pass_type} actions={_actions} "
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
