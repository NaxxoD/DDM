"""
ddm_snapshot.py — v2
====================
Exporte l'état complet d'une partie DDM en JSON à chaque fin de tour.

Attributs réels confirmés depuis ddm_p1_core.py :
  - Faction     : state.faction_A["name"] / state.faction_B["name"]
  - Champion    : state.hero_A / state.hero_B  (dicts)
  - QG HP       : state.hq_A_hp / state.hq_B_hp
  - QG HP max   : state.hq_A_hp_max / state.hq_B_hp_max
  - QG DEF      : state.hq_A_def_base / state.hq_B_def_base
  - QG Position : HQ_POS["A"] / HQ_POS["B"]  (global de p1_core)
  - Pool        : state.pool_A / state.pool_B
  - Unités      : UNITS["A"] / UNITS["B"]  (global)
  - Faction unité : inférée depuis unit.owner -> state.faction_A/B
  - Dés         : dice_bag_A / dice_bag_B passés en paramètre
  - Log         : buffer _snapshot_log sur state, alimenté par log_append()
"""

import json
import pathlib

SNAPSHOT_DIR = pathlib.Path(__file__).parent / "snapshots"


def _ability_needs_target(u) -> bool:
    effects = getattr(u, "ability_effects", None) or {}
    etype = effects.get("type", "")
    raw = (effects.get("raw_text") or "").lower()
    if etype == "teleport":
        return True
    return any(w in raw for w in ["brume", "toxique", "zone de brume"])


def _ability_range(u) -> int:
    effects = getattr(u, "ability_effects", None) or {}
    return int(effects.get("range", 2) or 2)


# =============================================================================
# HELPERS
# =============================================================================

def _safe(obj, *attrs, default=None):
    for attr in attrs:
        try:
            val = getattr(obj, attr, None)
            if val is not None:
                return val
        except Exception:
            pass
    return default


def _serialize_unit(u, state):
    owner = _safe(u, "owner", default="?")
    if owner == "A":
        faction = (_safe(state, "faction_A") or {}).get("name", "?")
    elif owner == "B":
        faction = (_safe(state, "faction_B") or {}).get("name", "?")
    else:
        faction = "?"

    hp      = int(_safe(u, "hp",       default=0))
    hp_max  = int(_safe(u, "hp_max",   default=hp))
    defense = int(_safe(u, "defense",  default=0))
    temp_d  = int(_safe(u, "temp_def", default=0))

    return {
        "nom":         _safe(u, "name",         default="?"),
        "owner":       owner,
        "faction":     faction,
        "niveau":      int(_safe(u, "level",    default=1)),
        "is_champion": bool(_safe(u, "is_champion", default=False)),
        "lettre":      _safe(u, "champion_letter", default=""),
        "hp":          hp,
        "hp_max":      hp_max,
        "atk":         int(_safe(u, "atk",      default=0)),
        "def":         defense + temp_d,
        "def_base":    defense,
        "def_temp":    temp_d,
        "row":         _safe(u, "row",           default=-1),
        "col":         _safe(u, "col",           default=-1),
        "moved":       bool(_safe(u, "has_moved",    default=False)),
        "attacked":    bool(_safe(u, "has_attacked", default=False)),
        "stunned":        int(_safe(u, "stunned",          default=0)),
        "immovable":      bool(_safe(u, "immovable",       default=False)),
        "poison_stacks":  int(_safe(u, "poison_stacks",    default=0)),
        "poison_duration":int(_safe(u, "poison_duration",  default=0)),
        "buff_def":       int(_safe(u, "temp_def",         default=0)),
        "buff_def_dur":   int(_safe(u, "buff_def_duration",default=0)),
        "capacite":          _safe(u, "ability_name",          default=""),
        "ability_targeted":  _ability_needs_target(u),
        "cap_range":         _ability_range(u),
    }


def _serialize_hero(hero_dict, etat="?"):
    if not hero_dict or not isinstance(hero_dict, dict):
        return None
    return {
        "nom":    hero_dict.get("name",    "?"),
        "hp":     int(hero_dict.get("hp",  0)),
        "hp_max": int(hero_dict.get("hp",  0)),
        "atk":    int(hero_dict.get("atk", 0)),
        "def":    int(hero_dict.get("def", 0)),
        "faction": hero_dict.get("faction", "?"),
        "etat":   etat,
    }


def _serialize_hq(state, side):
    if side == "A":
        hp       = int(_safe(state, "hq_A_hp",       default=0))
        hp_max   = int(_safe(state, "hq_A_hp_max",   default=35))
        def_base = int(_safe(state, "hq_A_def_base", default=0))
        def_aura = int(_safe(state, "hq_A_def_aura", default=0))
        champ_st = _safe(state, "champion_A_state",  default="?")
    else:
        hp       = int(_safe(state, "hq_B_hp",       default=0))
        hp_max   = int(_safe(state, "hq_B_hp_max",   default=35))
        def_base = int(_safe(state, "hq_B_def_base", default=0))
        def_aura = int(_safe(state, "hq_B_def_aura", default=0))
        champ_st = _safe(state, "champion_B_state",  default="?")

    def_eff = def_base + (def_aura if champ_st == "dormant" else 0)

    pos = None
    try:
        from .ddm_p1_core import HQ_POS
        raw = HQ_POS.get(side)
        pos = list(raw) if raw else None
    except Exception:
        pass

    return {
        "hp":             hp,
        "hp_max":         hp_max,
        "def":            def_eff,
        "def_base":       def_base,
        "champion_state": champ_st,
        "pos":            pos,
    }


def _serialize_pool(pool_dict):
    if not pool_dict:
        return {"MOVE": 0, "ATK": 0, "DEF": 0, "CAP": 0}
    return {k: int(v) for k, v in pool_dict.items()}


def _serialize_die(d):
    return {
        "nom":     _safe(d, "name",  default="?"),
        "niveau":  int(_safe(d, "level", default=1)),
        "faces":   list(_safe(d, "faces", default=[])),
        "utilise": bool(_safe(d, "used",  default=False)),
    }


def _serialize_board(board):
    try:
        return [list(row) for row in board]
    except Exception:
        return []


# =============================================================================
# LOG BUFFER — à alimenter depuis le moteur
# =============================================================================

def log_append(state, msg: str):
    """
    Capture une ligne de log pour le snapshot.
    Appeler depuis les points clés du moteur :
        from .ddm_snapshot import log_append
        log_append(state, f"Unité X attaque Unité Y")
    """
    if not hasattr(state, "_snapshot_log"):
        state._snapshot_log = []
    state._snapshot_log.append(str(msg))


def log_clear(state):
    """Vide le buffer en début de tour."""
    state._snapshot_log = []


def _get_log(state):
    buf = getattr(state, "_snapshot_log", None)
    if buf and isinstance(buf, list):
        return [str(l) for l in buf[-40:]]
    return []


# =============================================================================
# WRITE
# =============================================================================

def write_snapshot(state, board, units_dict, turn_number: int,
                   active_player: str,
                   dice_bag_A: list = None,
                   dice_bag_B: list = None,
                   extra: dict = None):
    """
    Écrit le snapshot JSON.

    Appel depuis ddm_p4_turn.py après end_turn_tick() :
        from .ddm_snapshot import write_snapshot
        write_snapshot(state, state.board, UNITS, turn_idx, player_char,
                       dice_bag_A=dice_bag_A, dice_bag_B=dice_bag_B)
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    hero_A = _serialize_hero(
        _safe(state, "hero_A"),
        etat=_safe(state, "champion_A_state", default="?")
    )
    hero_B = _serialize_hero(
        _safe(state, "hero_B"),
        etat=_safe(state, "champion_B_state", default="?")
    )

    # Dés lancés — les deux joueurs (le renderer en a besoin pour afficher B)
    rolled_A = getattr(state, "last_rolled_A", None) or []
    rolled_B = getattr(state, "last_rolled_B", None) or []
    des_A = [_serialize_die(d) for d in rolled_A]
    des_B = [_serialize_die(d) for d in rolled_B]
    faces_A = getattr(state, "last_faces_A", None) or []
    faces_B = getattr(state, "last_faces_B", None) or []
    # Compat : "des" = joueur actif (legacy)
    des = des_A if active_player == "A" else des_B

    snapshot = {
        "tour":         int(turn_number),
        "joueur_actif": active_player,

        "joueur_A": {
            "faction":  (_safe(state, "faction_A") or {}).get("name", "?"),
            "qg":       _serialize_hq(state, "A"),
            "champion": hero_A,
            "pool":     _serialize_pool(_safe(state, "pool_A")),
            "unites":   [_serialize_unit(u, state)
                         for u in units_dict.get("A", [])
                         if getattr(u, "hp", 0) > 0],
        },

        "joueur_B": {
            "faction":  (_safe(state, "faction_B") or {}).get("name", "?"),
            "qg":       _serialize_hq(state, "B"),
            "champion": hero_B,
            "pool":     _serialize_pool(_safe(state, "pool_B")),
            "unites":   [_serialize_unit(u, state)
                         for u in units_dict.get("B", [])
                         if getattr(u, "hp", 0) > 0],
        },

        "grille": _serialize_board(board),
        "des":    des,
        "des_A":  des_A,
        "des_B":  des_B,
        "faces_A": faces_A,
        "faces_B": faces_B,
        "log":    _get_log(state),
        "log_B":  getattr(state, "last_log_B_turn", []),
        "traps":  list(_safe(state, "traps", default=[])),
        "invoc_niveau": getattr(state, "pending_invoc_level", None),
    }

    if extra:
        snapshot.update(extra)

    fname = SNAPSHOT_DIR / f"turn_{turn_number:04d}_{active_player}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    latest = SNAPSHOT_DIR / "latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    return fname


# =============================================================================
# READ — côté renderer Pygame
# =============================================================================

def read_latest_snapshot():
    latest = SNAPSHOT_DIR / "latest.json"
    if not latest.exists():
        return None
    try:
        with open(latest, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[SNAPSHOT] Erreur lecture : {e}")
        return None


def read_snapshot(turn_number, active_player):
    path = SNAPSHOT_DIR / f"turn_{turn_number:04d}_{active_player}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
