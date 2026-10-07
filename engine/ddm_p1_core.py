

from __future__ import annotations
import random
import os
import sys
import re
from datetime import datetime
import json 
from pathlib import Path
from dataclasses import dataclass

STATE_FILE = Path("ddm_panel_state.json")


def update_panel(faction, champion_file, mob_file):
    """
    faction       : "demons", "humains", "reptiliens", etc.
    champion_file : nom du png du champion (dans le sous-dossier)
    mob_file      : nom du png du mob (dans le sous-dossier)
    """
    data = {
        "faction": faction,
        "champion_file": champion_file,
        "mob_file": mob_file,
    }
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f)


# ----------------------------------------------------------------------
#  CONFIG CHEMINS & LOGGER
# ----------------------------------------------------------------------

# Mode de test : si True, Joueur A est aussi piloté par l'IA.
AI_VS_AI_MODE = False  # True pour lancer des runs IA vs IA

# --- root detection (portable) ---
_THIS_DIR = Path(__file__).resolve().parent

def _detect_project_root() -> Path:
    """Best-effort project root detection (Proto_DDM)."""
    env = os.environ.get("DDM_ROOT", "").strip()
    if env:
        try:
            p = Path(env).expanduser().resolve()
            if (p / "engine").is_dir():
                return p
            if p.name.lower() == "engine":
                return p.parent
            if (p / "data" / "Data_8_Factions.json").exists() or (p / "logs").exists():
                return p
        except Exception:
            pass
    if _THIS_DIR.name.lower() == "engine":
        return _THIS_DIR.parent
    return _THIS_DIR

PROJECT_ROOT = Path(os.environ.get("DDM_PROJECT_ROOT", str(_detect_project_root()))).resolve()
ENGINE_DIR = PROJECT_ROOT / "engine" if (PROJECT_ROOT / "engine").is_dir() else _THIS_DIR
DDM_ROOT = ENGINE_DIR.resolve()

def _first_existing(*cands: Path) -> Path:
    for c in cands:
        try:
            if c.exists():
                return c
        except Exception:
            pass
    return cands[0] if cands else Path(".")

# --- log family routing (avoid mixing HvIA vs AutoRuns) ---
_family = (os.environ.get("DDM_LOG_FAMILY") or ("autorun" if os.environ.get("DDM_AUTORUN", "0") == "1" else "hvia")).strip().lower()
_base_logs = PROJECT_ROOT / "logs" / ("autorun_log_data" if _family in ("autorun", "iaia", "auto") else "log_data")

# Canonical paths (overrideable via env)
LOG_DIR = os.environ.get("DDM_LOG_DIR", str(_base_logs / "log"))
STDOUT_DIR = os.environ.get("DDM_STDOUT_DIR", str(_base_logs / "stdout"))
STDOUT_FILE = None
_STDOUT_TEE = None

# Canonical data paths (prefer Proto_DDM/data/)
FACTIONS_JSON_PATH = os.environ.get("DDM_FACTIONS_JSON", str(_first_existing(
    PROJECT_ROOT / "data" / "Data_8_Factions.json",
    ENGINE_DIR / "Data_8_Factions.json",
    PROJECT_ROOT / "Data_8_Factions.json",
)))
FACTION_STATS_PATH = os.environ.get("DDM_FACTION_STATS", str(_first_existing(
    PROJECT_ROOT / "data" / "faction_stats.json",
    ENGINE_DIR / "data" / "faction_stats.json",
    ENGINE_DIR / "faction_stats.json",
    PROJECT_ROOT / "faction_stats.json",
)))
REWORK_JSON_PATH = os.environ.get("DDM_REWORK_JSON", str(_first_existing(
    PROJECT_ROOT / "data" / "Data_Rework.json",
    ENGINE_DIR / "Data_Rework.json",
    PROJECT_ROOT / "Data_Rework.json",
)))

LOG_FILE = None
REWORK_UNITS_BY_FACTION: dict[str, dict[int, list[dict]]] = {}


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def _tee_write(streams, data: str):
    for s in streams:
        if s is None:
            continue
        try:
            s.write(data)
        except Exception:
            pass


class _TeeStream:
    """Duplique stdout/stderr vers plusieurs flux (console + fichier)."""
    def __init__(self, *streams):
        self.streams = list(streams)
    def write(self, data):
        _tee_write(self.streams, data)
        return len(data)
    def flush(self):
        for s in self.streams:
            if s is None:
                continue
            try:
                s.flush()
            except Exception:
                pass
    def isatty(self):
        # Rend certains CLI plus confortables sur Windows
        try:
            return any(getattr(s, 'isatty', lambda: False)() for s in self.streams if s is not None)
        except Exception:
            return False


def init_logger():
    global LOG_FILE, LOG_DIR, STDOUT_DIR, STDOUT_FILE, _STDOUT_TEE
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs(STDOUT_DIR, exist_ok=True)
        ts = os.environ.get('RUN_ID') or os.environ.get('DDM_RUN_ID') or datetime.now().strftime('%Y%m%d_%H%M%S')
        LOG_FILE = os.path.join(LOG_DIR, f'run_{ts}.log')
        STDOUT_FILE = os.path.join(STDOUT_DIR, f'stdout_{ts}.txt')
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f'# Proto_DDM run {ts}\n')

        # Tee stdout/stderr -> fichier (par défaut ON ; DDM_CAPTURE_STDOUT=0 pour couper)
        capture = os.environ.get('DDM_CAPTURE_STDOUT', '1') != '0'
        if capture:
            f_out = open(STDOUT_FILE, 'w', encoding='utf-8', buffering=1)
            _STDOUT_TEE = _TeeStream(sys.stdout, f_out)
            sys.stdout = _STDOUT_TEE
            sys.stderr = _TeeStream(sys.stderr, f_out)

        print(f'[LOG] Fichier créé : {LOG_FILE}')
        if capture:
            print(f'[STDOUT] Capture : {STDOUT_FILE}')
    except Exception as e:
        # Fallback portable si le chemin Windows n'existe pas (ou n'est pas monté)
        try:
            base = PROJECT_ROOT / "logs" / ("autorun_log_data" if _family in ("autorun", "iaia", "auto") else "log_data")
            LOG_DIR = str(base / "log")
            STDOUT_DIR = str(base / "stdout")
            os.makedirs(LOG_DIR, exist_ok=True)
            os.makedirs(STDOUT_DIR, exist_ok=True)
            ts = os.environ.get('RUN_ID') or os.environ.get('DDM_RUN_ID') or datetime.now().strftime('%Y%m%d_%H%M%S')
            LOG_FILE = os.path.join(LOG_DIR, f'run_{ts}.log')
            STDOUT_FILE = os.path.join(STDOUT_DIR, f'stdout_{ts}.txt')
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.write(f'# Proto_DDM run {ts}\n')
            capture = os.environ.get('DDM_CAPTURE_STDOUT', '1') != '0'
            if capture:
                f_out = open(STDOUT_FILE, 'w', encoding='utf-8', buffering=1)
                _STDOUT_TEE = _TeeStream(sys.stdout, f_out)
                sys.stdout = _STDOUT_TEE
                sys.stderr = _TeeStream(sys.stderr, f_out)
            print(f'[LOG] Fichier créé (fallback) : {LOG_FILE}')
            if capture:
                print(f'[STDOUT] Capture (fallback) : {STDOUT_FILE}')
        except Exception:
            LOG_FILE = None
            STDOUT_FILE = None
            print(f'[LOG] Logger désactivé ({e})')
init_logger()

def log(msg: str):
    if LOG_FILE is None:
        return
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(msg + "\n")
    except Exception as e:
        print(f"[LOG] Erreur écriture : {e}")


def _json_compact(obj) -> str:
    """Compact JSON (no spaces) for canon logs."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def canon_log(tag: str, **kv) -> None:
    """Canon log format: TAG key=value ... with JSON for structured values."""
    mode = os.environ.get("DDM_LOG_CANON", "MIN").upper()
    if mode == "OFF":
        return
    if mode == "MIN":
        allowed = {"RUN_START","PICK","TURN_START","TURN_END","GAME_END","SUMMARY_END","CRASH_END"}
        if tag not in allowed:
            return
    parts = [tag]
    for k,v in kv.items():
        if v is None:
            continue
        if isinstance(v, (dict, list, tuple)):
            parts.append(f"{k}={_json_compact(v)}")
        else:
            parts.append(f"{k}={v}")
    log(" ".join(parts))


# ----------------------------------------------------------------------
#  PLATEAU & CONSTANTES
# ----------------------------------------------------------------------

WIDTH, HEIGHT = 13, 19  # 13 de large, 19 de haut

EMPTY = '.'
P1_QG = 'A'
P2_QG = 'B'
P1_TILE = 'a'
P2_TILE = 'b'

UNITS = {'A': [], 'B': []}
HQ_POS = {'A': None, 'B': None}

COST_KEYS = ("ATK", "MOVE", "DEF", "CAP")
# ----------------------------------------------------------------------
#  FACTIONS.JSON + STATS IA + PROFILS IA
# ----------------------------------------------------------------------

FACTIONS_DATA = []


def load_factions_data(path: str = FACTIONS_JSON_PATH):
    global FACTIONS_DATA
    tried = []
    candidates = [path]

    # fallback si le fichier canon n'existe pas / ancien nom dans certains patchs
    if path == FACTIONS_JSON_PATH:
        candidates += [
                        os.path.join(os.path.dirname(__file__), 'Data_8_Factions.json'),
            os.path.join(os.getcwd(), 'Data_8_Factions.json'),
        ]

    last_err = None
    for p in candidates:
        if p in tried:
            continue
        tried.append(p)
        try:
            with open(p, encoding='utf-8') as f:
                raw = json.load(f)
            FACTIONS_DATA = raw.get('factions', [])
            print(f"[FACTIONS] {len(FACTIONS_DATA)} factions chargées ({p}).")
            return
        except Exception as e:
            last_err = e

    print(f"[FACTIONS] Impossible de charger factions (essais={tried}) : {last_err}")
    FACTIONS_DATA = []

def load_rework_units(path: str = REWORK_JSON_PATH):
    """
    Charge les unités supplémentaires depuis Data_Rework.json
    et remplit REWORK_UNITS_BY_FACTION[name][level] = [units...].
    """
    global REWORK_UNITS_BY_FACTION
    REWORK_UNITS_BY_FACTION = {}

    if not os.path.exists(path):
        print(f"[REWORK] Fichier absent : {path}")
        return

    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        factions = raw.get("factions", [])
        for entry in factions:
            # Certaines entrées du JSON dérivé sont directement des unités : on les ignore
            if not isinstance(entry, dict) or "faction" not in entry or "unites" not in entry:
                continue

            name = entry["faction"]
            level_map: dict[int, list[dict]] = {}
            for u in entry.get("unites", []):
                lvl = u.get("niveau")
                if not isinstance(lvl, int):
                    # ligne ignorée : unité sans 'niveau' entier
                    continue
                level_map.setdefault(lvl, []).append(u)

            REWORK_UNITS_BY_FACTION[name] = level_map

        print(f"[REWORK] {len(REWORK_UNITS_BY_FACTION)} factions rework chargées.")
    except Exception as e:
        print(f"[REWORK] Impossible de charger {path} : {e}")
        REWORK_UNITS_BY_FACTION = {}

def extend_faction_units_with_rework(faction_info: dict, use_rework: bool) -> None:
    """
    Si use_rework=True, fusionne les unités de Data_Rework dans
    faction_info['units_by_level'] pour cette faction.
    """
    if not use_rework:
        return

    fac_name = faction_info.get("name") or faction_info.get("nom")
    if not fac_name:
        return

    extra = REWORK_UNITS_BY_FACTION.get(fac_name)
    if not extra:
        print(f"[REWORK] Aucune unité étendue pour {fac_name}.")
        return

    units_by_level = faction_info.setdefault("units_by_level", {})

    for lvl, lst in extra.items():
        if not isinstance(lvl, int):
            continue
        units_by_level.setdefault(lvl, []).extend(lst)

    print(f"[REWORK] Unités étendues fusionnées pour {fac_name}.")

def load_faction_stats():
    if not os.path.exists(FACTION_STATS_PATH):
        return {}
    try:
        with open(FACTION_STATS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def record_ai_pick(fid: int):
    # Tracking migré vers DDMStatsTracker (ddm_p4_stats.py / schema v2).
    # Cette fonction est conservée pour compatibilité d'appel mais ne fait rien.
    pass


def build_default_ai_profile(name: str | None = None) -> dict:
    """
    Profil IA de base, avec variations selon le nom de faction.
    """
    base = {
        "style": "balanced",
        "aggro_weight": 1.0,
        "block_weight": 1.0,
        "trap_usage": 0.5,
        "def_usage": 0.5,
        "despair_threshold": 0.45,
        "target_win_turn_min": 35,
        "target_win_turn_max": 45,
        "urgency_state_w": 0.25,   # réactivité à l'état du QG adverse
        "urgency_tempo_w": 0.20,   # réactivité à la durée / pression reçue
    }

    if not name:
        return base

    lname = name.lower()

    # --- Démons : push HQ, peu de back défense ---
    if "démon" in lname or "demon" in lname or "abyss" in lname:
        base.update({
            "style": "aggressive",
            "aggro_weight": 1.5,
            "block_weight": 0.7,
            "trap_usage": 0.4,
            "def_usage": 0.3,
            "target_win_turn_min": 30,
            "target_win_turn_max": 38,
            "urgency_state_w": 0.35,
            "urgency_tempo_w": 0.40,
            "pathfinding_mode": "aggressive",  # Dijkstra→A*→Greedy
        })

    # --- Égypte / Sphinx : bulwark défensif ---
    elif "égypte" in lname or "egypte" in lname or "sphinx" in lname or "solaire" in lname:
        base.update({
            "style": "bulwark",
            "aggro_weight": 0.85,
            "block_weight": 1.5,
            "trap_usage": 0.7,
            "def_usage": 1.1,
            "target_win_turn_min": 40,
            "target_win_turn_max": 55,
            "urgency_state_w": 0.10,   # base faible — mais variable selon état QG adverse
            "urgency_tempo_w": 0.05,
            "egypt_trigger": True,     # active la logique variable : state/tempo x3 si QG < 30%
            "pathfinding_mode": "defensive",   # Dijkstra→Dijkstra→A*
        })

    # --- Lycans : mobile / contre-attaque ---
    elif "lycan" in lname or "loup" in lname or "meutes lunaires" in lname:
        base.update({
            "style": "mobile",
            "aggro_weight": 1.2,
            "block_weight": 0.9,
            "trap_usage": 0.5,
            "def_usage": 0.5,
            "urgency_state_w": 0.45,
            "urgency_tempo_w": 0.10,
            "pathfinding_mode": "aggressive",  # Dijkstra→A*→Greedy
        })

    # --- Reptiliens : pièges / contrôle ---
    elif "reptil" in lname or "serpent" in lname or "vipère" in lname:
        base.update({
            "style": "traps",
            "aggro_weight": 0.9,
            "block_weight": 1.2,
            "trap_usage": 0.9,
            "def_usage": 0.6,
            "urgency_state_w": 0.22,   # +0.07 : opportunisme prédateur sur cible exposée
            "urgency_tempo_w": 0.10,
            "dynamic_aggro": True,     # active le boost via aggro_seq mémoire inter-tours
            "pathfinding_mode": "defensive",   # Dijkstra→Dijkstra→A*
        })

    # --- Humains : vrai balanced ---
    elif "humain" in lname or "citadelles" in lname:
        base.update({
            "style": "balanced",
            "aggro_weight": 1.0,
            "block_weight": 1.0,
            "trap_usage": 0.6,
            "def_usage": 0.7,
            "pathfinding_mode": "balanced",    # Dijkstra→A*→A*
        })

    # --- Orcs : très agressifs mais pas suicidaires ---
    elif "orc" in lname or "fureur" in lname:
        base.update({
            "style": "aggressive",
            "aggro_weight": 1.4,
            "block_weight": 0.85,
            "trap_usage": 0.4,
            "def_usage": 0.4,
            "urgency_state_w": 0.40,
            "urgency_tempo_w": 0.25,
            "pathfinding_mode": "aggressive",  # Dijkstra→A*→Greedy
        })

    # --- Cyborgs & Fractaux : contrôle / traps ---
    elif "cyborg" in lname or "oméga" in lname or "omega" in lname:
        base.update({
            "style": "control",
            "aggro_weight": 1.0,
            "block_weight": 1.1,
            "trap_usage": 0.7,
            "def_usage": 0.8,
            "urgency_state_w": 0.25,   # +0.05 : réactivité opportuniste sur QG exposé
            "urgency_tempo_w": 0.15,
            "pathfinding_mode": "balanced",    # Dijkstra→A*→A*
        })
    elif "abomination" in lname or "fractaux" in lname or "oniriques" in lname:
        base.update({
            "style": "weird",
            "aggro_weight": 1.0,
            "block_weight": 1.0,
            "trap_usage": 0.8,
            "def_usage": 0.7,
            "urgency_state_w": 0.30,
            "urgency_tempo_w": 0.30,
            "pathfinding_mode": "balanced",    # Dijkstra→A*→A*
        })

    return base


def apply_champion_modifier(profile: dict, faction_name: str, champion_letter: str) -> dict:
    """
    Applique les deltas urgency_state / urgency_tempo selon le champion joué.
    Retourne un nouveau profil (ne modifie pas l'original).
    """
    p = dict(profile)  # copie shallow
    lname = (faction_name or "").lower()
    letter = (champion_letter or "A").upper()

    # ─── Humains ───────────────────────────────────────────────
    if "humain" in lname or "citadelles" in lname:
        deltas = {"A": (-0.10, -0.08), "B": (-0.05, -0.05),
                  "C": (+0.10, +0.08), "D": (+0.08, +0.05), "E": (+0.05, +0.10)}
    # ─── Démons ────────────────────────────────────────────────
    elif "démon" in lname or "demon" in lname or "abyss" in lname:
        deltas = {"A": (+0.10, +0.05), "B": (-0.10, +0.05),
                  "C": (+0.08, +0.08), "D": (+0.12,  0.00), "E": (-0.15, -0.10)}
    # ─── Reptiliens ────────────────────────────────────────────
    elif "reptil" in lname or "serpent" in lname or "scaille" in lname:
        deltas = {"A": (+0.10, +0.05), "B": (+0.05,  0.00),
                  "C": (-0.05, -0.05), "D": (+0.08, +0.05), "E": (+0.12, +0.05)}
    # ─── Cyborgs ───────────────────────────────────────────────
    elif "cyborg" in lname or "oméga" in lname or "omega" in lname:
        deltas = {"A": (+0.05,  0.00), "B": (-0.05, -0.05),
                  "C": (+0.08, +0.05), "D": (-0.10, -0.05), "E": (+0.15, +0.10)}
    # ─── Orcs ──────────────────────────────────────────────────
    elif "orc" in lname or "fureur" in lname:
        deltas = {"A": (+0.08, +0.10), "B": (-0.05, +0.05),
                  "C": (+0.10, +0.08), "D": (-0.05, +0.08), "E": (+0.05, +0.05)}
    # ─── Lycans ────────────────────────────────────────────────
    elif "lycan" in lname or "loup" in lname or "lunaire" in lname:
        deltas = {"A": (+0.08, +0.05), "B": (+0.12,  0.00),
                  "C": (-0.15, +0.05), "D": (+0.05, +0.05), "E": (-0.20,  0.00)}
    # ─── Égypte ────────────────────────────────────────────────
    elif "égypte" in lname or "egypte" in lname or "solaire" in lname:
        deltas = {"A": (-0.05,  0.00), "B": ( 0.00,  0.00),
                  "C": (+0.08, +0.05), "D": (+0.15, +0.08), "E": (-0.05,  0.00)}
    # ─── Abominations ──────────────────────────────────────────
    elif "abomination" in lname or "fractaux" in lname or "onirique" in lname:
        # Logique variable — les deltas modifient les seuils, pas les poids
        abom_mods = {"A": "rng_threshold", "B": "reduce_state",
                     "C": "amplify_peaks",  "D": "redirect_trigger", "E": "boost_state"}
        p["abom_champion_mod"] = abom_mods.get(letter, "none")
        return p
    else:
        return p  # faction inconnue — profil inchangé

    ds, dt = deltas.get(letter, (0.0, 0.0))
    p["urgency_state_w"] = round(p.get("urgency_state_w", 0.25) + ds, 3)
    p["urgency_tempo_w"] = round(p.get("urgency_tempo_w", 0.20) + dt, 3)
    return p

def get_game_phase(state: "GameState", profile: dict) -> str:
    """
    Retourne 'early' / 'mid' / 'late' / 'overtime' en fonction du tour
    et de la fenêtre cible de victoire définie dans le profil IA.
    """
    t = max(state.turn, 1)
    t_min = profile.get("target_win_turn_min", 35)
    t_max = profile.get("target_win_turn_max", 40)

    if t < t_min * 0.6:
        return "early"
    elif t < t_min:
        return "mid"
    elif t <= t_max:
        return "late"
    else:
        return "overtime"



# ----------------------------------------------------------------------
#  HELPERS CHAMPIONS DYNAMIQUES (A/B/C/D/E…)
# ----------------------------------------------------------------------

def champ_letter(ch: dict) -> str:
    return (ch.get("lettre") or ch.get("letter") or "").strip().upper()

def champ_name(ch: dict) -> str:
    return (ch.get("name") or ch.get("nom") or "Champion").strip()

def champions_by_letter(fac: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ch in (fac.get("champions") or []):
        if not isinstance(ch, dict):
            continue
        L = champ_letter(ch)
        if L:
            out[L] = ch
    return out

def print_champion_menu(fac: dict) -> list[str]:
    m = champions_by_letter(fac)
    letters = sorted(m.keys())
    if not letters:
        print("[WARN] Aucun champion détecté pour cette faction.")
        return []
    parts = [f"{L}:{champ_name(m[L])}" for L in letters]
    print("Champions disponibles:", " | ".join(parts))
    return letters

def choose_champion_letter_cli(fac: dict, default_letter: str | None = None) -> str:
    letters = print_champion_menu(fac)
    if not letters:
        return "A"

    default_letter = (default_letter or letters[0]).strip().upper()
    if default_letter not in letters:
        default_letter = letters[0]

    while True:
        s = input(f"Choix champion ({'/'.join(letters)}) (Enter={default_letter}) : ").strip().upper()
        if not s:
            return default_letter
        if s in letters:
            return s
        print(f"[WARN] '{s}' invalide. Réessaye.")

def choose_faction(faction_id: int, champion_letter: str = "A"):
    """
    Retourne un dict simplifié :
      {
        'id', 'name', 'style', 'gameplay',
        'champion': {...},
        'units_by_level': {...},
        'ai_profile': {...}
      }
    """
    if not FACTIONS_DATA:
        print("[FACTIONS] Fallback générique.")
        return {
            'id': faction_id,
            'name': f'Faction {faction_id}',
            'style': '',
            'gameplay': '',
            'champion': {
                'nom': 'Champion',
                'stats': {'ATK': 7, 'DEF': 10, 'HP': 20}
            },
            'units_by_level': {},
            'ai_profile': build_default_ai_profile(),
        }

    fac = None
    for f in FACTIONS_DATA:
        if f.get('id') == faction_id:
            fac = f
            break
    if fac is None:
        raise ValueError(f"Faction {faction_id} introuvable")

    champ = None
    for c in fac.get("champions", []):
        if c.get("lettre") == champion_letter:
            champ = c
            break
    if champ is None and fac.get("champions"):
        champ = fac["champions"][0]

    units_by_level = {}
    for m in fac.get("monstres", []):
        dep = m.get("dependance_champion")
        if dep and dep != champion_letter:
            continue
        lvl = m.get("niveau", 1)
        units_by_level.setdefault(lvl, []).append(m)

    ai_profile = fac.get("ai_profile") or build_default_ai_profile(fac.get('nom'))

    return {
        'id': fac.get('id', faction_id),
        'name': fac.get('nom', f'Faction {faction_id}'),
        'style': fac.get('style', ''),
        'gameplay': fac.get('gameplay', ''),
        'champion': champ,
        'units_by_level': units_by_level,
        'ai_profile': ai_profile,
    }


def choose_faction_for_player():
    if not FACTIONS_DATA:
        print("[FACTIONS] Aucune donnée, fallback Humains A.")
        return 1, "A"

    print("\n=== Sélection de faction (Joueur A) ===")
    for f in FACTIONS_DATA:
        print(f"[{f['id']}] {f['nom']} — {f.get('style', '')}")

    while True:
        ch = input("Id de faction (Enter=1) : ").strip()
        if ch == "":
            fid = 1
        else:
            try:
                fid = int(ch)
            except ValueError:
                print("Id invalide.")
                continue

        fac_list = [f for f in FACTIONS_DATA if f.get("id") == fid]
        if not fac_list:
            print("Id invalide.")
            continue

        fac = fac_list[0]  # ✅ dict, pas list

        champs = fac.get("champions", [])
        if not champs:
            return fid, "A"

        ch_lettre = choose_champion_letter_cli(fac, default_letter="A")
        return fid, ch_lettre

def choose_faction_for_ai(player_fid: int):
    if not FACTIONS_DATA:
        print("[FACTIONS] Fallback Reptiliens A.")
        return 3, "A"

    # On évite (si possible) la même faction que le joueur
    options = [f for f in FACTIONS_DATA if f.get("id") != player_fid]
    if not options:
        options = FACTIONS_DATA

    fac = random.choice(options)
    fid = fac.get("id", 3)

    champs = fac.get("champions", [])
    letters = [c.get("lettre") for c in champs if c.get("lettre")]

    if letters:
        #  Nouveau : l’IA choisit aléatoirement A / B / C (ou ce qui existe)
        letter = random.choice(letters)
    else:
        # fallback ultra-sécurité
        letter = "A"

    print(f"\n[IA] Faction choisie : {fac.get('nom', '???')} (id={fid}, champion {letter})")
    record_ai_pick(fid)
    return fid, letter



# ----------------------------------------------------------------------
#  PARSE ABILITIES (texte -> coût minimal)
# ----------------------------------------------------------------------

def parse_ability_from_action_speciale(action_text: str, fallback_id=None):
    """
    Heuristique robuste:
    - extrait un coût depuis les parenthèses: (2 DEF + 1 MOVE), (3 TRAP), etc.
    - extrait portée: "portée 2"
    - extrait durée: "reste 2 tours", "pendant 3 tours"
    - détecte effets: buff_def, damage, poison
    """
    if not action_text:
        return None

    data = {
        "id": fallback_id,
        "name": action_text,
        "cost": {},
        "range": 1,
        "target_type": "self",
        "effects": {"raw_text": action_text},
        "max_per_turn": 1,
    }

    text = action_text.lower()

    # ---- cible (tile / enemy / self) ----
    if any(w in text for w in ["pose ", "pose un", "pose une", "zone", "jeton", "piège", "sur la case", "case cibl", "au sol"]):
        data["target_type"] = "tile"
    elif "cible" in text and any(w in text for w in ["ennemi", "adversaire"]):
        data["target_type"] = "enemy"
    else:
        # défaut conservateur
        data["target_type"] = data.get("target_type") or "self"


    # ---- coût (dans les parenthèses) ----
    # Certains textes contiennent plusieurs variantes (ex: "Attaque normale (1 ATK) / Attaque lourde (3 ATK)")
    # On prend le chunk de parenthèses avec le score de coût le plus élevé, pour rester cohérent avec la variante affichée.
    chunks = re.findall(r"\(([^)]*)\)", action_text)
    best_chunk = None
    best_score = -1
    for ch in chunks:
        ch_l = str(ch).lower()
        nums = [int(n) for n, _ in re.findall(r"(\d+)\s*(atk|def|trap|move|cap)", ch_l)]
        score = sum(nums) if nums else -1
        if score > best_score:
            best_score = score
            best_chunk = ch_l
    if best_chunk:
        for n, key in re.findall(r"(\d+)\s*(atk|def|trap|move|cap)", best_chunk):
            k = key.upper()
            # TRAP dans le texte JSON = ressource CAP (refacto sémantique)
            if k == "TRAP":
                k = "CAP"
            data["cost"][k] = data["cost"].get(k, 0) + int(n)


    # ---- portée ----
    m = re.search(r"port[ée]e?\s*(\d+)", text)
    if m:
        data["range"] = int(m.group(1))

    # ---- durée ----
    m = re.search(r"(reste|pendant)\s*(\d+)\s*tour", text)
    if m:
        data["effects"]["duration"] = int(m.group(2))

    # ---- effets (mots-clés) ----
    # Buff DEF
    if "déf" in text or "def" in text:
        if any(w in text for w in ["gagne", "+", "amélior", "posture", "verrouillage", "bouclier"]):
            data["effects"]["buff_def"] = data["effects"].get("buff_def", 2)
            data["effects"]["duration"] = data["effects"].get("duration", 1)

    # Dégâts (et "dégâts directs" -> ignore DEF)
    if "dégât" in text or "degat" in text or "damage" in text:
        m = re.search(r"(\d+)\s*d[ée]g[âa]t", text)
        if m:
            data["effects"]["damage"] = int(m.group(1))
        else:
            data["effects"]["damage"] = data["effects"].get("damage", 3)
        if "direct" in text:
            data["effects"]["ignore_def"] = True

    # Poison
    if "poison" in text or "toxique" in text:
        data["effects"]["poison"] = 1
        data["effects"]["poison_damage"] = 1
        data["effects"]["duration"] = data["effects"].get("duration", 2)

    return data

# ----------------------------------------------------------------------
#  UNITÉS
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
#  UID (unit id) – canon (Q8)
# ----------------------------------------------------------------------
_UID_SEQ = 0
def alloc_uid(owner: str = "U") -> str:
    global _UID_SEQ
    _UID_SEQ += 1
    return f"{owner}{_UID_SEQ:04d}"


class Unit:
    def __init__(
        self,
        owner,
        row,
        col,
        uid=None,
        hp=10,
        atk=3,
        move=2,
        name="Unité",
        defense=0,
        ability_id=None,
        ability_name=None,
        ability_cost=None,
        ability_range=None,
        ability_target_type=None,
        ability_effects=None,
        ability_max_per_turn=1,
        is_champion=False,
        level=1,
    ):
        self.owner = owner  # 'A' ou 'B'
        self.row = row
        self.col = col
        self.hp = hp
        self.atk = atk
        self.move = move
        self.name = name
        self.defense = defense

        # Buff DEF temporaire
        self.temp_def = 0
        self.buff_def_duration = 0

        # Cooldown de garde
        self.guard_cd = 0
        # Statuts (V2)
        self.poison_stacks = 0
        self.poison_duration = 0
        self.poison_damage = 1

        self.has_moved = False
        self.has_attacked = False

        # --- V2 : compétences ---
        self.ability_id = ability_id
        self.ability_name = ability_name
        self.ability_cost = ability_cost or {}
        self.ability_range = ability_range
        self.ability_target_type = ability_target_type
        self.ability_effects = ability_effects or {}
        self.ability_max_per_turn = ability_max_per_turn
        self.ability_uses_this_turn = 0

        # Champion ?
        self.is_champion = is_champion

        # Niveau d’invocation (1–5)
        self.level = level


    @property
    def has_ability(self) -> bool:
        # on considère qu’un nom suffit (coût vide = capacité gratuite)
        return bool(self.ability_name)

class Ability:
    """
    Optionnel : pour plus tard si tu veux des objets Ability.
    Actuellement, le jeu passe par les champs sur Unit.
    """
    def __init__(self, name,
                 cost=None,
                 effect_type=None,
                 effect_value=0,
                 effect_duration=0,
                 target="self"):
        self.name = name
        self.cost = cost or {}
        self.effect_type = effect_type
        self.effect_value = effect_value
        self.effect_duration = effect_duration
        self.target = target


def ability_from_data(data):
    """Construit un objet Ability à partir d'un dict (non utilisé pour l'instant)."""
    return Ability(
        name=data.get("name", "Ability"),
        cost=data.get("cost", {}),
        effect_type=data.get("effect_type"),
        effect_value=data.get("effect_value", 0),
        effect_duration=data.get("effect_duration", 0),
        target=data.get("target", "self"),
    )


# ----------------------------------------------------------------------
#  GAME STATE (inclut QG séparé + champion + profils IA)
# ----------------------------------------------------------------------

# Pending QG damage pour hook RL (réinitialisé à chaque lecture dans ddm_p4_rl)
_RL_QG_DMG_PENDING: dict = {}

class GameState:
    def __init__(self, board, faction_A_info, faction_B_info):
        self.board = board
        self.turn = 1
        self.max_rounds = 120   # contrainte de temps — modifiable par la boucle principale
        self.current_player = 1
        self.last_roll = []

        self.pool_A = {"ATK": 0, "DEF": 0, "MOVE": 0, "CAP": 0}
        self.pool_B = {"ATK": 0, "DEF": 0, "MOVE": 0, "CAP": 0}
        self.tile_effects = []  # zones/pièges posés au sol (durée en tours)

        # --- Factions & champions ---
        self.faction_A = faction_A_info
        self.faction_B = faction_B_info

        # Champion A
        champ_A = faction_A_info['champion']
        stats_A = champ_A.get("stats", {}) if champ_A else {}
        effet_A = champ_A.get("effet_defensif", "") if champ_A else ""
        self.hero_A = {
            "name": champ_A.get("nom", "Champion A") if champ_A else "Champion A",
            "hp": stats_A.get("HP", 20),
            "atk": stats_A.get("ATK", 7),
            "def": stats_A.get("DEF", 10),
            "faction": faction_A_info['name'],
            "effet_defensif": effet_A,
        }
        # pour usage facile ailleurs (logs / UI / futurs hooks)
        self.champion_A_effet_defensif = effet_A

        # Champion B
        champ_B = faction_B_info['champion']
        stats_B = champ_B.get("stats", {}) if champ_B else {}
        effet_B = champ_B.get("effet_defensif", "") if champ_B else ""
        self.hero_B = {
            "name": champ_B.get("nom", "Champion B") if champ_B else "Champion B",
            "hp": stats_B.get("HP", 20),
            "atk": stats_B.get("ATK", 7),
            "def": stats_B.get("DEF", 10),
            "faction": faction_B_info['name'],
            "effet_defensif": effet_B,
        }
        self.champion_B_effet_defensif = effet_B

        # Unités par niveau
        self.units_by_level_A = faction_A_info.get("units_by_level", {})
        self.units_by_level_B = faction_B_info.get("units_by_level", {})

        # Profils IA
        self.ai_profile_A = faction_A_info.get("ai_profile", build_default_ai_profile(faction_A_info.get("name")))
        self.ai_profile_B = faction_B_info.get("ai_profile", build_default_ai_profile(faction_B_info.get("name")))

        # --- QG séparés (HP, DEF) + aura du champion ---
        # Joueur A
        self.hq_A_hp_max = 35
        self.hq_A_hp = 35
        self.hq_A_def_base = 3
        self.hq_A_def_aura = 2  # bonus si champion A dormant
        self.champion_A_state = "dormant"  # "dormant", "deployed", "dead"

        # IA B
        self.hq_B_hp_max = 35
        self.hq_B_hp = 35
        self.hq_B_def_base = 3
        self.hq_B_def_aura = 2
        self.champion_B_state = "dormant"  # "dormant", "deployed", "dead"

        # --- MAJ9+ : Sleep Dash (mobilité early tant que champion dormant)
        # Réinitialisé à chaque début de tour dans la loop.
        self.sleep_dash_left_A = 0
        self.sleep_dash_left_B = 0

    # --- Helpers QG & champion ---

    def get_hq_effective_def(self, side: str) -> int:
        if side == 'A':
            bonus = self.hq_A_def_aura if self.champion_A_state == "dormant" else 0
            return self.hq_A_def_base + bonus
        else:
            bonus = self.hq_B_def_aura if self.champion_B_state == "dormant" else 0
            return self.hq_B_def_base + bonus

    def damage_hq(self, side: str, raw_atk: int, tag: str, attacker_pos=None):
        eff_def = self.get_hq_effective_def(side)
        dmg = max(1, raw_atk - eff_def)

        if side == 'A':
            self.hq_A_hp -= dmg
            hp_now = self.hq_A_hp
        else:
            self.hq_B_hp -= dmg
            hp_now = self.hq_B_hp

        pos_str = ""
        if attacker_pos is not None:
            pos_str = f" from_pos=({attacker_pos[0]},{attacker_pos[1]})"

        log(f"HQ_DMG_{side}[{tag}]: raw_atk={raw_atk} eff_def={eff_def} "
            f"dmg={dmg} hp_now={hp_now}{pos_str}")
        print(f"     -> QG {side} subit {dmg} dégâts (ATK={raw_atk}, DEF={eff_def}) -> HP={hp_now}")

        # Hook RL : incrémenter dmg_qg pour le joueur attaquant (opposé de side)
        try:
            import sys
            state_module = sys.modules.get("engine.ddm_p1_core") or sys.modules.get("DDM.ddm_p1_core")
            # On cherche le ctx dans le state courant via la convention rl_turn_ctx
            # L'attaquant est l'opposé du camp qui subit (side)
            attacker_char = "A" if side == "B" else "B"
            # On ne peut pas accéder au state ici directement — signal posé via module global
            _RL_QG_DMG_PENDING["char"] = attacker_char
            _RL_QG_DMG_PENDING["dmg"] = _RL_QG_DMG_PENDING.get("dmg", 0) + dmg
        except Exception:
            pass

        return dmg



# ----------------------------------------------------------------------
