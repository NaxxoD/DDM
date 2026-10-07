

from .ddm_p1_core import *
from .ddm_p2_board_dice import *
import os as _os
import re


def _is_ai_vs_ai() -> bool:
    """
    Vérifie si on est en mode IA vs IA.
    Priorité : env DDM_AUTORUN=1 > state.run_mode > ddm_p1_core.AI_VS_AI_MODE (global copié).
    Le global importé via import* est figé à False — ne pas l'utiliser directement.
    """
    if _os.environ.get("DDM_AUTORUN", "0") == "1":
        return True
    try:
        from . import ddm_p1_core as _P1
        return bool(getattr(_P1, "AI_VS_AI_MODE", False))
    except Exception:
        return False

# --- stats helpers (optional, non-bloquant) ---

def _ddm_get_stats(state):
    return getattr(state, "stats", None)


def _ddm_mode(state):
    return getattr(state, "run_mode", None) or "console"


def _ddm_infer_side(unit):
    # Most code uses owner/team as 'A'/'B' (or 1/2). Fallback: scan UNITS.
    owner = getattr(unit, "owner", None)
    if owner in ("A", "B"):
        return owner
    if owner in (1, "1"):
        return "A"
    if owner in (2, "2"):
        return "B"
    team = getattr(unit, "team", None)
    if team in ("A", "B"):
        return team
    # Fallback: scan global UNITS lists (small, OK)
    try:
        if "UNITS" in globals():
            if unit in UNITS.get("A", []):
                return "A"
            if unit in UNITS.get("B", []):
                return "B"
    except Exception:
        pass
    return None


def _ddm_faction_name(state, side):
    try:
        if side == "A":
            return (getattr(state, "faction_A", None) or getattr(state, "faction_A_info", None) or {}).get("name") or "?"
        if side == "B":
            return (getattr(state, "faction_B", None) or getattr(state, "faction_B_info", None) or {}).get("name") or "?"
    except Exception:
        pass
    return "?"


def _ddm_unit_meta(state, unit):
    side = _ddm_infer_side(unit)
    faction = getattr(unit, "faction_name", None) or _ddm_faction_name(state, side)
    level = getattr(unit, "level", None)
    utype = "champ" if getattr(unit, "is_champion", False) else "mob"
    return {"side": side, "faction": faction, "level": level, "type": utype}


#  INVOCATION
# ----------------------------------------------------------------------


def _ddm_get_faction_name(state, player_char: str | None = None) -> str:
    """
    Best-effort: récupère le nom de faction associé à A/B depuis l'état.
    Ne casse jamais le jeu : si on ne trouve pas, on renvoie 'A'/'B' ou '?'.

    ⚠️ Important : pour des stats utiles (winrate par faction), il faut que l'état expose
    un nom de faction (dict avec 'nom', ou attribut factionA/factionB, etc.).
    """
    candidates: list[object] = []

    # 1) Attributs explicites par side
    if player_char in ("A", "B"):
        side = player_char
        for a, b in (
            ("faction_name_A", "faction_name_B"),
            ("factionA_name", "factionB_name"),
            ("faction_A_name", "faction_B_name"),
            ("factionA", "factionB"),
            ("faction_A", "faction_B"),
            ("factionA_data", "factionB_data"),
            ("faction_data_A", "faction_data_B"),
            ("factionA_id", "factionB_id"),
            ("faction_id_A", "faction_id_B"),
            ("factionA_idx", "factionB_idx"),
        ):
            attr = a if side == "A" else b
            candidates.append(getattr(state, attr, None))
        candidates.append(getattr(state, f"faction_name_{side}", None))

    # 2) fallback génériques
    candidates.append(getattr(state, "faction_name", None))
    candidates.append(getattr(state, "faction", None))

    # 3) Essaye de résoudre un id -> nom via une table si dispo
    def _resolve_id(fid: int) -> str | None:
        for cont_attr in ("factions", "factions_data", "faction_defs", "FACTIONS", "FACTIONS_DATA"):
            cont = getattr(state, cont_attr, None) or globals().get(cont_attr)
            if not cont:
                continue
            # list of dicts
            if isinstance(cont, list) and 0 <= fid < len(cont):
                item = cont[fid]
                if isinstance(item, dict):
                    return item.get("nom") or item.get("name")
            # dict mapping
            if isinstance(cont, dict):
                # keys might be ids or names
                if fid in cont and isinstance(cont[fid], dict):
                    return cont[fid].get("nom") or cont[fid].get("name")
        return None

    for v in candidates:
        if v is None or v == "":
            continue
        if isinstance(v, str):
            return v
        if isinstance(v, int):
            resolved = _resolve_id(v)
            if resolved:
                return resolved
            # if not resolvable, keep scanning
            continue
        if isinstance(v, dict):
            for k in ("nom", "name", "faction", "title"):
                if v.get(k):
                    return str(v.get(k))
        for k in ("nom", "name", "title"):
            if hasattr(v, k):
                vv = getattr(v, k)
                if vv:
                    return str(vv)

    return player_char or "?"


def compute_invocation(stars):
    """
    stars = liste de (die, face)
    Retourne (niveau d'invoc, nom_de_règle, infos_debug)
    Règles :
        - < 2 étoiles : pas d'invocation
        - 3+ étoiles avec au moins un L5 : rituel noir -> niveau 5
        - 3+ étoiles sans noir : crit_triple -> max(1, min(5, max_level))
        - 2 étoiles : règle des points (table ci-dessous)
    """
    n = len(stars)
    if n < 2:
        return None, None, {"levels": [], "points": 0, "star_count": n}

    levels = sorted(d.level for (d, _f) in stars)
    total = sum(levels)
    has_black = any(d.level == 5 for (d, _f) in stars)

    # 1) Rituel noir : 3+ étoiles dont au moins un L5 -> invoc 5
    if has_black and n >= 3:
        return 5, "rituel_noir", {
            "levels": levels,
            "points": total,
            "star_count": n,
        }

    # 2) 3+ étoiles sans noir : critique triple
    if n >= 3:
        max_level = max(levels)
        # ex : max=3 -> invoc 2, max=4 -> invoc 3
        crit_level = max(1, min(5, max_level)) 
        return crit_level, "crit_triple", {
            "levels": levels,
            "points": total,
            "star_count": n,
        }

    # 3) 2 étoiles : règle des points
    # points possibles : de 2 (1+1) à 10 (5+5)
    points = total

    # Table simple et cohérente :
    #  2–3  -> niveau 1
    #  4–5  -> niveau 2
    #  6–7  -> niveau 3
    #  8–9  -> niveau 4
    #  10   -> niveau 5
    if points <= 3:
        invoc_level = 1
    elif points <= 5:
        invoc_level = 2
    elif points <= 7:
        invoc_level = 3
    elif points <= 9:
        invoc_level = 4
    else:
        invoc_level = 5

    return invoc_level, "points", {
        "levels": levels,
        "points": points,
        "star_count": n,
    }

# ----------------------------------------------------------------------
#  SPAWN UNITÉS
# ----------------------------------------------------------------------

def spawn_unit_for_player(state: GameState, player_char: str, level: int, new_cells):
    """
    new_cells : liste de (r,c) de la shape posée.
    Le mob pop au « centre » de la face : case de distance médiane au QG ennemi.

    Mode 11 (et par défaut) : DRAFT PANEL (plus tactique)
        - Lv1–Lv4 : 3 choix
        - Lv5 : 2 choix
        - anti-doublon : si la faction a >=3 mobs différents à ce niveau -> max 1 copie par type
        sinon -> max 2 copies (cas Démons/Égypte L1 pauvres)
        - synergie Égypte (bundle 70%) : Champion du Disque Solaire (Lv3) ↔ Statue du Disque Solaire (Lv4)
    """
    if not new_cells:
        return

    enemy = 'B' if player_char == 'A' else 'A'
    er, ec = HQ_POS[enemy]

    # distance de chaque case au QG ennemi
    cells_sorted = sorted(new_cells, key=lambda rc: manhattan(rc[0], rc[1], er, ec))
    r, c = cells_sorted[len(cells_sorted) // 2]

    if player_char == 'A':
        units_by_level = state.units_by_level_A
    else:
        units_by_level = state.units_by_level_B

    faction_name = _ddm_get_faction_name(state, player_char)

    # defaults ability
    ability_id = None
    ability_name = None
    ability_cost = {}
    ability_range = None
    ability_target_type = "self"
    ability_effects = {}
    ability_max_per_turn = 1

    candidates_all = units_by_level.get(level) or units_by_level.get(1) or []
    roster = getattr(state, f"draft_roster_{player_char}", None)
    if roster:
        from collections import Counter as _Counter
        roster_counts = _Counter(roster)
        weighted = []
        for m in candidates_all:
            n = roster_counts.get(m.get("nom"), 0)
            if n > 0:
                weighted.extend([m] * n)
        if not weighted:
            return  # niveau non drafté → invocation échouée, pas de spawn
        candidates_all = weighted
    if not candidates_all:
        hp, atk, defense, name = 10, 3, 0, "Unité"
        move = 2
        u = Unit(
            player_char, r, c,
            hp=hp, atk=atk, move=move, name=name, defense=defense,
            ability_id=ability_id,
            ability_name=ability_name,
            ability_cost=ability_cost,
            ability_range=ability_range,
            ability_target_type=ability_target_type,
            ability_effects=ability_effects,
            ability_max_per_turn=ability_max_per_turn,
            level=level,
        )
        UNITS[player_char].append(u)
        print(f"  -> Unité spawn pour {player_char} : {name} (Lv{level}) en (r={r}, c={c}) [HP={hp}, ATK={atk}]")
        return

    # --- anti-doublon soft ---
    existing_counts = {}
    for u0 in UNITS[player_char]:
        existing_counts[u0.name] = existing_counts.get(u0.name, 0) + 1

    uniq_names = list({m.get("nom", "Unité") for m in candidates_all})
    max_copies = 1 if len(uniq_names) >= 3 else 2

    filtered = []
    for mon in candidates_all:
        mon_name = mon.get("nom", "Unité")
        if existing_counts.get(mon_name, 0) < max_copies:
            filtered.append(mon)
    candidates_pool = filtered if filtered else candidates_all

    # --- panel draft ---
    panel_k = 2 if level >= 5 else 3
    panel_k = min(panel_k, len(candidates_pool))

    # synergie Égypte (bundle)
    egypt = ("egypte" in faction_name.lower()) or ("égypte" in faction_name.lower())
    CHAMP = "Champion du Disque Solaire"
    STATUE = "Statue du Disque Solaire"
    has_champ = any(u1.name == CHAMP for u1 in UNITS[player_char])
    has_statue = any(u1.name == STATUE for u1 in UNITS[player_char])

    def find_by_name(pool, nm):
        for m in pool:
            if m.get("nom") == nm:
                return m
        return None

    panel = []

    import random as _rng

    if egypt and panel_k > 0:
        if level == 4 and has_champ:
            partner = find_by_name(candidates_pool, STATUE)
            if partner and _rng.random() < 0.70:
                panel.append(partner)
        elif level == 3 and has_statue:
            partner = find_by_name(candidates_pool, CHAMP)
            if partner and _rng.random() < 0.70:
                panel.append(partner)

    remaining = [m for m in candidates_pool if m not in panel]

    def w(m):
        nm = m.get("nom", "Unité")
        stats = m.get("stats", {}) or {}
        base = int(stats.get("HP", 0)) + int(stats.get("ATK", 0)) + int(stats.get("DEF", 0))
        base += 8 if existing_counts.get(nm, 0) == 0 else 0
        role = (m.get("role") or "").lower()
        if "combo" in role:
            base += 2
        return base

    remaining.sort(key=w, reverse=True)
    for m in remaining:
        if len(panel) >= panel_k:
            break
        panel.append(m)

    if len(panel) < panel_k:
        for m in candidates_pool:
            if len(panel) >= panel_k:
                break
            if m not in panel:
                panel.append(m)

    # --- choix : humain ou IA ---
    run_mode = getattr(state, "run_mode", "") or ""
    is_human = False
    if _is_ai_vs_ai():
        is_human = False  # autorun / iaia : toujours IA
    elif run_mode == "hvh":
        is_human = True
    elif run_mode == "hvia":
        is_human = (player_char == "A")
    elif run_mode == "console":
        is_human = True

    chosen = None
    if is_human:
        print(f"\n[DRAFT Lv{level}] Choisis l'unité à invoquer ({faction_name}) :")
        for i, m in enumerate(panel):
            nm = m.get("nom", "Unité")
            role = m.get("role", "")
            st = m.get("stats", {}) or {}
            hp0, atk0, df0 = st.get("HP", "?"), st.get("ATK", "?"), st.get("DEF", "?")
            extra = f" — {role}" if role else ""
            print(f"  [{i}] {nm} (HP={hp0} ATK={atk0} DEF={df0}){extra}")
        raw = input(f"Choix (0-{len(panel)-1}, Enter=0) : ").strip()
        try:
            idx = int(raw) if raw else 0
        except Exception:
            idx = 0
        if not (0 <= idx < len(panel)):
            idx = 0
        chosen = panel[idx]
    else:
        def score(m):
            nm = m.get("nom", "Unité")
            s = w(m)
            if egypt:
                if level == 4 and nm == STATUE and not has_statue:
                    s += 10
                if level == 3 and nm == CHAMP and not has_champ:
                    s += 10
            return s
        chosen = max(panel, key=score)

    monster = chosen or candidates_pool[0]

    st = monster.get("stats", {}) or {}
    hp = int(st.get("HP", 10))
    atk = int(st.get("ATK", 3))
    defense = int(st.get("DEF", 0))
    name = monster.get("nom", "Unité")

    raw_text = monster.get("action_speciale", "") or monster.get("capacite", "") or ""
    if raw_text:
        try:
            parsed = parse_ability_from_action_speciale(raw_text)
        except Exception:
            parsed = None
        if parsed:
            ability_id = parsed.get("id")
            ability_name = parsed.get("name") or monster.get("nom", "Ability")
            ability_cost = parsed.get("cost", {}) or {}
            ability_range = parsed.get("range")
            ability_target_type = parsed.get("target") or parsed.get("target_type") or "self"
            ability_effects = parsed.get("effects", {}) or {}
            if raw_text:
                ability_effects.setdefault("raw_text", raw_text)
            ability_max_per_turn = parsed.get("max_per_turn", 1)
            # --- Pont action_id -> etype ---
            # Le JSON define action_id sur le mob. On l'injecte dans ability_effects["type"]
            # pour que use_unit_ability puisse dispatcher correctement.
            action_id = monster.get("action_id")
            if action_id and not ability_effects.get("type"):
                ability_effects["type"] = action_id
            # Injecte aussi action_params dans ability_effects pour les nouveaux types
            action_params = monster.get("action_params") or {}
            if action_params:
                for k, v in action_params.items():
                    ability_effects.setdefault(k, v)

    move = 2  # pour l'instant, fixe

    u = Unit(
        player_char, r, c,
        hp=hp, atk=atk, move=move, name=name, defense=defense,
        ability_id=ability_id,
        ability_name=ability_name,
        ability_cost=ability_cost,
        ability_range=ability_range,
        ability_target_type=ability_target_type,
        ability_effects=ability_effects,
        ability_max_per_turn=ability_max_per_turn,
        level=level,
    )
    u.uid = alloc_uid(player_char)   # uid canonique pour tracking buff/passif
    u.hp_max = hp                    # HP max pour passifs HP-based (Briseur de Lune)

    stt = _ddm_get_stats(state)
    if stt:
        try:
            stt.note_unit_spawn(_ddm_mode(state), name, faction_name, level, unit_type="mob")
        except Exception:
            pass

    UNITS[player_char].append(u)

    try:
        log(f"DRAFT_PICK side={player_char} level={level} name={name} faction={faction_name}")
    except Exception:
        pass

    print(f"  -> Unité spawn pour {player_char} : {name} (Lv{level}) en (r={r}, c={c}) [HP={hp}, ATK={atk}]")


# ----------------------------------------------------------------------
#  PLACEMENT INVOC (JOUEUR & IA)
# ----------------------------------------------------------------------

def attempt_place_invocation(board, player_id, level, state: GameState):
    """
    Redirige vers la version humaine ou IA selon player_id
    et le mode AI_VS_AI_MODE.
    """
    if level is None or level < 1:
        return False
    level = min(level, 5)

    # Joueur humain uniquement si player_id == 1 et qu'on n'est PAS en IA vs IA
    is_human = (player_id == 1 and not _is_ai_vs_ai())

    if is_human:
        player_tiles = {P1_QG, P1_TILE}
        tile_char = P1_TILE
        return attempt_place_human(board, state, level, player_tiles, tile_char, 'A')
    else:
        if player_id == 1:
            # IA qui joue le camp A
            player_tiles = {P1_QG, P1_TILE}
            tile_char = P1_TILE
            owner_char = 'A'
        else:
            # IA camp B (comme avant)
            player_tiles = {P2_QG, P2_TILE}
            tile_char = P2_TILE
            owner_char = 'B'

        return attempt_place_ai(board, state, level, player_tiles, tile_char, owner_char)



def attempt_place_human(board, state: GameState, level, player_tiles, tile_char, player_char):
    anchors = find_anchors(board, player_tiles)
    if not anchors:
        print("  [INVOC] Aucun endroit pour poser la shape (pas d'ancre).")
        return False

    print("\nAncres possibles (index : coord) :")
    for i, (r, c) in enumerate(anchors):
        print(f"  [{i}] (r={r}, c={c})")
    print_board_with_anchors(board, anchors)

    ch = input("Choix d'ancre (Enter=0) : ").strip()
    try:
        idx_anchor = int(ch) if ch else 0
    except ValueError:
        idx_anchor = 0
    if not (0 <= idx_anchor < len(anchors)):
        idx_anchor = 0
    ar, ac = anchors[idx_anchor]
    print(f"  -> Ancre choisie : (r={ar}, c={ac})")

    shapes = SHAPES_BY_LEVEL[level]

    while True:
        print(f"\nShapes disponibles pour le niveau {level} :")
        for i, shape in enumerate(shapes):
            print(f"  [{i}]")
            preview_shape(shape)

        ch = input("Choix de shape (Enter=0) : ").strip()
        try:
            idx_shape = int(ch) if ch else 0
        except ValueError:
            idx_shape = 0
        if not (0 <= idx_shape < len(shapes)):
            idx_shape = 0

        while True:
            choix_rot = input("Rotation (0/1/2/3 ; R=autre shape ; X=annuler) : ").strip().lower()
            if choix_rot == 'x':
                print("  Invocation annulée.")
                return False
            if choix_rot == 'r':
                break

            try:
                rot = int(choix_rot) if choix_rot else 0
            except ValueError:
                rot = 0
            rot %= 4

            local = rotate_pattern(shapes[idx_shape], rot)
            cells = translate_pattern(local, ar, ac)

            if not can_place_shape(board, cells, player_tiles):
                print("  [INVOC] Cette rotation ne passe pas ici.")
                continue

            print("\nAperçu de la pose :")
            print_board_with_ghost(board, cells)

            conf = input("Valider ? (O=oui, N=rotation, R=autre shape, X=annuler) : ").strip().lower()
            if conf in ('o', ''):
                placed_cells = place_shape(board, cells, tile_char)
                print(f"  [INVOC] Shape Lv{level} posée (rot={rot * 90}°).")
                spawn_unit_for_player(state, player_char, level, placed_cells)
                return True
            elif conf == 'n':
                continue
            elif conf == 'r':
                break
            elif conf == 'x':
                print("  Invocation annulée.")
                return False


def attempt_place_ai(board, state: GameState, level, player_tiles, tile_char, player_char):
    """
    IA : place une shape de niveau `level` en utilisant un scoring
    offensif/défensif + blocage de couloirs, pondéré par ai_profile.
    """
    anchors = find_anchors(board, player_tiles)
    if not anchors:
        print("  [INVOC] Pas d'ancre pour l'IA.")
        return False

    # --- Détection d'invasion du terrain pour basculer OFFENSIF / DÉFENSIF ---

    if player_char == 'B':
        own_rows = range(0, HEIGHT // 2)
        enemy_tile = P1_TILE
        profile = state.ai_profile_B
    else:
        own_rows = range(HEIGHT // 2, HEIGHT)
        enemy_tile = P2_TILE
        profile = state.ai_profile_A

    invasion_count = 0
    for r in own_rows:
        for c in range(WIDTH):
            if board[r][c] == enemy_tile:
                invasion_count += 1

    # Phase de game (early/mid/late/overtime) selon objectif de tours
    phase = get_game_phase(state, profile)

    INVASION_THRESHOLD = 10
    mode = "defensive" if invasion_count >= INVASION_THRESHOLD else "offensive"

    aggro_weight = profile.get("aggro_weight", 1.0)
    block_weight = profile.get("block_weight", 1.0)

    if mode == "defensive":
        aggro_weight *= 0.5
        block_weight *= 1.5
    else:
        aggro_weight *= 1.2
        block_weight *= 0.8

    # Ajustement supplémentaire selon la phase de game
    if phase == "early":
        # bétonner un peu plus, limiter le rush trop tôt
        aggro_weight *= 0.8
        block_weight *= 1.3
    elif phase == "mid":
        # équilibre
        aggro_weight *= 1.0
        block_weight *= 1.0
    elif phase == "late":
        # fenêtre de victoire : pousser plus fort
        aggro_weight *= 1.4
        block_weight *= 0.8
    else:  # "overtime"
        # on cherche clairement à finir
        aggro_weight *= 1.6
        block_weight *= 0.6

    # Log IA mode (stdout) + infos directionnelles (sideflip-safe)
    print(f"  [IA] Mode d'invocation = {mode.upper()} (invasion={invasion_count})")
    enemy = 'B' if player_char == 'A' else 'A'
    # Direction 'avant' : +1 si le QG ennemi est en dessous, -1 si au-dessus
    try:
        my_hq_r, _ = HQ_POS[player_char]
        enemy_hq_r, _ = HQ_POS[enemy]
        forward = 1 if enemy_hq_r > my_hq_r else -1
    except Exception:
        forward = -1 if player_char == 'A' else 1

    best_score = None
    best_cells = None
    best_info = None  # (anchor_r, anchor_c, rot, shape_idx)

    for ar, ac in anchors:
        for idx_shape, shape in enumerate(SHAPES_BY_LEVEL[level]):
            for rot in range(4):
                local = rotate_pattern(shape, rot)
                cells = translate_pattern(local, ar, ac)
                if not can_place_shape(board, cells, player_tiles):
                    continue

                rows = [r for (r, c) in cells]

                # Progression vers le QG ennemi (sideflip-safe)
                progress_score = max(r * forward for r in rows)

                # Blocage : nombre de cases adjacentes aux chemins ennemis
                block_score = 0
                for (r, c) in cells:
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < HEIGHT and 0 <= nc < WIDTH:
                            if board[nr][nc] == enemy_tile:
                                block_score += 1

                score = progress_score * aggro_weight + block_score * block_weight

                if best_score is None or score > best_score:
                    best_score = score
                    best_cells = cells
                    best_info = (ar, ac, rot, idx_shape)

    if best_cells is None:
        print("  [INVOC] IA : aucune shape ne rentre.")
        return False

    placed_cells = place_shape(board, best_cells, tile_char)
    ar, ac, rot, idx_shape = best_info
    # Tags machine-readables dans le .log (RunLab / policies)
    log(f"SHAPE_{player_char} level={level} shape={idx_shape} rot={rot} anchor=({ar},{ac})")
    log(f"SHAPE player={player_char} level={level} shape={idx_shape} rot={rot} anchor=({ar},{ac})")
    print(f"  [INVOC] IA place Lv{level} depuis {(ar, ac)} (rot={rot * 90}°).")
    spawn_unit_for_player(state, player_char, level, placed_cells)
    return True

# ----------------------------------------------------------------------
#  ABILITIES / COÛTS
# ----------------------------------------------------------------------

def can_pay_cost(pool, cost):
    for k, v in cost.items():
        if v > 0 and pool.get(k, 0) < v:
            return False
    return True


def pay_cost(pool, cost):
    for k, v in cost.items():
        if v > 0:
            pool[k] = pool.get(k, 0) - v


def get_pool_for_owner(state: GameState, owner_char: str):
    return state.pool_A if owner_char == 'A' else state.pool_B


def manhattan(a_r, a_c, b_r, b_c):
    return abs(a_r - b_r) + abs(a_c - b_c)


def get_unit_at(r, c, owner=None):
    """
    Retourne (unit, owner_char) si trouvé, sinon (None, None).
    Si owner est précisé, ne regarde que ce camp.
    """
    owners = [owner] if owner in ('A', 'B') else ['A', 'B']
    for side in owners:
        for u in UNITS[side]:
            if u.row == r and u.col == c:
                return u, side
    return None, None

def ensure_traps(state: GameState):
    if not hasattr(state, "traps") or state.traps is None:
        state.traps = []

def trap_at(state: GameState, r: int, c: int):
    ensure_traps(state)
    for t in state.traps:
        if t["r"] == r and t["c"] == c:
            return t
    return None

def is_walkable_ab(board, r, c):
    return board[r][c] in (P1_TILE, P2_TILE)  # 'a'/'b'

def place_trap(state: GameState, owner: str, r: int, c: int, damage: int = 3, duration: int = 2):
    ensure_traps(state)
    if trap_at(state, r, c) is not None:
        return False
    state.traps.append({
        "owner": owner,
        "r": int(r),
        "c": int(c),
        "damage": int(damage),
        "duration": int(duration),
        "trigger": "on_enter",
        "consume": True,
    })
    log(f"TRAP_PLACE owner={owner} pos=({r},{c}) dmg={damage} dur={duration}")
    return True

def trigger_trap_on_enter(state: GameState, unit: Unit):
    # Passif Lancier Écaille-Feu : si ennemi entre adjacent, pose flag
    try:
        friend_char = "B" if unit.owner == "A" else "A"
        for ally in UNITS[friend_char]:
            if ally.hp > 0 and manhattan(ally.row, ally.col, unit.row, unit.col) == 1:
                raw_t = str((getattr(ally, "ability_effects", {}) or {}).get("raw_text", "")).lower()
                if "interception" in raw_t:
                    ally._interception_bonus = getattr(ally, "_interception_bonus", 0) + 2
    except Exception:
        pass
    ensure_traps(state)
    t = trap_at(state, unit.row, unit.col)
    if not t:
        return False
    if t["owner"] == unit.owner:
        return False  # ignore alliés

    dmg = int(t.get("damage", 2))
    print(f"  [TRAP] {unit.name} déclenche un piège : -{dmg} HP !")
    apply_damage_to_unit(state, unit, dmg, source_tag="trap", ignore_def=True)

    if t.get("consume", True):
        try:
            state.traps.remove(t)
        except ValueError:
            pass
    return True

def tick_traps_end_turn(state: GameState):
    ensure_traps(state)
    kept = []
    for t in state.traps:
        t["duration"] -= 1
        if t["duration"] <= 0:
            log(f"TRAP_EXPIRE owner={t['owner']} pos=({t['r']},{t['c']})")
        else:
            kept.append(t)
    state.traps = kept

def remove_unit(u: Unit, state: "GameState" = None):
    side = u.owner
    if u in UNITS[side]:
        UNITS[side].remove(u)
    if state is not None:
        if not hasattr(state, "dead_pool") or state.dead_pool is None:
            state.dead_pool = {"A": [], "B": []}
        state.dead_pool[side].append(u)



# =============================================================================
# SYSTÈME DE PASSIFS (refacto 2026-02)
# =============================================================================
# Passifs identifiés dans Data_8_Factions.json :
#   passive_effect  → hooks on_death / on_attacked / pre_attack / aura
#   terrain_like_effect → sous-catégories remappées selon tags + texte

def _passive_action_id(unit) -> str:
    """Retourne l'action_id stocké dans ability_effects, ou ''."""
    eff = getattr(unit, "ability_effects", {}) or {}
    return str(eff.get("type") or eff.get("action_id") or "")

def _passive_tags(unit) -> list:
    """Retourne les action_tags stockés, ou []."""
    eff = getattr(unit, "ability_effects", {}) or {}
    return list(eff.get("action_tags") or [])

def _immune_direct_damage(unit) -> bool:
    """Golem de Ferraille : immunisé aux dégâts directs (ignore_def=True)."""
    eff = getattr(unit, "ability_effects", {}) or {}
    return bool(eff.get("immune_direct_damage"))

# ──────────────────────────────────────────────────────────────────────────────
# Hook 1 : on_attacked_passive  (avant hp -= dmg)
# ──────────────────────────────────────────────────────────────────────────────
def on_attacked_passive(state, target, attacker, dmg: int) -> None:
    """
    Déclenché après que les dégâts ont été calculés mais AVANT application.
    Gère :
        - Echo Glitché : counter 1 dmg direct la première fois par tour
        - Forteresse X-0 Mode Bastion : contre 1 dmg si pas bougé
    """
    if attacker is None or target is None:
        return

    raw_text = str((getattr(target, "ability_effects", {}) or {}).get("raw_text", "")).lower()

    # Echo Glitché — Retour d'Erreur
    if "retour d'erreur" in raw_text or "erreur" in raw_text and "premier" in raw_text:
        key = f"echo_counter_turn_{getattr(state, 'turn_idx', 0)}"
        already = getattr(target, "_echo_counter_done", None)
        if already != getattr(state, "turn_idx", 0):
            target._echo_counter_done = getattr(state, "turn_idx", 0)
            apply_damage_to_unit(state, attacker, 1, source_tag="passive_counter", ignore_def=True, attacker=None)
            print(f"  [PASSIF] {target.name} riposte : {attacker.name} subit 1 dégât direct (Retour d'Erreur).")
            log(f"PASSIVE_COUNTER owner={target.owner} unit={target.name} vs={attacker.name}")

    # Déflecteur de Flux — Rétroaction : annule l'attaque et redirige sur l'ennemi le plus proche de l'attaquant
    if _passive_action_id(target) == "counter_redirect":
        enemy_char = attacker.owner
        ally_char = target.owner
        nearest = None
        best_dist = 9999
        for u in UNITS[enemy_char]:
            if u is not attacker and u.hp > 0:
                d = manhattan(attacker.row, attacker.col, u.row, u.col)
                if d < best_dist:
                    best_dist = d
                    nearest = u
        if nearest:
            apply_damage_to_unit(state, nearest, dmg, source_tag="passive_counter_redirect", ignore_def=True, attacker=None)
            print(f"  [PASSIF] {target.name} Rétroaction : attaque annulée → redirigée sur {nearest.name} ({dmg} dmg).")
        else:
            apply_damage_to_unit(state, attacker, dmg, source_tag="passive_counter_redirect", ignore_def=True, attacker=None)
            print(f"  [PASSIF] {target.name} Rétroaction : attaque renvoyée sur {attacker.name} ({dmg} dmg).")
        log(f"PASSIVE_COUNTER_REDIRECT owner={target.owner} unit={target.name} vs={attacker.name} redirect_to={getattr(nearest,'name','?') if nearest else attacker.name}")
        target._counter_redirect_fired = True
        return

    # Garde Ancien — Protection Divine : riposte gratuite à la première attaque reçue
    if getattr(target, "counter_first_attack", False):
        target.counter_first_attack = False
        apply_damage_to_unit(state, attacker, target.atk, source_tag="passive_counter", attacker=None)
        print(f"  [PASSIF] {target.name} Protection Divine : riposte {target.atk} dmg sur {attacker.name}.")
        log(f"PASSIVE_GUARD_ANCIENT_COUNTER owner={target.owner} unit={target.name} vs={attacker.name} dmg={target.atk}")

    # Forteresse Mobile X-0 — Mode Bastion : +1 DEF si pas bougé + renvoi 1 dmg
    if "mode bastion" in raw_text or "bastion" in raw_text:
        if not getattr(target, "has_moved", False):
            # Bonus DEF passif appliqué via temp_def si pas encore actif ce tour
            bastion_key = getattr(target, "_bastion_active_turn", None)
            if bastion_key != getattr(state, "turn_idx", 0):
                target._bastion_active_turn = getattr(state, "turn_idx", 0)
                target.temp_def = getattr(target, "temp_def", 0) + 1
                log(f"PASSIVE_BASTION_DEF owner={target.owner} unit={target.name} +1DEF")
            # Renvoi 1 dmg direct à la première attaque subie
            if not getattr(target, "_bastion_retaliated", False):
                target._bastion_retaliated = True
                apply_damage_to_unit(state, attacker, 1, source_tag="passive_bastion", ignore_def=True, attacker=None)
                print(f"  [PASSIF] {target.name} Mode Bastion : {attacker.name} subit 1 dégât en retour.")
                log(f"PASSIVE_BASTION_RETALIATE owner={target.owner} unit={target.name} vs={attacker.name}")

# ──────────────────────────────────────────────────────────────────────────────
# Hook 2 : on_death_passive  (après remove_unit)
# ──────────────────────────────────────────────────────────────────────────────
def on_death_passive(state, dead_unit, attacker, source_tag: str) -> None:
    """
    Déclenché quand une unité meurt.
    Gère :
        - Larve de l'Abîme : 1 dmg direct sur l'attaquant adjacent (melee only)
        - Fragment Miroir : -1 ATK sur l'attaquant adjacent pour 1 tour
    """
    if dead_unit is None:
        return

    raw_text = str((getattr(dead_unit, "ability_effects", {}) or {}).get("raw_text", "")).lower()
    is_melee = attacker is not None and "trap" not in source_tag and "poison" not in source_tag

    # Larve de l'Abîme — Explosion Viscérale
    if ("explosion" in raw_text or "viscérale" in raw_text) and is_melee:
        if manhattan(dead_unit.row, dead_unit.col, attacker.row, attacker.col) <= 1:
            apply_damage_to_unit(state, attacker, 1, source_tag="passive_explosion", ignore_def=True, attacker=None)
            print(f"  [PASSIF] {dead_unit.name} Explosion Viscérale : {attacker.name} subit 1 dégât direct !")
            log(f"PASSIVE_EXPLOSION vs={attacker.name}")

    # Fragment Miroir — Réflexion Fragilisante
    if ("réflexion" in raw_text or "fragilisante" in raw_text) and is_melee:
        if manhattan(dead_unit.row, dead_unit.col, attacker.row, attacker.col) <= 1:
            debuffs = (getattr(dead_unit, "ability_effects", {}) or {}).get("debuffs") or [{"stat": "ATK", "amount": -1}]
            for d in debuffs:
                amount = int(d.get("amount", -1))
                attacker.atk = max(0, attacker.atk + amount)
                attacker.atk_debuff_duration = max(getattr(attacker, "atk_debuff_duration", 0), 1)
                attacker.atk_debuff_amount = getattr(attacker, "atk_debuff_amount", 0) + amount
            print(f"  [PASSIF] {dead_unit.name} Réflexion Fragilisante : {attacker.name} perd {abs(amount)} ATK pour 1 tour.")
            log(f"PASSIVE_REFLECT_DEBUFF vs={attacker.name} amount={amount}")

# ──────────────────────────────────────────────────────────────────────────────
# Hook 3 : get_passive_atk_bonus  (appelé avant toute attaque)
# ──────────────────────────────────────────────────────────────────────────────
def get_passive_atk_bonus(state, attacker, target) -> int:
    """
    Calcule le bonus ATK passif de l'attaquant selon les règles de son passif.
    Retourne le bonus à ajouter (peut être 0).
    Gère :
        - Casseur de Cailloux   : +1 ATK si target.DEF > self.DEF
        - Jeune Traqueur        : +1 ATK si autre allié adjacent à la cible
        - Lancier Écaille-Feu   : +2 ATK si ennemi vient d'entrer en adjacent (flag)
        - Briseur de Lune       : +2 ATK si HP < 50% max
        - Obsidian Maw          : +1 ATK par Lycan allié adjacent (max +3)
    """
    if attacker is None or target is None:
        return 0

    bonus = 0
    raw_text = str((getattr(attacker, "ability_effects", {}) or {}).get("raw_text", "")).lower()
    buffs = (getattr(attacker, "ability_effects", {}) or {}).get("buffs") or []
    owner = attacker.owner
    allies = [u for u in UNITS[owner] if u is not attacker and u.hp > 0]

    # Casseur de Cailloux — +1 ATK si DEF cible > DEF soi
    if "amour de la tôle" in raw_text or ("tôle" in raw_text and "def" in raw_text):
        target_def = target.defense + getattr(target, "temp_def", 0)
        self_def = attacker.defense + getattr(attacker, "temp_def", 0)
        if target_def > self_def:
            bonus += 1
            print(f"  [PASSIF] {attacker.name} Amour de la Tôle : +1 ATK (DEF cible {target_def} > DEF soi {self_def}).")

    # Jeune Traqueur / Instinct de Meute — +1 ATK si allié adjacent à la cible
    if "instinct de meute" in raw_text or "meute" in raw_text:
        ally_adj_to_target = any(
            manhattan(a.row, a.col, target.row, target.col) <= 1 for a in allies
        )
        if ally_adj_to_target:
            bonus += 1
            print(f"  [PASSIF] {attacker.name} Instinct de Meute : +1 ATK (allié adjacent à la cible).")

    # Obsidian Maw Primordial — Voracité de Meute : +1 ATK par Lycan adjacent (max +3)
    if "voracité" in raw_text or "voracite" in raw_text:
        adj_lycans = sum(
            1 for a in allies
            if manhattan(a.row, a.col, attacker.row, attacker.col) <= 1
        )
        add = min(3, adj_lycans)
        if add > 0:
            bonus += add
            print(f"  [PASSIF] {attacker.name} Voracité de Meute : +{add} ATK ({adj_lycans} allié(s) adjacent(s)).")

    # Briseur de Lune — Rage du Croissant : +2 ATK si HP < 50%
    if "rage du croissant" in raw_text or "croissant" in raw_text:
        hp_max = getattr(attacker, "hp_max", attacker.hp + 1)
        if attacker.hp < hp_max / 2:
            bonus += 2
            print(f"  [PASSIF] {attacker.name} Rage du Croissant : +2 ATK (HP={attacker.hp}/{hp_max}).")

    # Lancier Écaille-Feu — Lance d'Interception : +2 ATK si flag posé
    if getattr(attacker, "_interception_bonus", 0) > 0 and target is not None:
        bonus += 2
        attacker._interception_bonus = 0
        print(f"  [PASSIF] {attacker.name} Lance d'Interception : +2 ATK.")

    if bonus > 0:
        log(f"PASSIVE_ATK_BONUS owner={owner} unit={attacker.name} bonus={bonus}")

    return bonus

# ──────────────────────────────────────────────────────────────────────────────
# Hook 4 : tick_aura_passives  (fin de tour)
# ──────────────────────────────────────────────────────────────────────────────
def tick_aura_passives(state) -> None:
    """
    Applique les auras permanentes à chaque fin de tour.
    Gère :
      - Totem-Furie Totémique : +1 ATK aux Orcs adjacents si 2+ Orcs adj
      - Forteresse X-0 : reset _bastion_retaliated pour prochain tour
      - Micro-Sentinelle Défense : +1 DEF passif au QG adjacent (flag)
    """
    for side in ('A', 'B'):
        for u in UNITS[side]:
            if u.hp <= 0:
                continue
            raw_text = str((getattr(u, "ability_effects", {}) or {}).get("raw_text", "")).lower()

            # Totem-Furie — Totem de Fureur
            if "totem de fureur" in raw_text or "fureur" in raw_text and "adjacent" in raw_text:
                allies_adj = [
                    a for a in UNITS[side]
                    if a is not u and a.hp > 0 and manhattan(a.row, a.col, u.row, u.col) <= 1
                ]
                if len(allies_adj) >= 2:
                    for ally in allies_adj:
                        # On ne buff pas en boucle infinie : on marque le tour
                        last_buffed = getattr(ally, "_totem_buffed_turn", None)
                        if last_buffed != getattr(state, "turn_idx", 0):
                            ally._totem_buffed_turn = getattr(state, "turn_idx", 0)
                            ally.atk += 1
                            log(f"PASSIVE_TOTEM_FURY owner={side} unit={ally.name} +1ATK")
                    print(f"  [PASSIF] {u.name} Totem de Fureur : {len(allies_adj)} alliés adjacents gagnent +1 ATK.")

            # Forteresse X-0 — reset flag retaliation chaque tour
            if "mode bastion" in raw_text or "bastion" in raw_text:
                u._bastion_retaliated = False

            # Lancier Écaille-Feu — reset flag interception
            if "interception" in raw_text:
                u._interception_bonus = 0

def apply_damage_to_unit(state: GameState,
                        target: Unit | None,
                        raw_atk: int,
                        source_tag: str = "attack",
                        ignore_def: bool = False,
                        attacker: Unit | None = None) -> int:
    """
    Applique des dégâts à une unité.

    - target peut être None : dans ce cas, on log et on ne fait rien.
    - Si ignore_def=True : dégâts bruts (traps spéciaux, true damage).
    - Sinon : armure douce + facteur de niveau de l’attaquant.
    """
    # Sécurité : pas de cible -> on ne fait rien
    if target is None:
        log(f"DAMAGE_UNIT[{source_tag}]: target=None (appel ignoré)")
        return 0

    # DEF effective de la cible
    eff_def = target.defense + getattr(target, "temp_def", 0)

    if ignore_def:
        dmg = max(1, raw_atk)
        mode = "ignore_def"
        armor_factor = None
    else:
        # Niveau de l’attaquant (1 par défaut si inconnu)
        lvl = 1
        if attacker is not None and hasattr(attacker, "level"):
            try:
                lvl = max(1, int(attacker.level))
            except Exception:
                lvl = 1

        # Armure douce : la DEF compte moins si l’attaquant est haut niveau
        # lvl=1 -> ~70% de la DEF, lvl=5 -> ~30%
        armor_factor = 0.8 - 0.1 * lvl
        armor_factor = max(0.3, min(0.8, armor_factor))

        reduced_def = int(eff_def * armor_factor)
        raw = raw_atk - reduced_def
        dmg = max(1, raw)
        mode = f"soft_armor_l{lvl}"

    # Stats: damage (optional)
    st = _ddm_get_stats(state)
    if st:
        mode_stats = _ddm_mode(state)
        try:
            attacker_name = getattr(attacker, "name", None) if attacker is not None else None
            target_name = getattr(target, "name", None) if target is not None else None
            am = _ddm_unit_meta(state, attacker) if attacker is not None else None
            tm = _ddm_unit_meta(state, target)
            st.note_damage(mode_stats, attacker_name, target_name, dmg, attacker_meta=am, target_meta=tm)
        except Exception:
            pass

    # Passif : on_attacked (avant hp -= dmg, sauf si déjà en récursion passif)
    if source_tag not in ("passive_counter", "passive_explosion", "passive_bastion", "ability_self_dmg", "passive_bastion_retaliate"):
        if _immune_direct_damage(target) and ignore_def:
            print(f"  [PASSIF] {target.name} est immunisé aux dégâts directs !")
            log(f"PASSIVE_IMMUNE owner={target.owner} unit={target.name} source={source_tag}")
            return 0
        try:
            on_attacked_passive(state, target, attacker, dmg)
        except Exception:
            pass
        if getattr(target, "_counter_redirect_fired", False):
            target._counter_redirect_fired = False
            return 0

    target.hp -= dmg

    print(
        f"  -> {target.name} ({target.owner}) subit {dmg} dégâts "
        f"(ATK={raw_atk}, DEF={eff_def}, mode={mode}) -> HP={target.hp}"
    )
    log(
        f"DAMAGE_UNIT[{source_tag}]: owner={target.owner} name={target.name} "
        f"raw={raw_atk} eff_def={eff_def} mode={mode} "
        f"armor_factor={armor_factor} dmg={dmg} hp_now={target.hp}"
    )

    if target.hp <= 0:
        print(f"      [DEAD]  {target.name} ({target.owner}) est détruit !")
        log(
            f"UNIT_DEAD[{source_tag}]: owner={target.owner} name={target.name} "
            f"pos=({target.row},{target.col})"
        )
        # RL ctx : kills/pertes pendant le tour courant (vue joueur actif)
        try:
            ctx = getattr(state, "rl_turn_ctx", None)
            if isinstance(ctx, dict) and ctx.get("enabled"):
                player = ctx.get("player")
                opponent = ctx.get("opponent")
                if opponent and target.owner == opponent:
                    ctx["kills_enemy"] = ctx.get("kills_enemy", 0) + 1
                elif player and target.owner == player:
                    ctx["losses_self"] = ctx.get("losses_self", 0) + 1
        except Exception:
            pass

        # Stats: death / TTK / kill
        st = _ddm_get_stats(state)
        if st:
            mode_stats = _ddm_mode(state)
            try:
                meta_t = _ddm_unit_meta(state, target)
                ttk = None
                try:
                    sturn = getattr(target, "spawn_turn", None)
                    cturn = getattr(state, "turn_idx", None)
                    if sturn is not None and cturn is not None:
                        ttk = int(cturn) - int(sturn) + 1
                except Exception:
                    ttk = None
                st.note_unit_death(
                    mode_stats,
                    getattr(target, "name", "?"),
                    meta_t.get("faction") or "?",
                    getattr(target, "level", None) or (meta_t.get("level") or 1),
                    ttk_turns=ttk,
                    unit_type=meta_t.get("type") or "mob",
                )
                if attacker is not None:
                    meta_a = _ddm_unit_meta(state, attacker)
                    st.note_unit_kill(
                        mode_stats,
                        getattr(attacker, "name", "?"),
                        faction_name=meta_a.get("faction") or "?",
                        level=meta_a.get("level"),
                        unit_type=meta_a.get("type") or "?",
                    )
            except Exception:
                pass

        # Passif mort
        try:
            on_death_passive(state, target, attacker, source_tag)
        except Exception:
            pass
        remove_unit(target, state)

    return dmg


def find_enemy_adjacent(owner_char: str, r: int, c: int):
    enemy = 'B' if owner_char == 'A' else 'A'
    for u in UNITS[enemy]:
        if manhattan(r, c, u.row, u.col) == 1:
            return u
    return None


def find_enemy_in_range(owner_char: str, r: int, c: int, rng: int):
    enemy = 'B' if owner_char == 'A' else 'A'
    best = None
    best_dist = None
    for u in UNITS[enemy]:
        d = manhattan(r, c, u.row, u.col)
        if d <= rng:
            if best is None or d < best_dist:
                best = u
                best_dist = d
    return best



# ----------------------------------------------------------------------
#  Ability parsing helpers (light heuristic for legacy "action_speciale" texts)
# ----------------------------------------------------------------------

_MULTI_ATTACK_RE = re.compile(
    r"Attaque\s+normale\s*\((\d+)\s*ATK\).*?Attaque\s+lourde\s*\((\d+)\s*ATK\)",
    re.IGNORECASE | re.DOTALL,
)
_SINGLE_ATTACK_RE = re.compile(
    r"Attaque\s+normale\s*\((\d+)\s*ATK\)",
    re.IGNORECASE,
)



def _unit_at(owner_char: str, r: int, c: int, enemy_only: bool = False):
    """Retourne une unité sur (r,c). Si enemy_only=True, seulement une unité ennemie de owner_char."""
    for side in ("A", "B"):
        if enemy_only and side == owner_char:
            continue
        for u in UNITS.get(side, []):
            if getattr(u, "row", None) == r and getattr(u, "col", None) == c and getattr(u, "hp", 0) > 0:
                return u
    return None


def process_tile_effects(state: GameState, phase_tag: str = "") -> None:
    """Tick fin de tour : applique les zones simples posées via capacités (durée en tours)."""
    effs = getattr(state, "tile_effects", None)
    if not effs:
        return
    keep = []
    for e in list(effs):
        try:
            et = e.get("type")
            if et != "zone_damage":
                keep.append(e)
                continue
            r = int(e.get("row"))
            c = int(e.get("col"))
            dmg = int(e.get("damage", 0) or 0)
            dur = int(e.get("duration", 1) or 1)
            ign = bool(e.get("ignore_def"))
            src = e.get("source", "zone")
            # Applique à toute unité sur la case (A ou B)
            tgtA = _unit_at("B", r, c, enemy_only=False)  # any unit
            if tgtA:
                print(f"  [ZONE] {src} tick sur {tgtA.name} en ({r},{c}) : {dmg} dégâts{' directs' if ign else ''}.")
                apply_damage_to_unit(state, tgtA, dmg, source_tag="tile_zone", ignore_def=ign, attacker=None)
            dur -= 1
            if dur > 0:
                e["duration"] = dur
                keep.append(e)
        except Exception:
            # si erreur, on drop l'effet
            pass
    state.tile_effects = keep

def _parse_multi_attack_variants(raw_text: str):
    """Retourne [(label, atk_cost), ...] ou [] si non reconnu."""
    if not raw_text:
        return []
    m = _MULTI_ATTACK_RE.search(raw_text)
    if m:
        try:
            n = int(m.group(1))
            h = int(m.group(2))
            out = []
            if n > 0: out.append(("normale", n))
            if h > 0: out.append(("lourde", h))
            return out
        except Exception:
            return []
    # Fallback : variante unique "Attaque normale (X ATK)"
    m2 = _SINGLE_ATTACK_RE.search(raw_text)
    if m2:
        try:
            n = int(m2.group(1))
            return [("normale", n)] if n > 0 else []
        except Exception:
            return []
    return []

def _best_affordable_variant(pool: dict, variants: list[tuple[str,int]]):
    """Choisit la variante la plus chère payable (fallback: la moins chère)."""
    if not variants:
        return None
    atk_have = int(pool.get("ATK", 0) or 0)
    affordable = [v for v in variants if v[1] <= atk_have]
    if affordable:
        return max(affordable, key=lambda x: x[1])
    return min(variants, key=lambda x: x[1])


def ability_needs_target(unit) -> bool:
    """Retourne True si la capacité de cette unité nécessite un ciblage manuel."""
    effects = getattr(unit, "ability_effects", None) or {}
    raw = (effects.get("raw_text") or "").lower()
    return any(w in raw for w in ["brume", "toxique", "zone de brume"])


def use_unit_ability(state: GameState, unit: Unit, owner_char: str,
                     target_pos: tuple = None) -> bool:
    """
    Utilise la capacité d'une unité (MAJ9):
    - Le coût (ATK/DEF/MOVE/TRAP/...) est payé seulement si l'action est VALIDÉE
    - target_pos : (row, col) fourni par le joueur humain pour les capacités ciblées
    """
    if not unit.has_ability:
        print("Cette unité n'a pas de capacité définie.")
        return False
    if unit.ability_uses_this_turn >= unit.ability_max_per_turn:
        print("Capacité déjà utilisée ce tour.")
        return False

    # Pool du bon camp
    pool = get_pool_for_owner(state, owner_char)

    # Effets / type
    effects = unit.ability_effects or {}
    etype = effects.get("type") or effects.get("effect_type")
    raw = effects.get("raw_text")

    # Auto-détection si aucun type explicite mais des clés connues
    if etype is None:
        if "buff_def" in effects:
            etype = "buff_def"
        elif "damage" in effects:
            etype = "damage"
        elif "poison" in effects:
            etype = "poison"


    # Heuristique : certains mobs ont une "capacité" texte du style :
    # "Attaque normale (1 ATK). Attaque lourde (3 ATK)."
    # => on l'implémente comme une attaque directe (damage) vers la première cible en portée.
    if etype in (None, "attack_modes", "attack_variant", "basic_attack_only") and raw:
        variants = _parse_multi_attack_variants(raw)
        if variants:
            chosen = _best_affordable_variant(pool, variants)
            if chosen is not None:
                label, atk_cost = chosen
                # On force un effet "damage" + un coût ATK cohérent (sans input, OK pour IA aussi)
                # NB: on modifie le dict local `effects` en place pour rester compatible avec le reste.
                try:
                    effects.clear()
                    effects.update({
                        "type": "damage",
                        "damage": int(atk_cost),
                        "range": unit.ability_range or 1,
                        "raw_text": raw,
                        "variant": label,
                    })
                    unit.ability_cost = {"ATK": int(atk_cost)}
                    etype = "damage"
                except Exception:
                    pass

    # Pré-validation ciblage (évite de consommer des ressources sur des fails de ciblage)
    pre_target = None
    target_type = getattr(unit, "ability_target_type", None) or effects.get("target_type") or effects.get("target") or "enemy"

    if etype in ("damage", "poison", "ranged_damage", "direct_damage", "true_damage",
                 "armor_break", "debuff_atk", "execute_crit",
                 "increase_enemy_cost", "confusion_redirect",
                 "redirect_next_attack_to_adjacent_ally", "random_retarget",
                 "direct_damage_ignore_def", "basic_plus_buff") and target_type in ("enemy", "auto_enemy", "enemy_only"):
        rng = unit.ability_range or effects.get("range", 1) or 1
        pre_target = find_enemy_in_range(owner_char, unit.row, unit.col, rng)
        if not pre_target:
            print("     Aucun ennemi à portée pour la capacité.")
            try:
                canon_log(
                    "ABILITY_TRY",
                    player=owner_char,
                    unit=f"{getattr(unit,'uid','?')}:{unit.name}",
                    ability=unit.ability_name,
                    cap_used=0,
                    cost=unit.ability_cost or {},
                    result="FAIL",
                    reason="no_target",
                )
            except Exception:
                pass
            return False

    # Vérification du coût — mais on NE PAYE PAS tant que l'effet n'est pas appliqué.
    if not can_pay_cost(pool, unit.ability_cost):
        print("Pas assez de ressources pour cette capacité.")
        try:
            canon_log(
                "ABILITY_TRY",
                player=owner_char,
                unit=f"{getattr(unit,'uid','?')}:{unit.name}",
                ability=unit.ability_name,
                cap_used=0,
                cost=unit.ability_cost or {},
                result="FAIL",
                reason="no_resource",
            )
        except Exception:
            pass
        return False

    # Types supportés dans le moteur (MAJ9 : pas de terrain TRAP / zone)
    supported = etype in (
        "buff_def", "damage", "poison",
        "direct_damage", "buff_self", "heal",
        "apply_status", "apply_debuff",
        "ranged_damage", "true_damage", "swap_positions",
        "terrain_like_effect",
        "buff_self_if_adjacent_hq",
        "buff_target_def",
        "swap_atk_def_for_attack",
        "passive_effect",
        "armor_break", "debuff_atk", "execute_crit",
        "teleport",
        "increase_enemy_cost", "revive_adjacent",
        "confusion_redirect", "redirect_next_attack_to_adjacent_ally",
        "random_retarget", "counter_redirect",
        # types implémentés mais manquants de la liste
        "apply_status_aura_end_game",
        "basic_plus_buff",
        "buff_def_and_counter",
        "direct_damage_ignore_def",
        "place_terrain_token",
    )
    if not supported:
        # On affiche la description si elle existe, mais AUCUNE ressource n'est consommée.
        if raw:
            print(f"     Effet (non implémenté) : {raw}")
        else:
            print("     (Effet spécial non encore implémenté dans le moteur)")
        try:
            canon_log(
                "ABILITY_TRY",
                player=owner_char,
                unit=f"{getattr(unit,'uid','?')}:{unit.name}",
                ability=unit.ability_name,
                cap_used=0,
                cost=unit.ability_cost or {},
                result="FAIL",
                reason="unsupported_effect",
            )
        except Exception:
            pass
        log(f"ABILITY_UNSUPPORTED {owner_char}: unit={unit.name} type={etype} raw={raw}")
        return False
    elif etype == "place_trap":
        rng = int(getattr(unit, "ability_range", 2) or 2)
        dmg = int(effects.get("damage", 3) or 3)
        dur = int(effects.get("duration", 2) or 2)

        # humain si hvh OU (hvia & side A)
        rm = getattr(state, "run_mode", "") or ""
        is_human = (not _is_ai_vs_ai()) and (rm == "hvh" or (rm == "hvia" and owner_char == "A"))

        # cases valides = walkable a/b uniquement
        candidates = []
        for rr in range(HEIGHT):
            for cc in range(WIDTH):
                if manhattan(unit.row, unit.col, rr, cc) <= rng:
                    if not in_bounds(state.board, rr, cc):
                        continue
                    if not is_walkable_ab(state.board, rr, cc):
                        continue
                    if state.board[rr][cc] in ("A", "B"):
                        continue
                    u2, _ = get_unit_at(rr, cc)
                    if u2 is not None:
                        continue
                    if trap_at(state, rr, cc) is not None:
                        continue
                    candidates.append((rr, cc))

        if not candidates:
            print("     Aucun emplacement valide pour poser un piège.")
            ok = False
        else:
            if is_human:
                raw_in = input("Coordonnées trap (r,c) : ").strip().replace(" ", "")
                try:
                    rs, cs = raw_in.split(",")
                    rr, cc = int(rs), int(cs)
                except Exception:
                    print("     Format invalide. Exemple : 5,7")
                    ok = False
                else:
                    if (rr, cc) not in candidates:
                        print("     Case invalide (hors portée / non-walkable / occupée / déjà piégée).")
                        ok = False
                    else:
                        ok = place_trap(state, owner_char, rr, cc, damage=dmg, duration=dur)
            else:
                enemies = UNITS["B"] if owner_char == "A" else UNITS["A"]
                def score(pos):
                    rr, cc = pos
                    if not enemies:
                        return 0
                    return -min(manhattan(rr, cc, e.row, e.col) for e in enemies)
                best = max(candidates, key=score)
                ok = place_trap(state, owner_char, best[0], best[1], damage=dmg, duration=dur)     
    value = int(effects.get("value", effects.get("effect_value", 0)) or 0)
    duration = int(effects.get("duration", effects.get("effect_duration", 0)) or 1)

    ok = False

    # 1) Buff DEF sur soi
    if etype == "buff_def":
        if value <= 0:
            value = int(effects.get("buff_def", 2) or 2)
        if duration <= 0:
            duration = int(effects.get("duration", 1) or 1)
        # Guard : inutile de se buffer si aucun ennemi à portée raisonnable (rayon 5)
        nearest_threat = find_enemy_in_range(owner_char, unit.row, unit.col, rng=5)
        if nearest_threat is None:
            log(f"ABILITY_SKIP_{owner_char}: unit={unit.name} type=buff_def reason=no_threat_nearby")
            return False

        unit.temp_def += value
        unit.buff_def_duration = max(getattr(unit, "buff_def_duration", 0), duration)
        print(
            f"     {unit.name} gagne +{value} DEF pendant {duration} tour(s). "
            f"(DEF totale = {unit.defense + unit.temp_def})"
        )
        log(f"ABILITY_BUFF_DEF {owner_char}: unit={unit.name} value={value} duration={duration}")
        ok = True

    # 2) Dégâts directs
    # 2) Dégâts / pièges (tile ou enemy)
    elif etype == "damage":
        # direct ? (ignore DEF) si explicite dans les effets/texte
        ignore_def = bool(effects.get("ignore_def"))
        raw_txt = (effects.get("raw_text") or "").lower()
        if ("direct" in raw_txt) or ("dégât direct" in raw_txt) or ("degat direct" in raw_txt) or ("dégâts directs" in raw_txt):
            ignore_def = True

        target_type = getattr(unit, "ability_target_type", None) or effects.get("target_type") or effects.get("target") or "enemy"
        rng = unit.ability_range or effects.get("range", 1) or 1

        # --- (A) cible ENNEMI ---
        if target_type in ("enemy", "auto_enemy", "enemy_only"):
            target = pre_target
            if not target:
                print("     Aucun ennemi valide pour les dégâts.")
                log(f"ABILITY_FAIL {owner_char}: unit={unit.name} reason=no_target_post")
                ok = False
            else:
                dmg_raw = int(value or effects.get("damage", 0) or unit.atk)
                print(
                    f"     {unit.name} inflige {dmg_raw} dégâts à {target.name} "
                    f"(HP avant = {target.hp})."
                )
                apply_damage_to_unit(
                    state,
                    target,
                    dmg_raw,
                    source_tag="ability_damage",
                    ignore_def=ignore_def,
                    attacker=unit,
                )
                log(f"ABILITY_DAMAGE {owner_char}: from={unit.name} to={target.name} dmg={dmg_raw} direct={int(ignore_def)}")
                ok = True

        # --- (B) cible CASE (piège/zone) ---
        else:
            # Choix de case : humain -> input ; IA -> heuristique (case ennemi si possible, sinon random)
            rr = cc = None
            if _ddm_mode(state) in ("hvia", "console") and owner_char == "A":
                try:
                    s = input("     Case cible (r,c) (Enter=annuler) : ").strip()
                except Exception:
                    s = ""
                if not s:
                    return False
                parts = re.split(r"[ ,;]+", s)
                if len(parts) >= 2:
                    try:
                        rr, cc = int(parts[0]), int(parts[1])
                    except Exception:
                        rr = cc = None
            if rr is None or cc is None:
                # IA : prend un ennemi en portée si existe, sinon une case en portée
                cand_enemy = find_enemy_in_range(owner_char, unit.row, unit.col, rng)
                if cand_enemy:
                    rr, cc = cand_enemy.row, cand_enemy.col
                else:
                    # bornes board
                    H = len(state.board) if getattr(state, "board", None) is not None else 0
                    W = len(state.board[0]) if H and state.board[0] is not None else 0
                    best = None
                    for dr in range(-rng, rng+1):
                        for dc in range(-rng, rng+1):
                            if abs(dr)+abs(dc) > rng:
                                continue
                            r2, c2 = unit.row+dr, unit.col+dc
                            if 0 <= r2 < H and 0 <= c2 < W:
                                best = (r2, c2)
                                break
                        if best:
                            break
                    if best:
                        rr, cc = best
            if rr is None or cc is None:
                print("     Aucune case valide.")
                ok = False
            else:
                dmg_raw = int(value or effects.get("damage", 0) or 0)
                dur = int(effects.get("duration", 1) or 1)
                # Enregistre une zone simple (tick fin de tour)
                if not hasattr(state, "tile_effects") or state.tile_effects is None:
                    state.tile_effects = []
                state.tile_effects.append({
                    "type": "zone_damage",
                    "row": rr,
                    "col": cc,
                    "damage": dmg_raw,
                    "duration": dur,
                    "ignore_def": bool(ignore_def),
                    "owner": owner_char,
                    "source": unit.name,
                })
                print(f"     {unit.name} pose un effet au sol en ({rr},{cc}) pour {dur} tour(s).")
                # Application immédiate si une unité ennemie est sur la case
                tgt = _unit_at(owner_char, rr, cc, enemy_only=True)
                if tgt:
                    print(f"     Effet immédiat sur {tgt.name} (HP avant={tgt.hp}).")
                    apply_damage_to_unit(state, tgt, dmg_raw, source_tag='ability_zone', ignore_def=ignore_def, attacker=unit)
                log(f"ABILITY_TILE {owner_char}: from={unit.name} r={rr} c={cc} dmg={dmg_raw} dur={dur} direct={int(ignore_def)}")
                ok = True

# 3) Poison (stacks + durée, sans terrain)
    elif etype == "poison":
        target = pre_target
        if not target:
            print("     Aucun ennemi valide pour le poison.")
            log(f"ABILITY_FAIL {owner_char}: unit={unit.name} reason=no_target_post")
            ok = False
        else:
            stacks = int(value or effects.get("poison", 1) or 1)
            dmg_per_stack = int(effects.get("poison_damage", 1) or 1)
            if duration <= 0:
                duration = int(effects.get("duration", 2) or 2)

            target.poison_stacks = int(getattr(target, "poison_stacks", 0)) + stacks
            target.poison_damage = dmg_per_stack
            target.poison_duration = max(int(getattr(target, "poison_duration", 0)), duration)

            print(
                f"     {target.name} est empoisonné : +{stacks} stack(s), "
                f"{dmg_per_stack} dmg/stack, durée {target.poison_duration}."
            )
            log(
                f"ABILITY_POISON {owner_char}: from={unit.name} to={target.name} "
                f"stacks_add={stacks} dmg_per_stack={dmg_per_stack} dur={target.poison_duration}"
            )
            ok = True


    # ---------------------------------------------------------------
    # BATCH 2 — Nouveaux action_id (refacto 2026-02)
    # ---------------------------------------------------------------

    # 4) direct_damage — dégâts fixes (valeur action_params["damage"])
    elif etype == "direct_damage":
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, unit.ability_range or 1)
        if not target:
            print("     Aucun ennemi à portée.")
            ok = False
        else:
            params = unit.ability_effects or {}
            dmg_raw = int(params.get("damage", 0) or params.get("damage_values", [0])[0] or unit.atk)
            apply_damage_to_unit(state, target, dmg_raw, source_tag="ability_direct", attacker=unit)
            print(f"     {unit.name} inflige {dmg_raw} dégâts directs à {target.name}.")
            log(f"ABILITY_DIRECT_DMG {owner_char}: from={unit.name} to={target.name} dmg={dmg_raw}")
            ok = True

    # 5) ranged_damage — dégâts à portée > 1
    elif etype == "ranged_damage":
        rng = int(unit.ability_range or effects.get("range", 2) or 2)
        target = find_enemy_in_range(owner_char, unit.row, unit.col, rng)
        if not target:
            print(f"     Aucun ennemi à portée {rng}.")
            ok = False
        else:
            dmg_raw = int(effects.get("damage", 0) or unit.atk)
            apply_damage_to_unit(state, target, dmg_raw, source_tag="ability_ranged", attacker=unit)
            print(f"     {unit.name} tire sur {target.name} (portée {rng}) : {dmg_raw} dégâts.")
            log(f"ABILITY_RANGED_DMG {owner_char}: from={unit.name} to={target.name} dmg={dmg_raw} range={rng}")
            ok = True

    # 6) true_damage — dégâts ignorant la DEF + self-damage optionnel
    elif etype == "true_damage":
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, unit.ability_range or 1)
        if not target:
            print("     Aucun ennemi à portée pour true_damage.")
            ok = False
        else:
            params = effects
            atk_bonus = 0
            for b in (params.get("buffs") or []):
                if b.get("stat") == "ATK":
                    atk_bonus += int(b.get("amount", 0))
            dmg_raw = int(params.get("damage", 0) or params.get("damage_values", [0])[0] or unit.atk) + atk_bonus
            apply_damage_to_unit(state, target, dmg_raw, source_tag="ability_true", ignore_def=True, attacker=unit)
            print(f"     {unit.name} inflige {dmg_raw} dégâts vrais (ignore DEF) à {target.name}.")
            # Self-damage si "true_damage": true dans params (ex: Démon Mineur)
            self_dmg = int(params.get("self_damage", 0) or params.get("damage_values", [0, 0])[1] if len(params.get("damage_values", [])) > 1 else 0)
            if self_dmg > 0 or params.get("true_damage") is True:
                sd = self_dmg or 1
                apply_damage_to_unit(state, unit, sd, source_tag="ability_self_dmg", ignore_def=True, attacker=None)
                print(f"     {unit.name} subit {sd} dégât(s) direct(s) en retour.")
            log(f"ABILITY_TRUE_DMG {owner_char}: from={unit.name} to={target.name} dmg={dmg_raw}")
            ok = True

    # 7) heal — soigne un allié adjacent (ou soi-même) de N HP
    elif etype == "heal":
        heal_amount = int(effects.get("heal", 3) or effects.get("value", 3) or 3)
        # Cherche un allié adjacent blessé (priorité au plus bas HP), fallback self
        allies = UNITS[owner_char]
        adjacent_wounded = [
            u for u in allies
            if u is not unit and u.hp > 0 and manhattan(unit.row, unit.col, u.row, u.col) == 1
            and u.hp < getattr(u, "hp_max", u.hp + 1)
        ]
        target_heal = min(adjacent_wounded, key=lambda u: u.hp) if adjacent_wounded else unit
        old_hp = target_heal.hp
        hp_max = getattr(target_heal, "hp_max", old_hp + heal_amount)
        target_heal.hp = min(hp_max, old_hp + heal_amount)
        gained = target_heal.hp - old_hp
        print(f"     {unit.name} soigne {target_heal.name} de {gained} HP ({old_hp} → {target_heal.hp}).")
        log(f"ABILITY_HEAL {owner_char}: from={unit.name} to={target_heal.name} gained={gained}")
        ok = True

    # 8) buff_self — buff temporaire sur ATK/DEF/MOVE de l'unité
    elif etype == "buff_self":
        buffs = effects.get("buffs") or []
        if not buffs:
            # Fallback : lire depuis action_params si dispo via raw
            for kw, stat in [("atk", "ATK"), ("def", "DEF"), ("move", "MOVE")]:
                if kw in (effects.get("raw_text") or "").lower():
                    buffs = [{"stat": stat, "amount": 2}]
                    break
        if not buffs:
            buffs = [{"stat": "DEF", "amount": 2}]
        duration = int(effects.get("duration", 1) or 1)
        for b in buffs:
            stat = b.get("stat", "DEF")
            amount = int(b.get("amount", 2))
            if stat == "DEF":
                unit.temp_def += amount
                unit.buff_def_duration = max(getattr(unit, "buff_def_duration", 0), duration)
                print(f"     {unit.name} gagne +{amount} DEF pendant {duration} tour(s). (DEF totale = {unit.defense + unit.temp_def})")
            elif stat == "ATK":
                unit.atk += amount
                # enregistre le buff pour tick de fin de tour
                if not hasattr(state, "temp_atk_buffs"):
                    state.temp_atk_buffs = []
                state.temp_atk_buffs.append({"unit_uid": getattr(unit, "uid", None), "amount": amount, "duration": duration})
                print(f"     {unit.name} gagne +{amount} ATK pendant {duration} tour(s).")
            elif stat == "MOVE":
                pool_owner = get_pool_for_owner(state, owner_char)
                pool_owner["MOVE"] = pool_owner.get("MOVE", 0) + amount
                print(f"     {unit.name} gagne +{amount} MOVE ce tour.")
            log(f"ABILITY_BUFF_SELF {owner_char}: unit={unit.name} stat={stat} amount={amount} dur={duration}")
        ok = True

    # 9) apply_status — applique un statut (TAUNT, STUN, DISABLE)
    elif etype == "apply_status":
        status_list = effects.get("apply_status") or []
        if not status_list:
            status_list = [{"status": "DISABLE"}]
        rng = int(unit.ability_range or effects.get("range", 1) or 1)
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, rng)
        if not target:
            print("     Aucun ennemi à portée pour apply_status.")
            ok = False
        else:
            for s in status_list:
                status = s.get("status", "DISABLE")
                dur = int(s.get("duration", 1) or 1)
                if status == "TAUNT":
                    # Force la cible à attaquer cette unité si elle attaque ce tour
                    if not hasattr(target, "taunted_by"):
                        target.taunted_by = []
                    target.taunted_by.append({"uid": getattr(unit, "uid", None), "duration": dur})
                    print(f"     {target.name} est provoqué : doit cibler {unit.name} s'il attaque.")
                elif status in ("STUN", "DISABLE"):
                    target.stunned = dur
                    print(f"     {target.name} est étourdi pendant {dur} tour(s).")
                else:
                    target.status_effects = getattr(target, "status_effects", {})
                    target.status_effects[status] = dur
                    print(f"     {target.name} reçoit le statut {status} ({dur} tour(s)).")
                log(f"ABILITY_STATUS {owner_char}: from={unit.name} to={target.name} status={status} dur={dur}")
            ok = True

    # 10) apply_debuff — réduit ATK ou DEF d'un ennemi temporairement
    elif etype == "apply_debuff":
        debuffs = effects.get("debuffs") or []
        if not debuffs:
            debuffs = [{"stat": "ATK", "amount": -2}]
        rng = int(unit.ability_range or effects.get("range", 1) or 1)
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, rng)
        if not target:
            print("     Aucun ennemi à portée pour apply_debuff.")
            ok = False
        else:
            for d in debuffs:
                stat = d.get("stat", "ATK")
                amount = int(d.get("amount", -2))  # négatif dans le JSON
                dur = int(d.get("duration", 1) or 1)
                amount = -abs(amount)  # force négatif
                if stat == "ATK":
                    target.atk = max(0, target.atk + amount)
                    if not hasattr(state, "temp_atk_buffs"):
                        state.temp_atk_buffs = []
                    state.temp_atk_buffs.append({"unit_uid": getattr(target, "uid", None), "amount": amount, "duration": dur})
                    print(f"     {target.name} perd {abs(amount)} ATK pendant {dur} tour(s). (ATK = {target.atk})")
                elif stat == "DEF":
                    target.temp_def += amount  # amount négatif = malus
                    print(f"     {target.name} perd {abs(amount)} DEF pendant {dur} tour(s).")
                log(f"ABILITY_DEBUFF {owner_char}: from={unit.name} to={target.name} stat={stat} amount={amount} dur={dur}")
            ok = True

    # 11) swap_positions — échange de case avec un allié adjacent
    elif etype == "swap_positions":
        allies = [
            u for u in UNITS[owner_char]
            if u is not unit and u.hp > 0 and manhattan(unit.row, unit.col, u.row, u.col) == 1
        ]
        if not allies:
            print("     Aucun allié adjacent pour l'échange de position.")
            ok = False
        else:
            target_ally = allies[0]  # IA : premier allié adjacent ; humain : idem pour l'instant
            unit.row, unit.col, target_ally.row, target_ally.col = (
                target_ally.row, target_ally.col, unit.row, unit.col
            )
            print(f"     {unit.name} et {target_ally.name} échangent leurs positions.")
            log(f"ABILITY_SWAP_POS {owner_char}: unit={unit.name} ally={target_ally.name}")
            ok = True

    # 12) terrain_like_effect — sous-catégories
    elif etype == "terrain_like_effect":
        raw_text_tle = (effects.get("raw_text") or "").lower()
        action_tags = effects.get("action_tags") or []

        # Sprint / Déplacement bonus (+1 MOVE ce tour)
        if any(w in raw_text_tle for w in ["sprint", "déplace d'1 case supplémentaire", "téléporte", "téléportation"]):
            pool_owner = get_pool_for_owner(state, owner_char)
            extra_move = 1
            if "téléport" in raw_text_tle:
                # Téléport adjacent : bonus +1 MOVE et ignore obstacles (simplifié: +1 MOVE)
                extra_move = 1
            pool_owner["MOVE"] = pool_owner.get("MOVE", 0) + extra_move
            print(f"  [TERRAIN] {unit.name} : +{extra_move} MOVE ce tour.")
            log(f"TERRAIN_LIKE_MOVE owner={owner_char} unit={unit.name} extra_move={extra_move}")
            ok = True

        # Bond (move + attack combo) — Grand Lycan Lunaire, Prédateur Nocturne
        elif any(w in raw_text_tle for w in ["bond", "chasse en meute", "se déplace de 2 cases avant"]):
            pool_owner = get_pool_for_owner(state, owner_char)
            pool_owner["MOVE"] = pool_owner.get("MOVE", 0) + 2
            pool_owner["ATK"] = pool_owner.get("ATK", 0) + 1
            print(f"  [TERRAIN] {unit.name} Bond/Chasse : +2 MOVE +1 ATK ce tour.")
            log(f"TERRAIN_LIKE_BOND owner={owner_char} unit={unit.name}")
            ok = True

        # Brume / Zone toxique (Cracheur) — place_terrain_token avec effet poison
        elif any(w in raw_text_tle for w in ["brume", "toxique", "zone de brume"]):
            rng_z = int(effects.get("range", 2) or 2)
            dur_z = int(effects.get("duration_turns", 2) or 2)
            dmg_z = int(effects.get("damage", 1) or 1)
            # Cible : choisie par le joueur si fournie, sinon auto (IA)
            if target_pos and len(target_pos) == 2:
                best_pos = (int(target_pos[0]), int(target_pos[1]))
            else:
                enemies = UNITS["B"] if owner_char == "A" else UNITS["A"]
                best_pos = None
                best_score = -999
                for rr in range(len(state.board)):
                    for cc in range(len(state.board[0])):
                        if manhattan(unit.row, unit.col, rr, cc) > rng_z:
                            continue
                        score = -min((manhattan(rr, cc, e.row, e.col) for e in enemies if e.hp > 0), default=99)
                        if score > best_score:
                            best_score = score
                            best_pos = (rr, cc)
            if best_pos:
                if not hasattr(state, "tile_effects") or state.tile_effects is None:
                    state.tile_effects = []
                state.tile_effects.append({
                    "type": "zone_damage",
                    "row": best_pos[0], "col": best_pos[1],
                    "damage": dmg_z, "duration": dur_z,
                    "ignore_def": True, "owner": owner_char, "source": unit.name,
                })
                print(f"  [TERRAIN] {unit.name} Brume Caustique en ({best_pos[0]},{best_pos[1]}) : {dmg_z} dmg/tour, {dur_z} tours.")
                log(f"TERRAIN_BRUME owner={owner_char} unit={unit.name} pos={best_pos} dmg={dmg_z} dur={dur_z}")
                ok = True
            else:
                ok = False

        # Sceau / Blocage de case — trop complexe pour l'instant, affichage propre
        elif any(w in raw_text_tle for w in ["sceau", "leurre", "pont", "barrière", "reconfiguration", "transfert de flux", "dissipation", "purge", "recyclage"]):
            raw_disp = effects.get("raw_text") or "(effet terrain)"
            print(f"  [TERRAIN] {unit.name} — {raw_disp[:100]}")
            print(f"  (Effet terrain non simulable sans plateau graphique — aucune ressource consommée.)")
            log(f"TERRAIN_LIKE_DISPLAY_ONLY owner={owner_char} unit={unit.name}")
            ok = False  # pas de commit ressource

        # Frappe ignorant DEF temporaire / ligne droite — re-map direct_damage
        elif any(w in raw_text_tle for w in ["frappe", "attaque", "tir", "inflige"]):
            target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, unit.ability_range or 2)
            if not target:
                print("     Aucun ennemi à portée.")
                ok = False
            else:
                dmg_raw = int(effects.get("damage", 0) or unit.atk)
                apply_damage_to_unit(state, target, dmg_raw, source_tag="terrain_attack", ignore_def=False, attacker=unit)
                print(f"  [TERRAIN] {unit.name} attaque {target.name} : {dmg_raw} dégâts.")
                log(f"TERRAIN_LIKE_ATK owner={owner_char} unit={unit.name} to={target.name} dmg={dmg_raw}")
                ok = True

        else:
            raw_disp = effects.get("raw_text") or "(effet terrain)"
            print(f"  [TERRAIN] {unit.name} — {raw_disp[:120]}")
            ok = False

    # 13) buff_self_if_adjacent_hq — buff DEF conditionnel si adjacent au QG
    elif etype == "buff_self_if_adjacent_hq":
        params = effects.get("action_params") or {}
        buffs = params.get("buffs") or effects.get("buffs") or []
        hq_r, hq_c = (state.hq_A_pos if owner_char == "A" else state.hq_B_pos)
        adjacent_hq = (manhattan(unit.row, unit.col, hq_r, hq_c) <= 1)
        applied = False
        for i, b in enumerate(buffs):
            stat = b.get("stat", "DEF")
            amount = int(b.get("amount", 1))
            # Le 2e buff (index 1) est le bonus conditionnel adjacent QG
            if i == 0 or adjacent_hq:
                if stat == "DEF":
                    unit.temp_def = getattr(unit, "temp_def", 0) + amount
                    state.temp_atk_buffs.append({
                        "unit_uid": getattr(unit, "uid", None),
                        "stat": "DEF",
                        "amount": amount,
                        "duration": 2,  # jusqu'à la fin du tour adverse
                    })
                elif stat == "ATK":
                    unit.atk += amount
                    state.temp_atk_buffs.append({
                        "unit_uid": getattr(unit, "uid", None),
                        "stat": "ATK",
                        "amount": amount,
                        "duration": 2,
                    })
                applied = True
        cond_label = " (adjacent QG ✓)" if adjacent_hq else " (hors QG, buff base)"
        print(f"  [ABILITÉ] {unit.name} Tenir la Ligne{cond_label}")
        log(f"ABILITY_BUFF_SELF_HQ owner={owner_char} unit={unit.name} adjacent_hq={adjacent_hq}")
        ok = applied

    # 14) buff_target_def — buff DEF sur soi ou allié adjacent (Paladin Aegis)
    elif etype == "buff_target_def":
        params = effects.get("action_params") or {}
        buffs = params.get("buffs") or effects.get("buffs") or []
        amount = int(buffs[0].get("amount", 4)) if buffs else 4
        buff_tgt_mode = params.get("buff_target") or effects.get("buff_target") or "self"
        # Chercher le meilleur allié (le moins défendu)
        allies = [u for u in (UNITS[owner_char]) if u.hp > 0 and u is not unit
                    and manhattan(unit.row, unit.col, u.row, u.col) == 1]
        if buff_tgt_mode == "self_or_adjacent_ally" and allies:
            # Préférer l'allié le plus attaqué (HP le plus bas)
            tgt = min(allies, key=lambda u: u.hp)
        else:
            tgt = unit
        tgt.temp_def = getattr(tgt, "temp_def", 0) + amount
        state.temp_atk_buffs.append({
            "unit_uid": getattr(tgt, "uid", None),
            "stat": "DEF",
            "amount": amount,
            "duration": 1,
        })
        print(f"  [ABILITÉ] {unit.name} Aegis Sacrée → {tgt.name} +{amount} DEF")
        log(f"ABILITY_BUFF_TARGET_DEF owner={owner_char} caster={unit.name} target={tgt.name} amount={amount}")
        ok = True

    # 15) swap_atk_def_for_attack — Transmutateur : inverse ATK↔DEF pour cette attaque
    elif etype == "swap_atk_def_for_attack":
        # Exécute immédiatement l'attaque avec ATK = DEF actuelle
        enemies = UNITS["B"] if owner_char == "A" else UNITS["A"]
        target = find_enemy_adjacent(owner_char, unit.row, unit.col)
        if target is None:
            target = find_enemy_in_range(owner_char, unit.row, unit.col, 1)
        if target is None:
            print(f"  [ABILITÉ] {unit.name} Transmutation — aucun ennemi adjacent.")
            ok = False
        else:
            swapped_atk = unit.defense + getattr(unit, "temp_def", 0)
            print(f"  [ABILITÉ] {unit.name} Transmutation : ATK={unit.atk}→{swapped_atk} (DEF inversée) vs {target.name}")
            log(f"ABILITY_SWAP_ATK_DEF owner={owner_char} unit={unit.name} normal_atk={unit.atk} swapped_atk={swapped_atk}")
            apply_damage_to_unit(state, target, swapped_atk, source_tag="ability_swap_atk_def", attacker=unit)
            ok = True

    # 16) passive_effect — passifs sans type d'action actif : log + no-op
    elif etype == "passive_effect":
        raw_disp = effects.get("raw_text") or unit.ability_name or "(passif)"
        print(f"  [PASSIF ACTIF] {unit.name} — {raw_disp[:100]}")
        log(f"PASSIVE_ACTIVE_NOOP owner={owner_char} unit={unit.name} ability={unit.ability_name or '?'}")
        ok = False  # Passif ne se "déclenche" pas via ability, pas de coût

    # 17) armor_break — attaque ignorant partiellement la DEF + retire le buff DEF temporaire
    elif etype == "armor_break":
        target = pre_target
        if not target:
            print("     Aucun ennemi adjacent pour armor_break.")
            ok = False
        else:
            ignore_def_amt = int(effects.get("ignore_def", 2) or 2)
            remove_temp = bool(effects.get("remove_temp_def_buff", False))
            if remove_temp and getattr(target, "temp_def", 0) > 0:
                target.temp_def = 0
                target.buff_def_duration = 0
            effective_def = max(0, (target.defense + getattr(target, "temp_def", 0)) - ignore_def_amt)
            dmg = max(1, unit.atk - effective_def)
            apply_damage_to_unit(state, target, dmg, source_tag="ability_armor_break", ignore_def=True, attacker=unit)
            label = " (buff DEF retiré)" if remove_temp else ""
            print(f"     {unit.name} Brise-Armure → {target.name} : {unit.atk} ATK - {effective_def} DEF eff. = {dmg} dmg{label}.")
            log(f"ABILITY_ARMOR_BREAK {owner_char}: from={unit.name} to={target.name} dmg={dmg} ignore_def={ignore_def_amt} remove_temp={remove_temp}")
            ok = True

    # 18) debuff_atk — inflige des dégâts + réduit l'ATK de la cible temporairement
    elif etype == "debuff_atk":
        target = pre_target
        if not target:
            print("     Aucun ennemi à portée pour debuff_atk.")
            ok = False
        else:
            debuff_cfg = effects.get("debuff") or {}
            dmg_raw = int(effects.get("damage", 0) or unit.atk)
            stat = debuff_cfg.get("stat", "ATK")
            amount = -abs(int(debuff_cfg.get("amount", -2) or -2))
            dur_raw = debuff_cfg.get("duration", 1)
            try:
                dur = int(dur_raw.split("_")[0]) if isinstance(dur_raw, str) else int(dur_raw)
            except Exception:
                dur = 1
            apply_damage_to_unit(state, target, dmg_raw, source_tag="ability_debuff_atk", attacker=unit)
            if stat == "ATK":
                target.atk = max(0, target.atk + amount)
                if not hasattr(state, "temp_atk_buffs"):
                    state.temp_atk_buffs = []
                state.temp_atk_buffs.append({"unit_uid": getattr(target, "uid", None), "amount": amount, "duration": dur})
            elif stat == "DEF":
                target.temp_def += amount
            print(f"     {unit.name} → {target.name} : {dmg_raw} dmg + {stat} {amount:+d} pendant {dur} tour(s).")
            log(f"ABILITY_DEBUFF_ATK {owner_char}: from={unit.name} to={target.name} dmg={dmg_raw} stat={stat} amount={amount} dur={dur}")
            ok = True

    # 19) execute_crit — attaque critique (ignore DEF) si la cible est sous le seuil de HP
    elif etype == "execute_crit":
        target = pre_target
        if not target:
            print("     Aucun ennemi adjacent pour execute_crit.")
            ok = False
        else:
            threshold = float(effects.get("threshold_hp_pct", 0.5) or 0.5)
            hp_max = getattr(target, "hp_max", target.hp)
            is_crit = (hp_max > 0 and target.hp < threshold * hp_max)
            if is_crit:
                apply_damage_to_unit(state, target, unit.atk, source_tag="ability_execute_crit", ignore_def=True, attacker=unit)
                print(f"     {unit.name} Frappe Mortelle CRITIQUE → {target.name} : {unit.atk} dégâts vrais.")
            else:
                eff_def = max(0, target.defense + getattr(target, "temp_def", 0))
                dmg = max(1, unit.atk - eff_def)
                apply_damage_to_unit(state, target, dmg, source_tag="ability_execute_normal", ignore_def=True, attacker=unit)
                print(f"     {unit.name} Frappe Mortelle (non-crit) → {target.name} : {dmg} dmg (cible ≥ {int(threshold*100)}% HP).")
            log(f"ABILITY_EXECUTE_CRIT {owner_char}: from={unit.name} to={target.name} crit={is_crit} threshold={threshold}")
            ok = True

    # 20) teleport — déplace un allié à portée vers une case vide adjacente au lanceur
    elif etype == "teleport":
        rng = int(unit.ability_range or effects.get("range", 3) or 3)
        allies_in_range = [
            u for u in UNITS[owner_char]
            if u is not unit and u.hp > 0 and manhattan(unit.row, unit.col, u.row, u.col) <= rng
        ]
        if not allies_in_range:
            print("     Aucun allié à portée pour le téléport.")
            ok = False
        else:
            free_adj = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                rr, cc = unit.row + dr, unit.col + dc
                if not in_bounds(state.board, rr, cc):
                    continue
                if not is_walkable_ab(state.board, rr, cc):
                    continue
                occ, _ = get_unit_at(rr, cc)
                if occ is None or occ.hp <= 0:
                    free_adj.append((rr, cc))

            if not free_adj:
                print("     Aucune case libre adjacente au lanceur.")
                ok = False
            else:
                dest = None
                if target_pos and len(target_pos) == 2:
                    cand = (int(target_pos[0]), int(target_pos[1]))
                    if cand not in free_adj:
                        print(f"     Case ({cand[0]},{cand[1]}) invalide (non adjacente ou occupée).")
                    else:
                        dest = cand
                else:
                    enemy_char = "B" if owner_char == "A" else "A"
                    enemies = [e for e in UNITS[enemy_char] if e.hp > 0]
                    if enemies:
                        dest = min(free_adj, key=lambda pos: min(manhattan(pos[0], pos[1], e.row, e.col) for e in enemies))
                    else:
                        dest = free_adj[0]

                if dest is None:
                    ok = False
                else:
                    ally = max(allies_in_range, key=lambda u: u.atk)
                    old_r, old_c = ally.row, ally.col
                    ally.row, ally.col = dest[0], dest[1]
                    print(f"     {unit.name} téléporte {ally.name} ({old_r},{old_c})→({dest[0]},{dest[1]}).")
                    log(f"ABILITY_TELEPORT {owner_char}: caster={unit.name} ally={ally.name} from=({old_r},{old_c}) to={dest}")
                    ok = True

    # 21) increase_enemy_cost — surcharge l'ennemi ciblé (+N ATK sur sa prochaine attaque)
    elif etype == "increase_enemy_cost":
        rng = int(unit.ability_range or effects.get("range", 1) or 1)
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, rng)
        if not target:
            print("     Aucun ennemi à portée pour increase_enemy_cost.")
            ok = False
        else:
            cfg = effects.get("cost_increase") or {}
            amount = int(cfg.get("amount", 2) or 2)
            target.atk_cost_surcharge = getattr(target, "atk_cost_surcharge", 0) + amount
            target.atk_cost_surcharge_dur = 1
            print(f"     {unit.name} Surcharge → {target.name} : prochaine attaque coûte +{amount} ATK.")
            log(f"ABILITY_COST_SURCHARGE {owner_char}: from={unit.name} to={target.name} amount={amount}")
            ok = True

    # 22) revive_adjacent — ressuscite un allié Lv1/Lv2 détruit avec 1 HP
    elif etype == "revive_adjacent":
        params = effects.get("action_params") or effects
        allowed_levels = list(params.get("revive_levels") or [1, 2])
        revive_hp = int(params.get("revive_hp", 1) or 1)
        dead_pool = getattr(state, "dead_pool", {})
        candidates = [
            u for u in dead_pool.get(owner_char, [])
            if getattr(u, "level", 1) in allowed_levels
        ]
        if not candidates:
            print("     Aucun allié Lv1/Lv2 détruit à ressusciter.")
            ok = False
        else:
            free_adj = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                rr, cc = unit.row + dr, unit.col + dc
                if not in_bounds(state.board, rr, cc):
                    continue
                if not is_walkable_ab(state.board, rr, cc):
                    continue
                occ, _ = get_unit_at(rr, cc)
                if occ is None or occ.hp <= 0:
                    free_adj.append((rr, cc))
            if not free_adj:
                print("     Aucune case libre adjacente pour la résurrection.")
                ok = False
            else:
                revived = candidates[0]
                dest = free_adj[0]
                revived.hp = revive_hp
                revived.row, revived.col = dest
                revived.has_moved = True
                revived.has_attacked = True
                revived.ability_uses_this_turn = revived.ability_max_per_turn
                UNITS[owner_char].append(revived)
                dead_pool[owner_char].remove(revived)
                print(f"     {unit.name} ressuscite {revived.name} en ({dest[0]},{dest[1]}) avec {revive_hp} HP (skip ce tour).")
                log(f"ABILITY_REVIVE {owner_char}: caster={unit.name} revived={revived.name} pos={dest}")
                ok = True

    # 23) confusion_redirect — l'ennemi ciblé a X% de chance d'attaquer l'unité adjacente la plus proche
    elif etype == "confusion_redirect":
        rng = int(unit.ability_range or effects.get("range", 2) or 2)
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, rng)
        if not target:
            print("     Aucun ennemi à portée pour confusion_redirect.")
            ok = False
        else:
            chance = float(effects.get("chance", 0.5) or 0.5)
            target.confusion_redirect_chance = chance
            target.confusion_redirect_dur = 1
            print(f"     {unit.name} Reflet Trompeur → {target.name} : {int(chance*100)}% chance de mésattaque.")
            log(f"ABILITY_CONFUSION {owner_char}: from={unit.name} to={target.name} chance={chance}")
            ok = True

    # 24) redirect_next_attack_to_adjacent_ally — l'ennemi doit cibler un allié adjacent (s'il en a un)
    elif etype == "redirect_next_attack_to_adjacent_ally":
        rng = int(unit.ability_range or effects.get("range", 1) or 1)
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, rng)
        if not target:
            print("     Aucun ennemi à portée pour redirect_next_attack.")
            ok = False
        else:
            target.redirect_to_ally = True
            target.redirect_to_ally_dur = 1
            print(f"     {unit.name} Redirection Mentale → {target.name} : doit cibler un allié adjacent.")
            log(f"ABILITY_REDIRECT_ALLY {owner_char}: from={unit.name} to={target.name}")
            ok = True

    # 25) random_retarget — prochaine attaque de l'ennemi ciblé = cible aléatoire
    elif etype == "random_retarget":
        rng = int(unit.ability_range or effects.get("range", 2) or 2)
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, rng)
        if not target:
            print("     Aucun ennemi à portée pour random_retarget.")
            ok = False
        else:
            target.random_retarget = True
            target.random_retarget_dur = 1
            print(f"     {unit.name} Redirection Chaotique → {target.name} : prochaine attaque aléatoire.")
            log(f"ABILITY_RANDOM_RETARGET {owner_char}: from={unit.name} to={target.name}")
            ok = True

    # 26) counter_redirect — passif : annule l'attaque reçue et redirige sur l'ennemi le plus proche
    elif etype == "counter_redirect":
        print(f"     {unit.name} Rétroaction : passif activé automatiquement à la réception d'une attaque.")
        log(f"PASSIVE_COUNTER_REDIRECT_REGISTERED {owner_char}: unit={unit.name}")
        ok = False  # Passif — ne se déclenche pas via ability manuelle

    # 27) direct_damage_ignore_def — dégâts ignorant N points de DEF (Bête de l'Abîme)
    elif etype == "direct_damage_ignore_def":
        params = unit.ability_effects or {}
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, unit.ability_range or 1)
        if not target:
            print("     Aucun ennemi à portée.")
            ok = False
        else:
            ignore_n = int(params.get("ignore_def", 4))
            orig_def = target.defense
            target.defense = max(0, target.defense - ignore_n)
            apply_damage_to_unit(state, target, unit.atk, source_tag="ability_ignore_def", attacker=unit)
            target.defense = orig_def
            print(f"     {unit.name} Assaut Primordial → {target.name} : ATK={unit.atk}, ignore {ignore_n} DEF.")
            log(f"ABILITY_IGNORE_DEF {owner_char}: from={unit.name} to={target.name} atk={unit.atk} ignore_n={ignore_n}")
            ok = True

    # 28) basic_plus_buff — attaque normale + buff DEF ce tour (Gardien Cuirassé)
    elif etype == "basic_plus_buff":
        params = unit.ability_effects or {}
        target = pre_target or find_enemy_in_range(owner_char, unit.row, unit.col, 1)
        if not target:
            print("     Aucun ennemi adjacent pour basic_plus_buff.")
            ok = False
        else:
            apply_damage_to_unit(state, target, unit.atk, source_tag="ability_basic_atk", attacker=unit)
            print(f"     {unit.name} attaque {target.name} ({unit.atk} ATK).")
            buffs = params.get("buffs") or [{"stat": "DEF", "amount": 3}]
            for b in buffs:
                stat = b.get("stat", "DEF")
                amount = int(b.get("amount", 3))
                if stat == "DEF":
                    unit.temp_def = getattr(unit, "temp_def", 0) + amount
                    unit.buff_def_duration = max(getattr(unit, "buff_def_duration", 0), 1)
                    print(f"     {unit.name} gagne +{amount} DEF ce tour.")
            log(f"ABILITY_BASIC_PLUS_BUFF {owner_char}: unit={unit.name} to={target.name}")
            ok = True

    # 29) buff_def_and_counter — +DEF + riposte gratuite à la première attaque (Garde Ancien)
    elif etype == "buff_def_and_counter":
        params = unit.ability_effects or {}
        buffs = params.get("buffs") or [{"stat": "DEF", "amount": 5}]
        for b in buffs:
            stat = b.get("stat", "DEF")
            amount = int(b.get("amount", 5))
            if stat == "DEF":
                unit.temp_def = getattr(unit, "temp_def", 0) + amount
                unit.buff_def_duration = max(getattr(unit, "buff_def_duration", 0), 1)
                print(f"     {unit.name} gagne +{amount} DEF ce tour.")
        if params.get("counter_first_attack"):
            unit.counter_first_attack = True
            print(f"     {unit.name} ripostera gratuitement à la première attaque reçue ce tour.")
        log(f"ABILITY_BUFF_DEF_COUNTER {owner_char}: unit={unit.name}")
        ok = True

    # 30) place_terrain_token — pose un jeton sur une case (Chaînes, Gaz, Brume, Portail, Ronces)
    elif etype == "place_terrain_token":
        params = unit.ability_effects or {}
        if not hasattr(state, "tile_effects") or state.tile_effects is None:
            state.tile_effects = []
        rng_t = int(params.get("range", 1) or 1)
        dur_t = int(params.get("duration_turns", 2) or 2)
        dmg_values = params.get("damage_values") or []
        dmg_t = int(dmg_values[0]) if dmg_values else 0
        debuffs_t = params.get("debuffs") or []
        if target_pos and len(target_pos) == 2:
            tok_pos = (int(target_pos[0]), int(target_pos[1]))
        else:
            enemies = UNITS["B"] if owner_char == "A" else UNITS["A"]
            tok_pos = None
            best_score = -999
            for rr in range(len(state.board)):
                for cc in range(len(state.board[0])):
                    if manhattan(unit.row, unit.col, rr, cc) > rng_t:
                        continue
                    score = -min((manhattan(rr, cc, e.row, e.col) for e in enemies if e.hp > 0), default=99)
                    if score > best_score:
                        best_score = score
                        tok_pos = (rr, cc)
        if tok_pos:
            token = {
                "type": "zone_damage" if dmg_t > 0 else "zone_debuff",
                "row": tok_pos[0], "col": tok_pos[1],
                "damage": dmg_t,
                "duration": dur_t,
                "ignore_def": True,
                "owner": owner_char,
                "source": unit.name,
            }
            if debuffs_t:
                token["debuffs"] = debuffs_t
            state.tile_effects.append(token)
            print(f"  [TOKEN] {unit.name} pose un jeton en ({tok_pos[0]},{tok_pos[1]}) : dmg={dmg_t}/tour dur={dur_t} tours debuffs={debuffs_t}.")
            log(f"TERRAIN_TOKEN owner={owner_char} unit={unit.name} pos={tok_pos} dmg={dmg_t} dur={dur_t}")
            ok = True
        else:
            ok = False

    # 31) apply_status_aura_end_game — ANCHOR permanent sur soi + alliés à portée (Sphinx Céleste)
    elif etype == "apply_status_aura_end_game":
        params = unit.ability_effects or {}
        rng_a = int(params.get("range", 1) or 1)
        allies = UNITS[owner_char]
        targets_aura = [u for u in allies if u.hp > 0 and manhattan(unit.row, unit.col, u.row, u.col) <= rng_a]
        if unit not in targets_aura:
            targets_aura.append(unit)
        for u_a in targets_aura:
            u_a.anchored = True
            u_a.anchored_permanent = True
        names = ", ".join(u_a.name for u_a in targets_aura)
        print(f"  [AURA] {unit.name} Énigme d'Immobilisation → {names} : ANCHOR permanent.")
        log(f"ABILITY_ANCHOR_AURA {owner_char}: unit={unit.name} targets={[u_a.name for u_a in targets_aura]}")
        ok = True

    # ---------------------------------------------------------------
    if not ok:
        # Aucun commit de ressources
        try:
            canon_log(
                "ABILITY_TRY",
                player=owner_char,
                unit=f"{getattr(unit,'uid','?')}:{unit.name}",
                ability=unit.ability_name,
                cap_used=0,
                cost=unit.ability_cost or {},
                result="FAIL",
                reason="apply_failed",
            )
        except Exception:
            pass
        return False

    # Commit : paiement + compteur d'utilisation
    print(f"  -> {unit.name} utilise {unit.ability_name} (coût {unit.ability_cost}).")
    if raw:
        print(f"     Effet : {raw}")
    pay_cost(pool, unit.ability_cost or {})
    unit.ability_uses_this_turn += 1

    try:
        canon_log(
            "ABILITY_TRY",
            player=owner_char,
            unit=f"{getattr(unit,'uid','?')}:{unit.name}",
            ability=unit.ability_name,
            cap_used=0,
            cost=unit.ability_cost or {},
            result="OK",
            reason="ok",
        )
    except Exception:
        pass

    return True

def _get_defender_champion_dict(state: GameState, defender_char: str) -> dict:
    """Récupère le dict champion du camp defender_char depuis l'état (robuste aux noms d'attributs)."""
    cand_attrs = []
    if defender_char == "A":
        cand_attrs = ["faction_A_info", "faction_A", "factionA_info", "factionA"]
    else:
        cand_attrs = ["faction_B_info", "faction_B", "factionB_info", "factionB"]
    for attr in cand_attrs:
        fac = getattr(state, attr, None)
        if isinstance(fac, dict):
            champ = fac.get("champion") or fac.get("champion_data") or fac.get("champ")
            if isinstance(champ, dict):
                return champ
    return {}

def on_hq_attacked(state: GameState, defender_char: str, attacker_unit: Unit):
    """Déclenche les effets défensifs liés au champion quand le QG est attaqué."""
    champ = _get_defender_champion_dict(state, defender_char)
    # Effets défensifs du champion uniquement quand le champion est DÉPLOYÉ (despair)
    try:
        st = state.champion_A_state if defender_char == 'A' else state.champion_B_state
        if st != 'deployed':
            return
    except Exception:
        # si on ne peut pas déterminer l'état, on préfère ne pas appliquer
        return

    if not champ or not attacker_unit:
        return

    # Priorité : effet_def_id + params (format structuré)
    eid = champ.get("effet_def_id") or champ.get("effet_defensif_id") or champ.get("def_effect_id")
    params = champ.get("effet_def_params") or champ.get("effet_defensif_params") or champ.get("def_effect_params") or {}
    if isinstance(params, str):
        params = {}

    # Fallback : parsing léger du texte libre (format FR)
    etxt = champ.get("effet_defensif") or champ.get("defensive_effect") or ""

    amount = None
    duration = None

    if eid == "hq_attacker_atk_down":
        try:
            amount = int(params.get("amount", 1) or 1)
            duration = int(params.get("duration", 1) or 1)
        except Exception:
            amount, duration = 1, 1
    else:
        # Exemple: "Quand une unité ennemie attaque le QG, son ATK diminue de 1 pendant 1 tour"
        m = re.search(r"attaque\s+le\s+qg.*?atk\s+diminue\s+de\s+(\d+).*?pendant\s+(\d+)\s*tour", str(etxt), flags=re.IGNORECASE)
        if m:
            try:
                amount = int(m.group(1))
                duration = int(m.group(2))
            except Exception:
                amount, duration = 1, 1

    if not amount or amount <= 0 or not duration or duration <= 0:
        return

    # Application : on baisse l'ATK direct et on restore via end_turn_tick()
    try:
        attacker_unit.atk = max(0, int(attacker_unit.atk) - int(amount))
    except Exception:
        return

    attacker_unit.atk_debuff_amount = int(getattr(attacker_unit, "atk_debuff_amount", 0) or 0) + int(amount)
    attacker_unit.atk_debuff_duration = max(int(getattr(attacker_unit, "atk_debuff_duration", 0) or 0), int(duration))

    print(f"  [EFFET DEF] Le champion {defender_char} affaiblit {attacker_unit.name}: ATK -{amount} pendant {duration} tour(s).")
    try:
        log(f"DEF_HQ_ATK_DOWN defender={defender_char} attacker={attacker_unit.name} amount={amount} duration={duration}")
    except Exception:
        pass



def resolve_attack_redirect(state, attacker, owner_char, intended_target):
    """
    Vérifie les flags de redirection sur l'attaquant avant d'appliquer un coup.
    Consomme le flag (dur = 0) si déclenché.
    Retourne (actual_target, was_redirected).
    actual_target peut être None si aucun voisin valide.
    """
    import random as _rng

    # redirect_to_ally : doit attaquer un allié adjacent (friendly fire)
    if getattr(attacker, "redirect_to_ally", False) and getattr(attacker, "redirect_to_ally_dur", 0) > 0:
        attacker.redirect_to_ally = False
        attacker.redirect_to_ally_dur = 0
        allies = [u for u in UNITS[owner_char]
                  if u is not attacker and u.hp > 0
                  and manhattan(attacker.row, attacker.col, u.row, u.col) == 1]
        if allies:
            tgt = allies[0]
            print(f"  [REDIRECT] {attacker.name} Redirection Mentale : attaque son allié {tgt.name} !")
            log(f"REDIRECT_TO_ALLY owner={owner_char} unit={attacker.name} target={tgt.name}")
            return tgt, True
        return intended_target, False

    # random_retarget : unité adjacente aléatoire (allié ou ennemi)
    if getattr(attacker, "random_retarget", False) and getattr(attacker, "random_retarget_dur", 0) > 0:
        attacker.random_retarget = False
        attacker.random_retarget_dur = 0
        all_adj = []
        for side in ("A", "B"):
            all_adj.extend([u for u in UNITS[side]
                            if u is not attacker and u.hp > 0
                            and manhattan(attacker.row, attacker.col, u.row, u.col) == 1])
        if all_adj:
            tgt = _rng.choice(all_adj)
            print(f"  [REDIRECT] {attacker.name} Redirection Chaotique : attaque {tgt.name} aléatoirement !")
            log(f"REDIRECT_RANDOM owner={owner_char} unit={attacker.name} target={tgt.name}")
            return tgt, True
        return intended_target, False

    # confusion_redirect : X% de chance d'attaquer l'unité adjacente la plus proche
    if getattr(attacker, "confusion_redirect_chance", 0) > 0 and getattr(attacker, "confusion_redirect_dur", 0) > 0:
        chance = float(attacker.confusion_redirect_chance)
        attacker.confusion_redirect_chance = 0
        attacker.confusion_redirect_dur = 0
        if _rng.random() < chance:
            all_adj = []
            for side in ("A", "B"):
                all_adj.extend([u for u in UNITS[side]
                                if u is not attacker and u.hp > 0
                                and manhattan(attacker.row, attacker.col, u.row, u.col) == 1])
            if all_adj:
                tgt = min(all_adj, key=lambda x: manhattan(attacker.row, attacker.col, x.row, x.col))
                print(f"  [REDIRECT] {attacker.name} Reflet Trompeur : attaque {tgt.name} par erreur !")
                log(f"REDIRECT_CONFUSION owner={owner_char} unit={attacker.name} target={tgt.name}")
                return tgt, True

    return intended_target, False


def get_atk_cost_surcharge(attacker) -> int:
    """Retourne le coût ATK supplémentaire si la prochaine attaque de l'unité est surchargée."""
    if getattr(attacker, "atk_cost_surcharge_dur", 0) > 0:
        return int(getattr(attacker, "atk_cost_surcharge", 0))
    return 0


def consume_atk_cost_surcharge(attacker) -> int:
    """Consomme et retourne le surcoût ATK (à déduire du pool)."""
    surcharge = get_atk_cost_surcharge(attacker)
    if surcharge:
        attacker.atk_cost_surcharge = 0
        attacker.atk_cost_surcharge_dur = 0
    return surcharge


def end_turn_tick(state: GameState):
    """
    Tick de fin de tour :
    - décrément des buffs DEF
    - décrément de la durée des pièges restants
    """
    for side in ('A', 'B'):
        for u in UNITS[side]:
            # Diminution de la durée des buffs DEF temporaires
            if getattr(u, "buff_def_duration", 0) > 0:
                u.buff_def_duration -= 1
                if u.buff_def_duration <= 0 and getattr(u, "temp_def", 0) > 0:
                    print(f"  Le buff DEF de {u.name} s'estompe.")
                    u.temp_def = 0

            # [OK] cooldown de garde
            if u.guard_cd > 0:
                u.guard_cd -= 1
            # Poison tick (dégâts directs en fin de tour de l'unité)
            if getattr(u, "poison_duration", 0) > 0 and getattr(u, "poison_stacks", 0) > 0:
                tick_dmg = int(getattr(u, "poison_damage", 1)) * int(u.poison_stacks)
                print(f"  [POISON] POISON tick sur {u.name} : -{tick_dmg} HP (stacks={u.poison_stacks})")
                log(f"POISON_TICK owner={u.owner} unit={u.name} dmg={tick_dmg} "
                    f"stacks={u.poison_stacks} dur_before={u.poison_duration}")
                apply_damage_to_unit(state, u, tick_dmg, source_tag="poison", ignore_def=True)
                u.poison_duration -= 1
                if u.poison_duration <= 0:
                    u.poison_stacks = 0
                    log(f"POISON_EXPIRE owner={u.owner} unit={u.name}")

            # ATK debuff tick / restore (ex: effet défensif du champion)
            if getattr(u, "atk_debuff_duration", 0) > 0:
                u.atk_debuff_duration -= 1
                if u.atk_debuff_duration <= 0:
                    amt = int(getattr(u, "atk_debuff_amount", 0) or 0)
                    if amt:
                        try:
                            u.atk = int(u.atk) + amt
                        except Exception:
                            pass
                    u.atk_debuff_amount = 0
                    u.atk_debuff_duration = 0

    # Reset riposte buff_def_and_counter (Protection Divine — un seul tir par activation)
    for side in ('A', 'B'):
        for u in UNITS[side]:
            if getattr(u, "counter_first_attack", False):
                u.counter_first_attack = False

    # Tick statuts comportementaux (surcharge, confusion, redirections)
    _STATUS_TICK_FIELDS = [
        ("atk_cost_surcharge_dur", "atk_cost_surcharge"),
        ("confusion_redirect_dur", "confusion_redirect_chance"),
        ("redirect_to_ally_dur",  "redirect_to_ally"),
        ("random_retarget_dur",   "random_retarget"),
    ]
    for side in ('A', 'B'):
        for u in UNITS[side]:
            for dur_field, val_field in _STATUS_TICK_FIELDS:
                dur = getattr(u, dur_field, 0)
                if dur > 0:
                    dur -= 1
                    setattr(u, dur_field, dur)
                    if dur <= 0:
                        setattr(u, val_field, 0 if "chance" in val_field or "surcharge" in val_field else False)
                        log(f"STATUS_EXPIRE owner={u.owner} unit={u.name} field={val_field}")

    # Passifs auras
    try:
        tick_aura_passives(state)
    except Exception:
        pass

    # Restore ATK buffs/debuffs temporaires (buff_self ATK, apply_debuff ATK)
    for side in ('A', 'B'):
        for u in UNITS[side]:
            if not hasattr(state, 'temp_atk_buffs'):
                break
    if hasattr(state, 'temp_atk_buffs') and state.temp_atk_buffs:
        still_active = []
        for entry in state.temp_atk_buffs:
            uid = entry.get("unit_uid")
            amount = int(entry.get("amount", 0))
            stat = entry.get("stat", "ATK")  # ATK par défaut (legacy)
            dur = int(entry.get("duration", 1)) - 1
            if dur <= 0:
                # Restaurer la stat concernée
                for side in ('A', 'B'):
                    for u in UNITS[side]:
                        if getattr(u, "uid", None) == uid:
                            if stat == "DEF":
                                u.temp_def = max(0, getattr(u, "temp_def", 0) - amount)
                                log(f"DEF_BUFF_EXPIRE uid={uid} amount={amount} def_now={u.defense}+{u.temp_def}")
                            else:
                                u.atk = max(0, u.atk - amount)
                                log(f"ATK_BUFF_EXPIRE uid={uid} amount={amount} atk_now={u.atk}")
            else:
                still_active.append({**entry, "duration": dur})
        state.temp_atk_buffs = still_active

    # Tick pièges : décrémente les durées en fin de tour
    tick_traps_end_turn(state)


def reset_units_for_new_mob_phase(owner_char: str):
    for u in UNITS[owner_char]:
        u.has_moved = False
        u.has_attacked = False
        u.ability_uses_this_turn = 0
        # Clear aussi les attributs legacy écrits par _set_moved/_set_attacked
        try: u.moved = False
        except: pass
        try: u.attacked = False
        except: pass


# ----------------------------------------------------------------------