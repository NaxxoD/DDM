"""
ddm_p4_claude_api.py — Adversaire Claude via API Anthropic en direct.

Format compatible avec les autres profils LLM scriptés :
    phase_mobs_claude_api(state, owner, must_hq_fn) -> bool

Différence clé : au lieu d'une heuristique Python, on sérialise l'état du jeu,
on envoie à Claude API, on parse les actions retournées, on les applique.

Configuration via env vars :
    ANTHROPIC_API_KEY        : clé API Anthropic (obligatoire)
    DDM_CLAUDE_API_MODEL     : modèle (défaut: claude-haiku-4-5-20251001)
    DDM_CLAUDE_API_MAX_RETRY : nb de retries en cas d'erreur (défaut: 3)
    DDM_CLAUDE_API_FALLBACK  : "1" pour fallback greedy en cas d'échec (défaut: 1)

Usage typique (training Neosia phase 2 ou test gating) :
    Inscrit dans rl/ddm_env.py via _PROFILE_MAP avec tag "claude_api".
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from .ddm_p1_core import (
    GameState, UNITS, HEIGHT, WIDTH, HQ_POS,
)
from .ddm_p3_mechanics import (
    manhattan, find_enemy_adjacent, find_enemy_in_range,
    apply_damage_to_unit, use_unit_ability, get_unit_at,
    reset_units_for_new_mob_phase,
)
from .ddm_p2_board_dice import P1_TILE, P2_TILE
from .ddm_p4_ai import phase_mobs_ai


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_MODEL    = os.environ.get("DDM_CLAUDE_API_MODEL", "claude-haiku-4-5-20251001")
MAX_RETRY        = int(os.environ.get("DDM_CLAUDE_API_MAX_RETRY", "3"))
USE_FALLBACK     = os.environ.get("DDM_CLAUDE_API_FALLBACK", "1") != "0"
TIMEOUT_SECONDS  = float(os.environ.get("DDM_CLAUDE_API_TIMEOUT", "15"))

_CLIENT = None  # Lazy init du client Anthropic


def _get_client():
    """Lazy-load le client Anthropic avec la clé API depuis l'env."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY non définie. Configurer avec :\n"
            "  setx ANTHROPIC_API_KEY sk-ant-xxx  (Windows persistent)\n"
            "  $env:ANTHROPIC_API_KEY='sk-ant-xxx'  (PowerShell session)"
        )
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise RuntimeError("Package 'anthropic' non installé. → pip install anthropic") from e
    _CLIENT = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS)
    return _CLIENT


# ── Sérialisation du state pour Claude ────────────────────────────────────────

def _serialize_state(state: GameState, owner: str, must_hq_fn) -> dict:
    """State compact pour Claude. Format optimisé tokens (~70% reduction vs verbose).

    Format unit : [row, col, hp, atk, def, dist_enemy_hq, flags]
    flags = bitmask : 1=champion, 2=has_ability, 4=has_moved, 8=has_attacked
    """
    enemy = "B" if owner == "A" else "A"
    pool = state.pool_A if owner == "A" else state.pool_B
    enemy_pool = state.pool_B if owner == "A" else state.pool_A
    my_hq_r, my_hq_c = must_hq_fn(owner)
    enemy_hq_r, enemy_hq_c = must_hq_fn(enemy)

    def unit_array(u):
        flags = 0
        if getattr(u, "is_champion", False):  flags |= 1
        if getattr(u, "has_ability", False):  flags |= 2
        if getattr(u, "has_moved", False):    flags |= 4
        if getattr(u, "has_attacked", False): flags |= 8
        return [
            u.row, u.col,
            u.hp, u.atk, getattr(u, "defense", 0),
            manhattan(u.row, u.col, enemy_hq_r, enemy_hq_c),
            flags,
        ]

    my_units    = [unit_array(u) for u in UNITS[owner] if u.hp > 0]
    enemy_units = [unit_array(u) for u in UNITS[enemy] if u.hp > 0]

    return {
        "turn":  state.turn,
        "my_hp": state.hq_A_hp if owner == "A" else state.hq_B_hp,
        "en_hp": state.hq_B_hp if owner == "A" else state.hq_A_hp,
        "my_hq": [my_hq_r, my_hq_c],
        "en_hq": [enemy_hq_r, enemy_hq_c],
        "my_pool": [pool.get(k, 0) for k in ("MOVE","ATK","DEF","CAP")],
        "en_pool": [enemy_pool.get(k, 0) for k in ("MOVE","ATK","DEF","CAP")],
        "my_u":   my_units,
        "en_u":   enemy_units,
    }


# ── Prompt ─────────────────────────────────────────────────────────────────────

SONNET_PHILOSOPHY = """# Ta philosophie de jeu (référence Sonnet 4.6)

STYLE : Joue chaque tour comme un arbre de décision — priorise l'efficacité des ressources,
ne gaspille jamais un point ATK ou MOVE. Construis le sentier de façon chirurgicale pour
restreindre les options de déplacement adverse. Déclenche les abilities au moment exact où
elles maximisent leur impact, pas avant.

PRINCIPES :
- Précision et adaptabilité > plan rigide
- Évalue l'état du plateau à chaque tour, ajuste selon les ressources disponibles
- Lecture fine du jeu : comprendre ce que l'adversaire peut faire au tour suivant vaut
  souvent plus qu'une unité supplémentaire
- Punir les surextensions ennemies (advance imprudent, unité isolée à portée)
- Bloquer les lignes d'avance adverses via le placement du sentier

PRIORITÉS TACTIQUES (en ordre) :
1. Si une unité ennemie est adjacente à mon QG → priorité absolue, kill ou repousse
2. Si une de mes unités peut tuer un ennemi blessé → focus fire (action 3 ou 1)
3. Si une de mes unités est adjacente au QG ennemi → finir le tour en attaque (action 3)
4. Sinon advance (action 1) si pool MOVE dispo, vers QG ennemi

"""

SYSTEM_PROMPT = SONNET_PHILOSOPHY + """Tu joues à DDM (Dungeon Dice Monsters), un jeu tactique tour par tour sur grille 19x13.
Deux joueurs invoquent des unités via des dés et cherchent à détruire le QG adverse (~35 HP).

# Mécaniques clés

## Pool de ressources (dés, par tour)
- ATK : points pour frapper unités/QG (1 par attaque)
- MOVE : points pour déplacer unités (1 par case)
- CAP : points pour utiliser abilities (coût variable selon ability)
- DEF : valeur défensive
- STAR : invocations (géré automatiquement avant le mob phase)

## Plateau
Le terrain se construit au fil des invocations (shapes posées). Early game = sentier étroit.
Mid/late game = plateau large, flancs possibles. Les unités ne peuvent se déplacer que sur le
sentier de leur faction ou cases neutres.

## Champion
Entre en jeu en condition critique. Ability unique selon faction.

# Les 8 factions et leurs archétypes

| ID | Faction | Archétype |
|---|---|---|
| 1 | Humains — Citadelles du Nexus | Défensif, positionnel, bastion, attrition |
| 2 | Démons — Conclave Abyssal | Agressif, drain, brutalité isolée |
| 3 | Reptiliens — Légions Scailles-Feu | Contrôle de zone, venin, poke progressif |
| 4 | Cyborgs — Système Oméga | Calculé, technique, précision, optimisation |
| 5 | Orcs — Clans Fer & Fureur | Rush, mêlée brute, tout ou rien |
| 6 | Lycans — Meutes Lunaires | Mobilité, flanc, meute, débordement |
| 7 | Égyptiens — Dynasties Solaires | Réactif, late game, montée en puissance |
| 8 | Abominations — Fractaux Oniriques | Chaos, illusion, redirection, imprévisible |

# Heuristiques de jeu observées (top players)

- **Mate threat** : unité adjacente au QG ennemi = priorité absolue de protection (côté défense)
  ou de finition (côté offense)
- **Kill shot** : finir une unité ennemie blessée < laisser une unité full HP — focus fire paie
- **Préserver pool ATK** : action 3 (attack only) économise MOVE, utile en zone dense
- **Tempo abilities** : utiliser CAP tôt si avantage tactique > économiser pour la fin
- **Advance first** : si tour ouvert sans menace immédiate, action 1 (advance) accélère le push
- **Champion timing** : si le QG est sous 15 HP, le champion entre — c'est le pic de menace

# Format du state (envoyé à chaque tour, JSON compact)

- turn : numéro de tour courant
- my_hp / en_hp : HP de ton QG / QG ennemi (max 35)
- my_hq / en_hq : [row, col] des QG (le tien et l'ennemi)
- my_pool / en_pool : [MOVE, ATK, DEF, CAP] dés disponibles ce tour
- my_u / en_u : liste d'unités vivantes, chaque unité = [row, col, hp, atk, def, dist_to_en_hq, flags]
  flags bitmask : 1=is_champion, 2=has_ability_dispo, 4=has_moved_ce_tour, 8=has_attacked_ce_tour

# Actions possibles par unité (1 chiffre par unité de my_u)

| Code | Action | Effet |
|---|---|---|
| 0 | pass | Ne rien faire ce tour |
| 1 | advance | Avancer vers QG ennemi, attaque si adjacent |
| 2 | hunt | Chasser unité ennemie la plus proche, attaque si adjacent |
| 3 | attack | Attaquer adjacent sans bouger (économise MOVE) |
| 4 | ability | Utiliser capacité spéciale (si flags & 2 = ability dispo) |

# Format de réponse OBLIGATOIRE

Réponds UNIQUEMENT par JSON valide, aucun texte autour, aucun commentaire :
  {"actions": [<int>, <int>, ...]}

Une action par unité de my_u, dans l'ordre. Si tu as 5 unités, retourne 5 entiers.
Pas plus, pas moins. Pas de texte hors du JSON."""


def _build_user_message(state_dict: dict) -> str:
    """Construit le message utilisateur avec le state."""
    return (
        "Voici l'état du jeu pour ton tour :\n"
        f"```json\n{json.dumps(state_dict, ensure_ascii=False)}\n```\n\n"
        f"Réponds avec {{\"actions\": [...]}} de longueur {len(state_dict['my_u'])}."
    )


# ── Parsing de la réponse ─────────────────────────────────────────────────────

def _parse_actions(response_text: str, n_units: int) -> Optional[list[int]]:
    """Extrait la liste d'actions du JSON retourné par Claude.
    Retourne None si parsing échoue ou format invalide.
    """
    try:
        # Claude peut wrapper le JSON dans ```json ... ``` ou retourner direct
        text = response_text.strip()
        if "```" in text:
            # Extraire le bloc entre ```
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break
        data = json.loads(text)
        actions = data.get("actions", [])
        if not isinstance(actions, list):
            return None
        # Tronquer / pad à n_units
        actions = [int(a) for a in actions[:n_units]]
        while len(actions) < n_units:
            actions.append(0)
        # Clamper à [0, 4]
        actions = [max(0, min(4, a)) for a in actions]
        return actions
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


# ── Appel API ──────────────────────────────────────────────────────────────────

def _query_claude(state_dict: dict) -> Optional[list[int]]:
    """Envoie le state à Claude et récupère les actions. None si échec."""
    n_units = len(state_dict["my_u"])
    if n_units == 0:
        return []

    client = _get_client()
    user_msg = _build_user_message(state_dict)

    for attempt in range(MAX_RETRY):
        try:
            resp = client.messages.create(
                model       = DEFAULT_MODEL,
                max_tokens  = 64,   # actions = liste courte d'ints, pas besoin de 256
                # Prompt caching : le system prompt est invariant → cache 5 min TTL
                # Sur cache hit (calls suivants), l'input est facturé 10% et ne compte
                # que partiellement vers le rate limit ITPM.
                system      = [{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages    = [{"role": "user", "content": user_msg}],
            )
            # Extraire le texte (1 seul bloc text attendu)
            text_blocks = [b.text for b in resp.content if hasattr(b, "text")]
            text = "".join(text_blocks).strip()
            actions = _parse_actions(text, n_units)
            if actions is not None:
                return actions
            # Parse failed, retry
        except Exception as e:
            print(f"[claude_api] attempt {attempt+1}/{MAX_RETRY} échec: {type(e).__name__}: {e}")
            time.sleep(0.5 * (attempt + 1))
    return None


# ── Application des actions au state ──────────────────────────────────────────

_CAND_STEPS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def _step_unit_toward(unit, target_r: int, target_c: int, board) -> bool:
    """Bouge l'unité d'une case vers (target_r, target_c). Retourne True si bouge."""
    dr = target_r - unit.row
    dc = target_c - unit.col
    if dr == 0 and dc == 0:
        return False
    if abs(dr) >= abs(dc):
        primary   = (unit.row + (1 if dr > 0 else -1), unit.col)
        secondary = (unit.row, unit.col + (1 if dc > 0 else (-1 if dc < 0 else 0)))
    else:
        primary   = (unit.row, unit.col + (1 if dc > 0 else -1))
        secondary = (unit.row + (1 if dr > 0 else (-1 if dr < 0 else 0)), unit.col)

    for nr, nc in (primary, secondary):
        if not (0 <= nr < HEIGHT and 0 <= nc < WIDTH):
            continue
        # Pas sur QG
        from .ddm_p2_board_dice import P1_QG, P2_QG
        cell = board[nr][nc]
        if cell in (P1_QG, P2_QG):
            continue
        occupant, _ = get_unit_at(nr, nc)
        if occupant is None:
            unit.row, unit.col = nr, nc
            return True
    return False


def _try_attack(unit, state, pool, owner, enemy):
    """Essaie d'attaquer une cible adjacente (unité ennemie ou QG)."""
    if pool.get("ATK", 0) <= 0:
        return
    adj = find_enemy_adjacent(owner, unit.row, unit.col)
    if adj and getattr(adj, "hp", 0) > 0:
        apply_damage_to_unit(state, adj, unit.atk, source_tag=f"claude_api_{owner}")
        pool["ATK"] = max(0, pool.get("ATK", 0) - 1)
        return
    enemy_hq = HQ_POS.get(enemy)
    if enemy_hq and manhattan(unit.row, unit.col, enemy_hq[0], enemy_hq[1]) == 1:
        state.damage_hq(enemy, unit.atk, tag=f"claude_api_{owner}",
                        attacker_pos=(unit.row, unit.col))
        pool["ATK"] = max(0, pool.get("ATK", 0) - 1)


def _exec_action(action: int, unit, state, pool, owner: str, enemy: str,
                 enemy_hq: tuple):
    """Applique une action (0-4) sur une unité. Identique à DDMEnv._exec_cmd."""
    if action == 0:  # pass
        return
    if action == 3:  # attack only
        if not unit.has_attacked:
            _try_attack(unit, state, pool, owner, enemy)
            unit.has_attacked = True
        return
    if action == 4:  # ability
        if not unit.has_attacked and getattr(unit, "has_ability", False):
            try:
                if use_unit_ability(state, unit, owner):
                    unit.ability_uses_this_turn = getattr(unit, "ability_uses_this_turn", 0) + 1
            except Exception:
                pass
        return
    # action 1 (advance) ou 2 (hunt)
    if action == 1:
        target = enemy_hq
    else:  # action == 2
        nearest = find_enemy_in_range(owner, unit.row, unit.col, rng=HEIGHT + WIDTH)
        target = (nearest.row, nearest.col) if nearest else enemy_hq

    if not unit.has_moved:
        move_pts = int(pool.get("MOVE", 0))
        for _ in range(move_pts):
            if not _step_unit_toward(unit, target[0], target[1], state.board):
                break
            pool["MOVE"] = max(0, pool.get("MOVE", 0) - 1)
        unit.has_moved = True

    if not unit.has_attacked:
        _try_attack(unit, state, pool, owner, enemy)
        unit.has_attacked = True


# ── Phase mobs principale ──────────────────────────────────────────────────────

def phase_mobs_claude_api(state: GameState, owner: str, must_hq_fn) -> bool:
    """Phase unités via API Claude. Compatible avec dispatch _PROFILE_FNS.

    Retourne True (continue) systématiquement. Si l'API échoue et fallback activé,
    bascule sur phase_mobs_ai (greedy) pour ne pas bloquer l'épisode.
    """
    units = [u for u in UNITS[owner] if u.hp > 0]
    if not units:
        return True

    pool = state.pool_A if owner == "A" else state.pool_B
    if pool.get("MOVE", 0) <= 0 and pool.get("ATK", 0) <= 0:
        return True

    reset_units_for_new_mob_phase(owner)

    # Despair champion (cohérence avec autres phase_mobs)
    try:
        from .ddm_p4_human import (
            maybe_trigger_despair_champion,
            maybe_trigger_despair_champion_A,
        )
        if owner == "A":
            maybe_trigger_despair_champion_A(state, "A", must_hq_fn)
        else:
            maybe_trigger_despair_champion(state, "B", must_hq_fn)
    except Exception:
        pass

    # Sérialiser state + appel API
    state_dict = _serialize_state(state, owner, must_hq_fn)
    actions = _query_claude(state_dict)

    if actions is None:
        if USE_FALLBACK:
            print(f"[claude_api {owner}] échec API → fallback greedy")
            return phase_mobs_ai(state, owner, must_hq_fn)
        return True  # ne fait rien ce tour

    enemy = "B" if owner == "A" else "A"
    enemy_hq = must_hq_fn(enemy)

    # Appliquer les actions sur les units (même ordre que sérialisation)
    for action, unit in zip(actions, units):
        _exec_action(int(action), unit, state, pool, owner, enemy, enemy_hq)

    return True
