#!/usr/bin/env python3
"""
compare_ddm_json_focus.py

Compare deux fichiers JSON DDM (factions / champions / monsters) et
affiche les différences de manière lisible :

- regroupées par faction
- puis par champion / monstre
- avec les champs qui diffèrent (ex: stats.ATK : 7 -> 8)

Utilisation :
    python compare_ddm_json_focus.py
    (puis entrer les chemins des deux JSON quand demandé)
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# clés qu'on ignore (fluff / description)
IGNORE_KEYS = {
    "design_visuel",
    "description",
    "fluff",
    "lore",
    "role",
    "effet_offensif",
    # "effet_defensif",  # tu peux l'ajouter ici si tu veux l'ignorer aussi
}


def load_json(path_str: str) -> Any:
    path = Path(path_str)
    if not path.exists():
        raise SystemExit(f"[ERREUR] Fichier introuvable : {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_factions_root(data: Any) -> List[Dict[str, Any]]:
    """
    Gère deux formes possibles :
    - [ {...}, {...} ]
    - { "factions": [ {...}, {...} ] }
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "factions" in data:
        return data["factions"]
    raise SystemExit("Format non géré : racine doit être liste ou contenir 'factions'.")


def index_entities(entities: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Indexe une liste d'entités (champions/monsters) par identifiant stable.
    On essaie d'abord 'lettre', puis 'id', puis 'nom'. Sinon, on fabrique un id avec l'index.
    """
    indexed: Dict[str, Dict[str, Any]] = {}
    for i, e in enumerate(entities):
        key = (
            str(e.get("lettre"))
            if "lettre" in e
            else (str(e.get("id")) if "id" in e else (e.get("nom") or f"idx_{i}"))
        )
        indexed[key] = e
    return indexed


def print_entity_header(
    kind: str, fac_id: str, ent_key: str, ent1: Optional[Dict], ent2: Optional[Dict]
) -> None:
    """
    Affiche un titre lisible pour l'entité comparée.
    kind = "Champion" ou "Monstre"
    """
    name1 = ent1.get("nom") if ent1 else None
    name2 = ent2.get("nom") if ent2 else None
    lvl = None
    for ent in (ent1, ent2):
        if ent and "level" in ent:
            lvl = ent["level"]
            break

    name = name1 or name2 or "???"
    extra = f", level={lvl}" if lvl is not None else ""
    print(f"\n--- {kind} [{fac_id}] {ent_key} ({name}{extra}) ---")


def compare_leaf(a: Any, b: Any, path: str, diffs: List[str]) -> None:
    """Compare deux valeurs simples et ajoute une ligne de diff si différentes."""
    if a != b:
        diffs.append(f"{path} : {repr(a)} -> {repr(b)}")


def compare_entity_dict(a: Dict, b: Dict, prefix: str = "") -> List[str]:
    """
    Compare deux dictionnaires représentant un champion/monstre,
    en ignorant les clés de IGNORE_KEYS et en affichant les différences
    sous forme de 'clé.sous_clé : old -> new'.
    """
    diffs: List[str] = []
    keys_a = set(a.keys())
    keys_b = set(b.keys())

    # clés en plus / en moins
    for key in sorted(keys_a - keys_b):
        if key in IGNORE_KEYS:
            continue
        path = f"{prefix}.{key}" if prefix else key
        diffs.append(f"{path} : présent seulement dans JSON1 -> {repr(a[key])}")

    for key in sorted(keys_b - keys_a):
        if key in IGNORE_KEYS:
            continue
        path = f"{prefix}.{key}" if prefix else key
        diffs.append(f"{path} : présent seulement dans JSON2 -> {repr(b[key])}")

    # clés communes
    for key in sorted(keys_a & keys_b):
        if key in IGNORE_KEYS:
            continue
        val_a = a[key]
        val_b = b[key]
        path = f"{prefix}.{key}" if prefix else key

        # dict -> récursif
        if isinstance(val_a, dict) and isinstance(val_b, dict):
            diffs.extend(compare_entity_dict(val_a, val_b, prefix=path))
        # liste -> si différent, on affiche brut
        elif isinstance(val_a, list) and isinstance(val_b, list):
            if val_a != val_b:
                diffs.append(f"{path} : {repr(val_a)} -> {repr(val_b)}")
        else:
            compare_leaf(val_a, val_b, path, diffs)

    return diffs


def compare_entity_sets(
    kind: str,
    fac_id: str,
    ents1: List[Dict[str, Any]],
    ents2: List[Dict[str, Any]],
) -> None:
    """
    Compare deux listes d'entités (champions ou monstres) pour une faction donnée.
    kind = "Champion" ou "Monstre"
    """
    idx1 = index_entities(ents1)
    idx2 = index_entities(ents2)

    all_keys = sorted(set(idx1.keys()) | set(idx2.keys()))

    for ent_key in all_keys:
        e1 = idx1.get(ent_key)
        e2 = idx2.get(ent_key)

        if e1 is None:
            print_entity_header(kind, fac_id, ent_key, e1, e2)
            print("  (absent du JSON1, présent seulement dans JSON2)")
            continue
        if e2 is None:
            print_entity_header(kind, fac_id, ent_key, e1, e2)
            print("  (présent dans JSON1, absent du JSON2)")
            continue

        # les deux existent -> comparaison des champs
        diffs = compare_entity_dict(e1, e2, prefix="")
        if diffs:
            print_entity_header(kind, fac_id, ent_key, e1, e2)
            for d in diffs:
                print("  -", d)


def to_faction_id(f: Dict[str, Any], idx: int) -> str:
    return (
        str(f.get("lettre"))
        if "lettre" in f
        else (str(f.get("id")) if "id" in f else f.get("nom") or f"F{idx}")
    )


def main():
    print("=== Comparateur DDM focalisé (champions / monstres) ===")
    json1_name = input("Nom / chemin du 1er JSON (ancien ?) : ").strip()
    json2_name = input("Nom / chemin du 2e JSON (nouveau ?) : ").strip()

    if not json1_name or not json2_name:
        print("[ERREUR] Tu dois fournir deux chemins de fichiers.")
        return

    print(f"\n[INFO] Chargement de : {json1_name}")
    data1 = load_json(json1_name)
    print(f"[INFO] Chargement de : {json2_name}")
    data2 = load_json(json2_name)

    facs1 = get_factions_root(data1)
    facs2 = get_factions_root(data2)

    # indexation par id de faction
    idx_f1: Dict[str, Dict[str, Any]] = {}
    idx_f2: Dict[str, Dict[str, Any]] = {}

    for i, f in enumerate(facs1):
        fid = to_faction_id(f, i)
        idx_f1[fid] = f

    for i, f in enumerate(facs2):
        fid = to_faction_id(f, i)
        idx_f2[fid] = f

    all_fids = sorted(set(idx_f1.keys()) | set(idx_f2.keys()))

    for fid in all_fids:
        f1 = idx_f1.get(fid)
        f2 = idx_f2.get(fid)

        print("\n==========================================")
        print(f"Faction : {fid}")
        print("==========================================")

        if f1 is None:
            print("  (Faction absente du JSON1, présente seulement dans JSON2)")
            continue
        if f2 is None:
            print("  (Faction présente dans JSON1, absente du JSON2)")
            continue

        # Champions
        champs1 = f1.get("champions", []) or []
        champs2 = f2.get("champions", []) or []
        if champs1 or champs2:
            compare_entity_sets("Champion", fid, champs1, champs2)
        else:
            print("  Aucun champion dans cette faction (dans les deux fichiers).")

        # Monstres (plusieurs formats possibles)
        mon1 = f1.get("monsters", None)
        mon2 = f2.get("monsters", None)

        if isinstance(mon1, list) or isinstance(mon2, list):
            # cas simple : liste directe de monstres
            mlist1 = mon1 if isinstance(mon1, list) else []
            mlist2 = mon2 if isinstance(mon2, list) else []
            if mlist1 or mlist2:
                compare_entity_sets("Monstre", fid, mlist1, mlist2)
        elif isinstance(mon1, dict) or isinstance(mon2, dict):
            # cas dict par niveau : {"L1": [...], "L2": [...], ...}
            levels = set()
            if isinstance(mon1, dict):
                levels |= set(mon1.keys())
            if isinstance(mon2, dict):
                levels |= set(mon2.keys())
            for lvl in sorted(levels):
                mlist1 = mon1.get(lvl, []) if isinstance(mon1, dict) else []
                mlist2 = mon2.get(lvl, []) if isinstance(mon2, dict) else []
                if not (mlist1 or mlist2):
                    continue
                print(f"\n***** Monstres niveau {lvl} *****")
                compare_entity_sets("Monstre", fid, mlist1, mlist2)

    print("\n[FIN] Comparaison focalisée terminée.")


if __name__ == "__main__":
    main()
