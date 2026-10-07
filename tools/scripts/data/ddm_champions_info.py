# ddm_champions_tool.py  (v2)
# Viewer + Admin Editor (terminal) pour Data_8_Factions.json
#
# Exemples:
#   python ddm_champions_tool.py --json Data_8_Factions.json
#   python ddm_champions_tool.py --json Data_8_Factions.json --interactive
#   python ddm_champions_tool.py --json Data_8_Factions.json --edit
#   python ddm_champions_tool.py --json Data_8_Factions.json --edit --faction 3 --champion D
#   python ddm_champions_tool.py --where

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
    """
    Set en respectant la clé existante si l'une des clés est déjà présente,
    sinon utilise la 1ère clé préférée.
    """
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

    # tri A..E
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
            desc = _s(_get(ch, "desc", "description", default="")).strip()

            if role:
                print(_wrap("Rôle", role, width=width, indent=4))
            if desc:
                print(_wrap("Desc", desc, width=width, indent=4))
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
    print("\nFactions dispo:")
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

def select_faction_interactive(factions: list[dict]) -> dict | None:
    index = {str(_get(f, "id", default="")): f for f in factions}
    list_factions(factions)
    while True:
        raw = input("Choisis une faction (id) ou 'q': ").strip().lower()
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
        raw = input("Choisis un champion (lettre A/B/C/D/E...) ou 'b' retour: ").strip().upper()
        if raw in ("B", "BACK"):
            return None
        if raw in index:
            return index[raw]
        print("[WARN] lettre invalide.")

def show_champion(ch: dict, width: int = 110):
    print("\n" + "-" * width)
    print(champ_line(ch))
    role = _s(_get(ch, "role", default="")).strip()
    desc = _s(_get(ch, "desc", "description", default="")).strip()
    eff_def = _s(_get(ch, "effet_defensif", "defensive_effect", default="")).strip()
    action = _s(_get(ch, "action_speciale", "special_action", default="")).strip()
    visuel = _s(_get(ch, "design_visuel", "visual_design", default="")).strip()
    stats = _get(ch, "stats", default={})
    if not isinstance(stats, dict):
        stats = {}

    if role:
        print(_wrap("Rôle", role, width=width, indent=2))
    if desc:
        print(_wrap("Desc", desc, width=width, indent=2))
    print(_wrap("Effet_def", eff_def, width=width, indent=2))
    if action:
        print(_wrap("Action", action, width=width, indent=2))
    if visuel:
        print(_wrap("Visuel", visuel, width=width, indent=2))

    print("  Stats:", {k: stats.get(k, None) for k in STATS_KEYS})
    print("-" * width + "\n")

def edit_champion(ch: dict) -> bool:
    dirty = False
    width = 110

    while True:
        show_champion(ch, width=width)
        print("Commandes:")
        print("  1) set name      2) set role      3) set desc")
        print("  4) set effet_def 5) set action    6) set visuel")
        print("  7) edit stats    8) raw set key   9) done/retour")
        cmd = input("> ").strip().lower()

        if cmd in ("9", "done", "return", "retour"):
            return dirty

        if cmd in ("1", "name"):
            cur = _s(_get(ch, "nom", "name", default=""))
            val = input(f"Nouveau nom (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "nom", "name")
            dirty = True

        elif cmd in ("2", "role"):
            cur = _s(_get(ch, "role", default=""))
            val = input(f"Nouveau rôle (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "role")
            dirty = True

        elif cmd in ("3", "desc", "description"):
            cur = _s(_get(ch, "desc", "description", default=""))
            val = input(f"Nouvelle desc (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "desc", "description")
            dirty = True

        elif cmd in ("4", "effet_def", "def"):
            cur = _s(_get(ch, "effet_defensif", "defensive_effect", default=""))
            val = input(f"Nouvel effet_defensif (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "effet_defensif", "defensive_effect")
            dirty = True

        elif cmd in ("5", "action"):
            cur = _s(_get(ch, "action_speciale", "special_action", default=""))
            val = input(f"Nouvelle action_speciale (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "action_speciale", "special_action")
            dirty = True

        elif cmd in ("6", "visuel", "visual"):
            cur = _s(_get(ch, "design_visuel", "visual_design", default=""))
            val = input(f"Nouveau design_visuel (actuel: '{cur}') : ").rstrip("\n")
            _set(ch, val, "design_visuel", "visual_design")
            dirty = True

        elif cmd in ("7", "stats"):
            stats = _get(ch, "stats", default={})
            if not isinstance(stats, dict):
                stats = {}
                _set(ch, stats, "stats")
                dirty = True

            print("Edit stats (laisser vide = ne change pas)")
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

        elif cmd in ("8", "raw", "rawset"):
            print("Raw set: clé EXACTE du dict champion (ex: 'cooldown' ou 'stats.ATK').")
            key = input("  key = ").strip()
            if not key:
                continue
            val = input("  value = ").rstrip("\n")

            if "." in key:
                head, tail = key.split(".", 1)
                if head == "stats":
                    stats = _get(ch, "stats", default={})
                    if not isinstance(stats, dict):
                        stats = {}
                        _set(ch, stats, "stats")
                    v = _safe_int(val)
                    stats[tail] = val if v in (None, "INVALID") else v
                    dirty = True
                else:
                    print("[WARN] Seul 'stats.X' est supporté pour l'instant.")
            else:
                v = _safe_int(val)
                ch[key] = val if v in (None, "INVALID") else v
                dirty = True

        else:
            print("[WARN] commande inconnue.")

def editor_loop(data: dict, json_path: Path, backup: bool, start_faction: str | None, start_champion: str | None):
    factions = data.get("factions", [])
    if not isinstance(factions, list) or not factions:
        print("[ERREUR] Aucune faction trouvée.")
        return

    # pré-sélection si possible
    if start_faction and start_champion and start_faction.strip().isdigit():
        f = select_faction_by_id(factions, int(start_faction.strip()))
        if f:
            ch = select_champion_by_letter(f, start_champion)
            if ch:
                changed = edit_champion(ch)
                if changed:
                    resp = input("Sauvegarder maintenant ? (y/n) ").strip().lower()
                    if resp == "y":
                        b = save_json_atomic(json_path, data, make_backup=backup)
                        print(f"[OK] Sauvegardé.{(' Backup: ' + str(b)) if b else ''}")
                return
            print("[WARN] Champion introuvable pour cette faction, retour menu normal.\n")
        else:
            print("[WARN] Faction introuvable, retour menu normal.\n")

    dirty_global = False

    while True:
        f = select_faction_interactive(factions)
        if f is None:
            break

        while True:
            ch = select_champion_interactive(f)
            if ch is None:
                break

            changed = edit_champion(ch)
            dirty_global = dirty_global or changed

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
    p = argparse.ArgumentParser(description="DDM — Viewer + Admin Editor champions (A→E) par faction")
    p.add_argument("--where", action="store_true", help="Affiche le chemin réel du script exécuté et quitte")

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
    p.add_argument("--edit", action="store_true", help="Admin: mode édition interactif (avec save JSON)")
    p.add_argument("--champion", default=None, help="Admin: pré-sélection champion (A-E)")
    p.add_argument("--no-backup", action="store_true", help="Admin: ne crée pas de backup avant save")

    args = p.parse_args()

    if args.where:
        print(Path(__file__).resolve())
        return

    args.letters_set = set([s.strip().upper() for s in args.letters.split(",") if s.strip()]) or set(LETTERS_DEFAULT)

    json_path = Path(args.json_path)
    data = load_json(json_path)

    if args.edit:
        # en edit, --faction doit être un id (si tu veux pré-sélection)
        editor_loop(
            data,
            json_path,
            backup=(not args.no_backup),
            start_faction=args.faction,
            start_champion=args.champion
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