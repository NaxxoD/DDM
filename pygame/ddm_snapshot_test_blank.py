import json, pathlib

snapshot = {
    "tour": 1,
    "joueur_actif": "A",
    "joueur_a": {
        "faction": "Lycans – Meutes Lunaires",
        "qg": {"hp": 35, "hp_max": 35, "def": 3, "champion_state": "dormant", "pos": [18, 6]},
        "champion": {"nom": "Alpha Lunaire", "hp": 20, "hp_max": 20, "atk": 11, "def": 9,
                     "faction": "Lycans – Meutes Lunaires", "etat": "dormant"},
        "pool": {"MOVE": 0, "ATK": 0, "DEF": 0, "CAP": 0},
        "unites": [],
    },
    "joueur_b": {
        "faction": "Reptiliens – Légions Scailles-Feu",
        "qg": {"hp": 35, "hp_max": 35, "def": 3, "champion_state": "dormant", "pos": [0, 6]},
        "champion": {"nom": "Seigneur Pyroscale", "hp": 18, "hp_max": 18, "atk": 12, "def": 8,
                     "faction": "Reptiliens – Légions Scailles-Feu", "etat": "dormant"},
        "pool": {"MOVE": 0, "ATK": 0, "DEF": 0, "CAP": 0},
        "unites": [],
    },
    "grille": [
        list("......B......"),  # 0
        list("............."),  # 1
        list("............."),  # 2
        list("............."),  # 3
        list("............."),  # 4
        list("............."),  # 5
        list("............."),  # 6
        list("............."),  # 7
        list("............."),  # 8
        list("............."),  # 9
        list("............."),  # 10
        list("............."),  # 11
        list("............."),  # 12
        list("............."),  # 13
        list("............."),  # 14
        list("............."),  # 15
        list("............."),  # 16
        list("............."),  # 17
        list("......A......"),  # 18
    ],
    "des": [
        {"nom": "L3-Bleu-1", "niveau": 3, "faces": ["MOVE","ATK","CAP","CAP","DEF","STAR"], "utilise": False},
        {"nom": "L3-Bleu-2", "niveau": 3, "faces": ["MOVE","ATK","CAP","CAP","DEF","STAR"], "utilise": False},
        {"nom": "L3-Bleu-3", "niveau": 3, "faces": ["MOVE","ATK","CAP","CAP","DEF","STAR"], "utilise": False},
    ],
    "log": [
        "=== Tour 1 — Joueur A ===",
        "[DÉS] Joueur A : L3-Bleu-1 Lv3 → STAR | L3-Bleu-2 Lv3 → STAR | L3-Bleu-3 Lv3 → ATK",
        "[POOL] A → MOVE=0 ATK=1 DEF=0 CAP=0",
        "[INVOC] A Lv3 invoqué (2★)",
    ],
    "traps": []
}

out = pathlib.Path(__file__).resolve().parent.parent / "engine" / "snapshots" / "latest.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)

print("Snapshot vierge écrit.")
