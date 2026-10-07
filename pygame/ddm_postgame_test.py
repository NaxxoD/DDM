# =============================================================================
# ddm_postgame_test.py — Données de test pour ddm_post_game.py
#
# Écrit un latest.json de fin de partie + un .log fictif,
# puis lance ddm_post_game.py directement.
#
# Usage :
#   python ddm_postgame_test.py
# =============================================================================

import json, pathlib, sys, subprocess
from datetime import datetime

import os
_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_PATH = pathlib.Path(os.path.join(_DDM_ROOT, "engine", "snapshots", "latest.json"))
LOG_DIR       = pathlib.Path(os.path.join(_DDM_ROOT, "logs", "log_data", "log"))
POST_GAME     = pathlib.Path(__file__).parent / "ddm_post_game.py"

# =============================================================================
# SNAPSHOT FIN DE PARTIE
# =============================================================================
snapshot = {
    "tour": 14,
    "joueur_actif": "A",
    "winner": "A",

    "joueur_A": {
        "faction": "Lycans – Meutes Lunaires",
        "qg": {"hp": 18, "hp_max": 35, "def": 3, "champion_state": "dormant", "pos": [18, 6]},
        "champion": {
            "nom": "Alpha Lunaire", "hp": 12, "hp_max": 20,
            "atk": 11, "def": 9, "faction": "Lycans – Meutes Lunaires", "etat": "dormant"
        },
        "pool": {"MOVE": 0, "ATK": 0, "DEF": 0, "CAP": 0},
        "unites": [
            {"nom": "Loup Gris",       "owner": "A", "faction": "Lycans – Meutes Lunaires",
             "niveau": 1, "hp": 6, "hp_max": 8, "atk": 3, "def": 1,
             "row": 12, "col": 5, "is_champion": False, "lettre": ""},
            {"nom": "Rôdeur Nocturne", "owner": "A", "faction": "Lycans – Meutes Lunaires",
             "niveau": 2, "hp": 9, "hp_max": 12, "atk": 5, "def": 2,
             "row": 10, "col": 6, "is_champion": False, "lettre": ""},
            {"nom": "Grand Lycan",     "owner": "A", "faction": "Lycans – Meutes Lunaires",
             "niveau": 3, "hp": 14, "hp_max": 18, "atk": 7, "def": 3,
             "row": 8, "col": 7, "is_champion": False, "lettre": ""},
        ],
    },

    "joueur_B": {
        "faction": "Reptiliens – Légions Écailles-Feu",
        "qg": {"hp": 0, "hp_max": 35, "def": 3, "champion_state": "dormant", "pos": [0, 6]},
        "champion": {
            "nom": "Seigneur Pyroscale", "hp": 0, "hp_max": 18,
            "atk": 12, "def": 8, "faction": "Reptiliens – Légions Écailles-Feu", "etat": "dormant"
        },
        "pool": {"MOVE": 0, "ATK": 0, "DEF": 0, "CAP": 0},
        "unites": [
            {"nom": "Lézard Cramoisi", "owner": "B", "faction": "Reptiliens – Légions Écailles-Feu",
             "niveau": 1, "hp": 3, "hp_max": 7, "atk": 4, "def": 1,
             "row": 6, "col": 4, "is_champion": False, "lettre": ""},
        ],
    },

    "grille": [
        list("......B......"),
        list(".bbbbb.bbbbbb"),
        list(".bbbbb.bbbbbb"),
        list(".bbbbb.bbbbbb"),
        list(".bbbbb.bbbbbb"),
        list(".bbbbb.bbbbbb"),
        list("............."),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list(".aaaaa.aaaaaa"),
        list("......A......"),
    ],

    "des": [],
    "des_A": [], "des_B": [],
    "faces_A": [], "faces_B": [],
    "log": [
        "=== Tour 14 — Joueur A ===",
        "[COMBAT] Grand Lycan attaque QG B — 9 DMG",
        "[FIN] Victoire Joueur A — QG B détruit",
    ],
    "log_B": [],
    "traps": [],
    "invoc_niveau": None,
}

# =============================================================================
# LOG FICTIF
# =============================================================================
log_lines = [
    "# Proto_DDM run test_post_game\n",
    # Rolls joueur A
    "ROLL A: L1-Blanc-1(1) -> MOVE\n",
    "ROLL A: L1-Blanc-2(1) -> ATK\n",
    "ROLL A: L2-Vert-Stable-1(2) -> STAR\n",
    "ROLL_END player=A stars=1 invoc_level=None\n",
    "ROLL A: L2-Vert-Agro-1(2) -> ATK\n",
    "ROLL A: L2-Vert-Stable-2(2) -> CAP\n",
    "ROLL A: L3-Bleu-1(3) -> STAR\n",
    "ROLL_END player=A stars=1 invoc_level=None\n",
    "ROLL A: L1-Blanc-1(1) -> STAR\n",
    "ROLL A: L2-Vert-Stable-1(2) -> STAR\n",
    "ROLL A: L3-Bleu-1(3) -> ATK\n",
    "ROLL_END player=A stars=2 invoc_level=2\n",
    "INVOKE_RESULT player=A level=2 success=1\n",
    "ROLL A: L3-Bleu-2(3) -> CAP\n",
    "ROLL A: L4-Rouge-1(4) -> ATK\n",
    "ROLL A: L1-Blanc-3(1) -> DEF\n",
    "ROLL_END player=A stars=0 invoc_level=None\n",
    "ROLL A: L2-Vert-Stable-1(2) -> ATK\n",
    "ROLL A: L2-Vert-Agro-1(2) -> MOVE\n",
    "ROLL A: L3-Bleu-1(3) -> STAR\n",
    "ROLL_END player=A stars=1 invoc_level=None\n",
    "ROLL A: L2-Vert-Stable-2(2) -> CAP\n",
    "ROLL A: L3-Bleu-2(3) -> STAR\n",
    "ROLL A: L4-Rouge-1(4) -> STAR\n",
    "ROLL_END player=A stars=2 invoc_level=3\n",
    "INVOKE_RESULT player=A level=3 success=1\n",
    "ROLL A: L4-Rouge-2(4) -> ATK\n",
    "ROLL A: L5-Noir-1(5) -> DEF\n",
    "ROLL A: L3-Bleu-1(3) -> CAP\n",
    "ROLL_END player=A stars=0 invoc_level=None\n",
    "ROLL A: L4-Rouge-1(4) -> STAR\n",
    "ROLL A: L4-Rouge-2(4) -> STAR\n",
    "ROLL A: L5-Noir-1(5) -> STAR\n",
    "ROLL_END player=A stars=3 invoc_level=4\n",
    "INVOKE_RESULT player=A level=4 success=1\n",
    # Rolls joueur B
    "ROLL B: L1-Blanc-1(1) -> MOVE\n",
    "ROLL B: L1-Blanc-2(1) -> DEF\n",
    "ROLL B: L2-Vert-Stable-1(2) -> ATK\n",
    "ROLL_END player=B stars=0 invoc_level=None\n",
    "ROLL B: L2-Vert-Agro-1(2) -> ATK\n",
    "ROLL B: L2-Vert-Stable-2(2) -> STAR\n",
    "ROLL B: L3-Bleu-1(3) -> MOVE\n",
    "ROLL_END player=B stars=1 invoc_level=None\n",
    "ROLL B: L1-Blanc-3(1) -> STAR\n",
    "ROLL B: L2-Vert-Stable-1(2) -> STAR\n",
    "ROLL B: L3-Bleu-2(3) -> DEF\n",
    "ROLL_END player=B stars=2 invoc_level=2\n",
    "INVOKE_RESULT player=B level=2 success=1\n",
    "ROLL B: L3-Bleu-1(3) -> ATK\n",
    "ROLL B: L4-Rouge-1(4) -> CAP\n",
    "ROLL B: L2-Vert-Agro-1(2) -> ATK\n",
    "ROLL_END player=B stars=0 invoc_level=None\n",
    "ROLL B: L3-Bleu-2(3) -> STAR\n",
    "ROLL B: L3-Bleu-1(3) -> STAR\n",
    "ROLL B: L4-Rouge-2(4) -> ATK\n",
    "ROLL_END player=B stars=2 invoc_level=3\n",
    "INVOKE_RESULT player=B level=3 success=1\n",
    "ROLL B: L4-Rouge-1(4) -> CAP\n",
    "ROLL B: L5-Noir-1(5) -> ATK\n",
    "ROLL B: L3-Bleu-2(3) -> MOVE\n",
    "ROLL_END player=B stars=0 invoc_level=None\n",
]

# =============================================================================
# ÉCRITURE
# =============================================================================
SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[TEST] Snapshot fin de partie écrit : {SNAPSHOT_PATH}")

LOG_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = LOG_DIR / f"run_{ts}_test.log"
log_path.write_text("".join(log_lines), encoding="utf-8")
print(f"[TEST] Log fictif écrit : {log_path}")

# =============================================================================
# LANCEMENT
# =============================================================================
print("[TEST] Lancement ddm_post_game.py...")
subprocess.run([sys.executable, str(POST_GAME)])
