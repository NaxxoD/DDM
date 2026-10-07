"""Bascule les data/{profile}_prefs.json entre 1er et 2nd choix interview.

Source : <dossier-resultats><modele>.md
Reference table hardcoded ici pour aligner exactement avec interviews.

Usage :
    python tools/scripts/swap_prefs.py --to first    # basule vers interview 1er
    python tools/scripts/swap_prefs.py --to second   # basule vers interview 2nd
    python tools/scripts/swap_prefs.py --check       # affiche état actuel
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

# Source-of-truth interview .md
INTERVIEW_PREFS = {
    # profile  : (1st_faction, 1st_champion, 2nd_faction, 2nd_champion)
    "haiku":    (7, "D", 3, "B"),  # Égypte/Serapia → Reptiliens/Nythra
    "gemini":   (4, "D", 3, "B"),  # Cyborgs/Architecte → Reptiliens/Nythra
    "chatgpt":  (4, "B", 3, "B"),  # Cyborgs/Analyste → Reptiliens/Nythra
    "mistral":  (4, "B", 1, "A"),  # Cyborgs/Analyste → Humains/Archonte
    "grok":     (5, "A", 2, "C"),  # Orcs/Chef Grok → Démons/Incarnation Rage
    "sonnet":   (4, "B", 7, "D"),  # Cyborgs/Analyste → Égypte/Serapia
    "opus":     (4, "D", 3, "D"),  # Cyborgs/Architecte → Reptiliens/Venina
    "deepseek": (6, "A", 3, "B"),  # Lycans/Alpha → Reptiliens/Nythra
    "qwen3":    (8, "E", 8, "C"),  # Abom/Manipulateur → Abom/Chaos Élémentaire
    "glm":      (3, "A", 6, "E"),  # Reptiliens/Pyroscale → Lycans/Gardien Céleste
}


def load_prefs(profile: str) -> dict | None:
    fp = DATA_DIR / f"{profile}_prefs.json"
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def save_prefs(profile: str, data: dict):
    fp = DATA_DIR / f"{profile}_prefs.json"
    fp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", choices=["first", "second"], help="Bascule vers 1er ou 2nd choix interview")
    ap.add_argument("--check", action="store_true", help="Affiche l'état actuel")
    args = ap.parse_args()

    if args.check or not args.to:
        print(f"{'profil':<10} {'actuel':<8} | {'1st':<6} {'2nd':<6}  diff")
        print("-" * 60)
        for profile, (f1, c1, f2, c2) in INTERVIEW_PREFS.items():
            data = load_prefs(profile)
            if not data:
                print(f"{profile:<10} (no prefs file)")
                continue
            pref = data.get("preferred", {})
            cur_f, cur_c = pref.get("faction"), pref.get("champion")
            cur = f"f{cur_f}+{cur_c}"
            first = f"f{f1}+{c1}"
            second = f"f{f2}+{c2}"
            diff = "1st" if cur == first else ("2nd" if cur == second else "DRIFT")
            print(f"{profile:<10} {cur:<8} | {first:<6} {second:<6}  {diff}")
        return

    print(f"Basculement vers {args.to.upper()} choice...")
    n_changed = 0
    for profile, (f1, c1, f2, c2) in INTERVIEW_PREFS.items():
        data = load_prefs(profile)
        if not data:
            continue
        if args.to == "first":
            new_f, new_c = f1, c1
        else:
            new_f, new_c = f2, c2

        old = data.get("preferred", {})
        if old.get("faction") == new_f and old.get("champion") == new_c:
            continue  # déjà à jour
        data["preferred"] = {"faction": new_f, "champion": new_c}
        save_prefs(profile, data)
        print(f"  {profile:<10}  f{old.get('faction')}+{old.get('champion')} -> f{new_f}+{new_c}")
        n_changed += 1

    print(f"\n[OK] {n_changed} profils mis à jour vers {args.to} choice.")


if __name__ == "__main__":
    main()
