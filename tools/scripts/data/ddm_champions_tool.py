# ddm_champions_tool.py (v3)
# Viewer + Admin Editor (Champions + Monstres + Faction) pour Data_8_Factions.json
#
# Exemples:
#   python ddm_champions_tool.py --json Data_8_Factions.json
#   python ddm_champions_tool.py --json Data_8_Factions.json --interactive
#
# Admin:
#   python ddm_champions_tool.py --json Data_8_Factions.json --edit
#   python ddm_champions_tool.py --json Data_8_Factions.json --edit --faction 3 --champion D
#   python ddm_champions_tool.py --json Data_8_Factions.json --edit --faction 3 --monster 7
#   python ddm_champions_tool.py --json Data_8_Factions.json --edit --faction 3 --monster 3:2   (lvl:rang)
#
# Sauvegarde: backup + écriture atomique (temp + replace)

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from textwrap import fill

LETTERS_DEFAULT = ["A", "B", "C", "D", "E"]
STATS_KEYS = ["ATK", "DEF", "HP"]


# ---------------------------
# Helpers
# ---------------------------

def _s(x) -> str:
    return "" if x is None else str(x)

def _get(d: dict, *keys, default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default

def _set(d: dict, value, *keys_preferred):
    # respecte clé existante si déjà présente, sinon prend la 1ère proposée
    for k in keys_preferred:
        if k in d:
            d[k] = value
            return
    d[keys_preferred[0]] = value

def _wrap(label: str, text: str, width: int, indent: int = 2) -> str:
    if not text.strip():
        return f'{" " * indent}{label}: (aucun)'
    wrapped = fill(text.strip(), width=width, subsequent_indent=" " * (indent + len(label) + 2))
    return f'{" " * indent}{label}: {wrapped}'

def _safe_int(s: str):
    s = s.strip()
    if s == "":
        return None
    try:
        return int(s)
    except ValueError:
        return "INVALID"


# ---------------------------
# JSON I/O (backup + atomic)
# ---------------------------

def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERREUR] Fichier introuvable: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERREUR] JSON invalide: {e}", file=sys.stderr)
        sys.exit(1)

def save_json_atomic(path: Path, data: dict, make_backup: bool = True) -> Path | None:
    backup_path = None
    if make_backup and path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_suffix(path.suffix + f".bak_{ts}")
        backup_path.write_bytes(path.read_bytes())

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)
    return backup_path


# ---------------------------
# Viewer
# ---------------------------

def champ_line(ch: dict) -> str:
    letter = _s(_get(ch, "lettre", "letter", default="?")).upper()
    name = _s(_get(ch, "nom", "name", default="<?>"))
    stats = _get(ch, "stats", default={})
    if not isinstance(stats, dict):
        stats = {}
    atk = stats.get("ATK", "?")
    deff = stats.get("DEF", "?")
    hp = stats.get("HP", "?")
    return f"[{letter}] {name} — ATK {atk} | DEF {deff} | HP {hp}"

def monster_line(m: dict) -> str:
    lvl = _get(m, "niveau", default="?")
    name = _s(_get(m, "nom", default="<?>"))
    stats = _get(m, "stats", default={})
    if not isinstance(stats, dict):
        stats = {}
    atk = stats.get("ATK", "?")
    deff = stats.get("DEF", "?")
    hp = stats.get("HP", "?")
    return f"(N{lvl}) {name} — ATK {atk} | DEF {deff} | HP {hp}"

def pick_factions(data: dict, faction_filter: str | None) -> list[dict]:
    factions = data.get("factions")
    if not isinstance(factions, list):
        print("[ERREUR] Structure attendue: { 'factions': [ ... ] }", file=sys.stderr)
        sys.exit(1)

    if not faction_filter:
        return factions

    ff = faction_filter.strip()
    if ff.isdigit():
        fid = int(ff)
        out = [f for f in factions if f.get("id") == fid]
        if not out:
            print(f"[WARN] Aucune faction avec id={fid}.", file=sys.stderr)
        return out

    ff_low = ff.lower()
    out = [f for f in factions if ff_low in _s(_get(f, "nom", "name", default="")).lower()]
    if not out:
        print(f"[WARN] Aucune faction dont le nom contient: '{ff}'.", file=sys.stderr)
    return out

def print_faction(faction: dict, letters: set[str], only_def: bool, compact: bool, width: int, with_visual: bool):
    fid = _get(faction, "id", default="?")
    fname = _s(_get(faction, "nom", "name", default="<?>"))
    gameplay = _s(_get(faction, "gameplay", default="")).strip()

    print("=" * width)
    print(f"FACTION {fid} — {fname}")
    if gameplay:
        print(_wrap("Gameplay", gameplay, width=width, indent=0))
    print("-" * width)

    champions = _get(faction, "champions", default=None)
    if not isinstance(champions, list):
        print("  [WARN] champions manquant ou invalide.")
        print("=" * width)
        print()
        return

    champs = [c for c in champions if _s(_get(c, "lettre", "letter", default="")).upper() in letters]

    order = {l: i for i, l in enumerate(LETTERS_DEFAULT)}
    champs.sort(key=lambda c: order.get(_s(_get(c, "lettre", "letter", default="?")).upper(), 999))

    printed = 0
    for ch in champs:
        eff_def = _s(_get(ch, "effet_defensif", "defensive_effect", default="")).strip()
        if only_def and not eff_def:
            continue

        print("  " + champ_line(ch))
        if compact:
            print("    " + fill(f"DEF: {eff_def if eff_def else '(aucun)'}", width=width - 4))
        else:
            role = _s(_get(ch, "role", default="")).strip()
            action = _s(_get(ch, "action_speciale", "special_action", default="")).strip()
            visuel = _s(_get(ch, "design_visuel", "visual_design", default="")).strip()

            if role:
                print(_wrap("Rôle", role, width=width, indent=4))
            print(_wrap("Effet_def", eff_def, width=width, indent=4))
            if action:
                print(_wrap("Action", action, width=width, indent=4))
            if with_visual and visuel:
                print(_wrap("Visuel", visuel, width=width, indent=4))

        print()
        printed += 1

    if printed == 0:
        msg = "(aucun champion correspondant au filtre)" if only_def else "(aucun champion A→E trouvé)"
        print("  " + msg)

    print("=" * width)
    print()

def list_factions(factions: list[dict]):
    print("\nFactions dispo :")
    for f in factions:
        fid = _get(f, "id", default="?")
        fname = _s(_get(f, "nom", "name", default="<?>"))
        print(f"  {fid}: {fname}")
    print()

def interactive_view_loop(data: dict, args):
    factions = data.get("factions", [])
    if not isinstance(factions, list) or not factions:
        print("[ERREUR] Aucune faction trouvée.")
        return

    index = {str(_get(f, "id", default="")): f for f in factions}
    print("Mode interactif (viewer) — tape l'ID d'une faction, 'all', ou 'q'.\n")
    list_factions(factions)

    while True:
        choice = input("> ").strip().lower()
        if choice in ("q", "quit", "exit"):
            break
        if choice == "all":
            for f in factions:
                print_faction(f, args.letters_set, args.only_def, args.compact, args.width, args.with_visual)
            continue
        if choice in index:
            print_faction(index[choice], args.letters_set, args.only_def, args.compact, args.width, args.with_visual)
        else:
            print("[WARN] Invalide. Essaie un id, 'all', ou 'q'.")


# ---------------------------
# Editor (admin)
# ---------------------------

def select_faction_by_id(factions: list[dict], faction_id: int) -> dict | None:
    for f in factions:
        if _get(f, "id", default=None) == faction_id:
            return f
    return None

def select_champion_by_letter(faction: dict, letter: str) -> dict | None:
    champions = _get(faction, "champions", default=[])
    if not isinstance(champions, list):
        return None
    letter = letter.strip().upper()
    for ch in champions:
        ltr = _s(_get(ch, "lettre", "letter", default="")).upper()
        if ltr == letter:
            return ch
    return None

def parse_monster_selector(sel: str):
    """
    Support:
      - "7"   => index global (1-based)
      - "3:2" => niveau=3, rang=2 parmi les monstres de ce niveau (1-based)
    """
    sel = sel.strip()
    if ":" in sel:
        a, b = sel.split(":", 1)
        if a.strip().isdigit() and b.strip().isdigit():
            return ("lvl_rank", int(a.strip()), int(b.strip()))
        return ("invalid", None, None)
    if sel.isdigit():
        return ("index", int(sel), None)
    return ("invalid", None, None)

def select_monster_by_selector(faction: dict, selector: str) -> dict | None:
    monsters = _get(faction, "monstres", default=[])
    if not isinstance(monsters, list) or not monsters:
        return None

    kind, a, b = parse_monster_selector(selector)
    if kind == "index":
        idx = a - 1
        if 0 <= idx < len(monsters):
            return monsters[idx]
        return None

    if kind == "lvl_rank":
        lvl = a
        rank = b
        filtered = [m for m in monsters if _get(m, "niveau", default=None) == lvl]
        if 1 <= rank <= len(filtered):
            return filtered[rank - 1]
        return None

    return None

def select_faction_interactive(factions: list[dict]) -> dict | None:
    index = {str(_get(f, "id", default="")): f for f in factions}
    list_factions(factions)
    while True:
        raw = input("Choisis une faction (id) ou 'q' : ").strip().lower()
        if raw in ("q", "quit", "exit"):
            return None
        if raw in index and index[raw] is not None:
            return index[raw]
        print("[WARN] id invalide.")

def list_champions(faction: dict):
    champions = _get(faction, "champions", default=[])
    if not isinstance(champions, list):
        print("[WARN] champions invalide.")
        return []

    print("\nChampions (lettre: nom) :")
    for ch in champions:
        letter = _s(_get(ch, "lettre", "letter", default="?")).upper()
        name = _s(_get(ch, "nom", "name", default="<?>"))
        print(f"  {letter}: {name}")
    print()
    return champions

def select_champion_interactive(faction: dict) -> dict | None:
    champions = list_champions(faction)
    if not champions:
        return None

    index = {_s(_get(ch, "lettre", "letter", default="")).upper(): ch for ch in champions}

    while True:
        raw = input("Choisis un champion (A/B/C/D/E...) ou 'b' retour : ").strip().upper()
        if raw in ("B", "BACK"):
            return None
        if raw in index:
            return index[raw]
        print("[WARN] lettre invalide.")

def list_monsters(faction: dict):
    monsters = _get(faction, "monstres", default=[])
    if not isinstance(monsters, list):
        print("[WARN] monstres invalide.")
        return []

    print("\nMonstres (index: niveau - nom) :")
    for i, m in enumerate(monsters, start=1):
        lvl = _get(m, "niveau", default="?")
        name = _s(_get(m, "nom", default="<?>"))
        print(f"  {i:>2}) N{lvl} — {name}")
    print("  Tip: tu peux aussi cibler par 'niveau:rang' ex: 3:2 (N3, 2e monstre du niveau)")
    print()
    return monsters

def select_monster_interactive(faction: dict) -> dict | None:
    monsters = list_monsters(faction)
    if not monsters:
        return None

    while True:
        raw = input("Choisis un monstre (index ou 'niveau:rang') ou 'b' retour : ").strip().lower()
        if raw in ("b", "back"):
            return None
        m = select_monster_by_selector(faction, raw)
        if m is not None:
            return m
        print("[WARN] sélection invalide.")

def show_champion(ch: dict, width: int = 110):
    print("\n" + "-" * width)
    print(champ_line(ch))
    role = _s(_get(ch, "role", default="")).strip()
    eff_def = _s(_get(ch, "effet_defensif", "defensive_effect", default="")).strip()
    action = _s(_get(ch, "action_speciale", "special_action", default="")).strip()
    visuel = _s(_get(ch, "design_visuel", "visual_design", default="")).strip()
    stats = _get(ch, "stats", default={})
    if not isinstance(stats, dict):
        stats = {}

    if role:
        print(_wrap("Rôle", role, width=width, indent=2))
    print(_wrap("Effet_def", eff_def, width=width, indent=2))
    if action:
        print(_wrap("Action", action, width=width, indent=2))
    if visuel:
        print(_wrap("Visuel", visuel, width=width, indent=2))

    print("  Stats:", {k: stats.get(k, None) for k in STATS_KEYS})
    print("-" * width + "\n")

def show_monster(m: dict, width: int = 110):
    print("\n" + "-" * width)
    print(monster_line(m))
    role = _s(_get(m, "role", default="")).strip()
    action = _s(_get(m, "action_speciale", default="")).strip()
    visuel = _s(_get(m, "design_visuel", default="")).strip()
    lvl = _get(m, "niveau", default=None)
    stats = _get(m, "stats", default={})
    if not isinstance(stats, dict):
        stats = {}

    print(f"  Niveau: {lvl}")
    if role:
        print(_wrap("Rôle", role, width=width, indent=2))
    if action:
        print(_wrap("Action", action, width=width, indent=2))
    if visuel:
        print(_wrap("Visuel", visuel, width=width, indent=2))

    print("  Stats:", {k: stats.get(k, None) for k in STATS_KEYS})
    print("-" * width + "\n")

def raw_set(entity: dict):
    print("Mode brut : clé EXACTE de l'entité (ex: 'cooldown' ou 'stats.ATK').")
    key = input("  Clé = ").strip()
    if not key:
        return False
    val = input("  Valeur = ").rstrip("\n")

    if "." in key:
        head, tail = key.split(".", 1)
        if head == "stats":
            stats = _get(entity, "stats", default={})
            if not isinstance(stats, dict):
                stats = {}
                _set(entity, stats, "stats")
            v = _safe_int(val)
            stats[tail] = val if v in (None, "INVALID") else v
            return True
        else:
            print("[WARN] Seul 'stats.X' est supporté pour l'instant.")
            return False
    else:
        v = _safe_int(val)
        entity[key] = val if v in (None, "INVALID") else v
        return True

def edit_stats(entity: dict) -> bool:
    stats = _get(entity, "stats", default={})
    if not isinstance(stats, dict):
        stats = {}
        _set(entity, stats, "stats")

    dirty = False
    print("Modifier stats (laisser vide = ne change pas) :")
    for k in STATS_KEYS:
        cur = stats.get(k, None)
        raw = input(f"  {k} (actuel: {cur}) => ").strip()
        if raw == "":
            continue
        v = _safe_int(raw)
        if v == "INVALID":
            print(f"[WARN] '{raw}' n'est pas un int. Ignoré.")
            continue
        stats[k] = v
        dirty = True
    return dirty

def edit_champion(ch: dict) -> bool:
    dirty = False
    width = 110

    while True:
        show_champion(ch, width=width)
        print("Commandes :")
        print("  1) Modifier le nom        2) Modifier le rôle")
        print("  3) Modifier l'effet DEF   4) Modifier l'action")
        print("  5) Modifier le visuel     6) Modifier les stats")
        print("  7) Modifier une clé (brut) 9) Terminer / Retour")
        cmd = input("> ").strip().lower()

        if cmd in ("9", "done", "retour", "return"):
            return dirty

        if cmd in ("1", "nom", "name"):
            cur = _s(_get(ch, "nom", "name", default=""))
            val = input(f"Nouveau nom (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "nom", "name")
            dirty = True

        elif cmd in ("2", "role"):
            cur = _s(_get(ch, "role", default=""))
            val = input(f"Nouveau rôle (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "role")
            dirty = True

        elif cmd in ("3", "effet", "def"):
            cur = _s(_get(ch, "effet_defensif", "defensive_effect", default=""))
            val = input(f"Nouvel effet_defensif (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "effet_defensif", "defensive_effect")
            dirty = True

        elif cmd in ("4", "action"):
            cur = _s(_get(ch, "action_speciale", "special_action", default=""))
            val = input(f"Nouvelle action_speciale (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "action_speciale", "special_action")
            dirty = True

        elif cmd in ("5", "visuel"):
            cur = _s(_get(ch, "design_visuel", "visual_design", default=""))
            val = input(f"Nouveau design_visuel (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "design_visuel", "visual_design")
            dirty = True

        elif cmd in ("6", "stats"):
            dirty = edit_stats(ch) or dirty

        elif cmd in ("7", "brut", "raw"):
            dirty = raw_set(ch) or dirty

        else:
            print("[WARN] commande inconnue.")

def edit_monster(m: dict) -> bool:
    dirty = False
    width = 110

    while True:
        show_monster(m, width=width)
        print("Commandes :")
        print("  1) Modifier le nom        2) Modifier le rôle")
        print("  3) Modifier l'action      4) Modifier le visuel")
        print("  5) Modifier les stats     6) Modifier le niveau")
        print("  7) Modifier une clé (brut) 9) Terminer / Retour")
        cmd = input("> ").strip().lower()

        if cmd in ("9", "done", "retour", "return"):
            return dirty

        if cmd in ("1", "nom"):
            cur = _s(_get(m, "nom", default=""))
            val = input(f"Nouveau nom (actuel: '{cur}') : ").rstrip("\n")
            _set(m, val, "nom")
            dirty = True

        elif cmd in ("2", "role"):
            cur = _s(_get(m, "role", default=""))
            val = input(f"Nouveau rôle (actuel: '{cur}') : ").rstrip("\n")
            _set(m, val, "role")
            dirty = True

        elif cmd in ("3", "action"):
            cur = _s(_get(m, "action_speciale", default=""))
            val = input(f"Nouvelle action_speciale (actuel: '{cur}') : ").rstrip("\n")
            _set(m, val, "action_speciale")
            dirty = True

        elif cmd in ("4", "visuel"):
            cur = _s(_get(m, "design_visuel", default=""))
            val = input(f"Nouveau design_visuel (actuel: '{cur}') : ").rstrip("\n")
            _set(m, val, "design_visuel")
            dirty = True

        elif cmd in ("5", "stats"):
            dirty = edit_stats(m) or dirty

        elif cmd in ("6", "niveau", "level"):
            cur = _get(m, "niveau", default=None)
            raw = input(f"Nouveau niveau (actuel: {cur}) => ").strip()
            v = _safe_int(raw)
            if v in (None, "INVALID"):
                print("[WARN] Niveau invalide.")
            else:
                _set(m, v, "niveau")
                dirty = True

        elif cmd in ("7", "brut", "raw"):
            dirty = raw_set(m) or dirty

        else:
            print("[WARN] commande inconnue.")

def edit_faction_meta(f: dict) -> bool:
    dirty = False
    width = 110

    while True:
        fid = _get(f, "id", default="?")
        nom = _s(_get(f, "nom", "name", default=""))
        style = _s(_get(f, "style", default=""))
        gameplay = _s(_get(f, "gameplay", default=""))

        print("\n" + "-" * width)
        print(f"FACTION {fid} — {nom}")
        if style:
            print(_wrap("Style", style, width=width, indent=2))
        if gameplay:
            print(_wrap("Gameplay", gameplay, width=width, indent=2))
        print("-" * width)

        print("Commandes :")
        print("  1) Modifier le nom   2) Modifier le style   3) Modifier le gameplay")
        print("  9) Terminer / Retour")
        cmd = input("> ").strip().lower()

        if cmd in ("9", "done", "retour", "return"):
            return dirty

        if cmd in ("1", "nom"):
            val = input(f"Nouveau nom (actuel: '{nom}') : ").rstrip("\n")
            _set(f, val, "nom", "name")
            dirty = True
        elif cmd in ("2", "style"):
            val = input(f"Nouveau style (actuel: '{style}') : ").rstrip("\n")
            _set(f, val, "style")
            dirty = True
        elif cmd in ("3", "gameplay"):
            val = input(f"Nouveau gameplay (actuel: '{gameplay}') : ").rstrip("\n")
            _set(f, val, "gameplay")
            dirty = True
        else:
            print("[WARN] commande inconnue.")

def editor_loop(data: dict, json_path: Path, backup: bool, start_faction: str | None, start_champion: str | None, start_monster: str | None):
    factions = data.get("factions", [])
    if not isinstance(factions, list) or not factions:
        print("[ERREUR] Aucune faction trouvée.")
        return

    # pré-sélection (direct)
    if start_faction and start_faction.strip().isdigit():
        f = select_faction_by_id(factions, int(start_faction.strip()))
        if f:
            if start_champion:
                ch = select_champion_by_letter(f, start_champion)
                if ch:
                    changed = edit_champion(ch)
                    if changed:
                        resp = input("Sauvegarder maintenant ? (y/n) ").strip().lower()
                        if resp == "y":
                            b = save_json_atomic(json_path, data, make_backup=backup)
                            print(f"[OK] Sauvegardé.{(' Backup: ' + str(b)) if b else ''}")
                    return
                print("[WARN] Champion introuvable, retour menu normal.\n")

            if start_monster:
                m = select_monster_by_selector(f, start_monster)
                if m:
                    changed = edit_monster(m)
                    if changed:
                        resp = input("Sauvegarder maintenant ? (y/n) ").strip().lower()
                        if resp == "y":
                            b = save_json_atomic(json_path, data, make_backup=backup)
                            print(f"[OK] Sauvegardé.{(' Backup: ' + str(b)) if b else ''}")
                    return
                print("[WARN] Monstre introuvable, retour menu normal.\n")

    dirty_global = False

    while True:
        f = select_faction_interactive(factions)
        if f is None:
            break

        while True:
            print("\nMode admin — que veux-tu éditer ?")
            print("  1) Champion (A–E)")
            print("  2) Monstre (mob)")
            print("  3) Faction (nom/style/gameplay)")
            print("  b) Retour faction / q) Quitter")
            choice = input("> ").strip().lower()

            if choice in ("q", "quit", "exit"):
                if dirty_global:
                    resp = input("Changements non sauvegardés. Sauvegarder avant de quitter ? (y/n) ").strip().lower()
                    if resp == "y":
                        b = save_json_atomic(json_path, data, make_backup=backup)
                        print(f"[OK] Sauvegardé.{(' Backup: ' + str(b)) if b else ''}")
                return

            if choice in ("b", "back"):
                break

            if choice == "1":
                ch = select_champion_interactive(f)
                if ch is None:
                    continue
                dirty_global = edit_champion(ch) or dirty_global

            elif choice == "2":
                m = select_monster_interactive(f)
                if m is None:
                    continue
                dirty_global = edit_monster(m) or dirty_global

            elif choice == "3":
                dirty_global = edit_faction_meta(f) or dirty_global

            else:
                print("[WARN] choix invalide.")
                continue

            if dirty_global:
                resp = input("Sauvegarder maintenant ? (y/n) ").strip().lower()
                if resp == "y":
                    b = save_json_atomic(json_path, data, make_backup=backup)
                    print(f"[OK] Sauvegardé.{(' Backup: ' + str(b)) if b else ''}")
                    dirty_global = False

        cont = input("Continuer (autre faction) ? (y/n) ").strip().lower()
        if cont != "y":
            break

    if dirty_global:
        resp = input("Changements non sauvegardés. Sauvegarder avant de quitter ? (y/n) ").strip().lower()
        if resp == "y":
            b = save_json_atomic(json_path, data, make_backup=backup)
            print(f"[OK] Sauvegardé.{(' Backup: ' + str(b)) if b else ''}")
        else:
            print("[INFO] Changements ignorés (non sauvegardés).")


# ---------------------------
# Main
# ---------------------------

def main():
    p = argparse.ArgumentParser(description="DDM — Viewer + Admin Editor (Champions + Monstres + Faction)")
    p.add_argument("--json", dest="json_path", default="Data_8_Factions.json", help="Chemin du JSON factions")

    # viewer
    p.add_argument("--faction", default=None, help="Viewer/Edit: id (ex: 3) ou substring nom (viewer)")
    p.add_argument("--letters", default="A,B,C,D,E", help="Viewer: lettres à afficher (CSV), ex: A,B,C")
    p.add_argument("--only-def", action="store_true", help="Viewer: n'affiche que effet_defensif non vide")
    p.add_argument("--compact", action="store_true", help="Viewer: affichage compact")
    p.add_argument("--width", type=int, default=110, help="Largeur terminal (wrap)")
    p.add_argument("--with-visual", action="store_true", help="Viewer: affiche design_visuel")
    p.add_argument("--interactive", action="store_true", help="Viewer: mode interactif")

    # admin
    p.add_argument("--edit", action="store_true", help="Admin: mode édition interactif (avec sauvegarde JSON)")
    p.add_argument("--champion", default=None, help="Admin: pré-sélection champion (A-E)")
    p.add_argument("--monster", default=None, help="Admin: pré-sélection monstre (index '7' ou 'niveau:rang' ex '3:2')")
    p.add_argument("--no-backup", action="store_true", help="Admin: ne crée pas de backup avant save")

    args = p.parse_args()

    args.letters_set = set([s.strip().upper() for s in args.letters.split(",") if s.strip()]) or set(LETTERS_DEFAULT)

    json_path = Path(args.json_path)
    data = load_json(json_path)

    if args.edit:
        editor_loop(
            data,
            json_path,
            backup=(not args.no_backup),
            start_faction=args.faction,
            start_champion=args.champion,
            start_monster=args.monster
        )
        return

    if args.interactive:
        interactive_view_loop(data, args)
        return

    factions = pick_factions(data, args.faction)
    for f in factions:
        print_faction(f, args.letters_set, args.only_def, args.compact, args.width, args.with_visual)

if __name__ == "__main__":
    main()