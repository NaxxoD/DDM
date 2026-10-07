#!/usr/bin/env python3
"""
build_invocation_policy_with_state.py

V2 : comme build_invocation_policy_from_logs, mais on ajoute un 'state' :

    state = "<NomFaction> | <phase>"

où phase ∈ {early, mid, late} selon le numéro de tour du joueur.

On ne garde QUE les décisions des camps marqués comme IA dans
le GAME_SUMMARY (TURNS_IA_A / TURNS_IA_B).
"""

from pathlib import Path
import re
import json
from collections import defaultdict

# TODO : mets ici ton dossier de logs
LOG_DIR = Path(r".\log_data")

OUTPUT_JSON = "ddm_invocation_policy_state.json"


def read_lines(path: Path):
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def parse_winner(lines):
    """Retourne 'A' ou 'B' si on trouve GAME_END: winner=X ..."""
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("GAME_END:"):
            m = re.search(r"winner=([AB])", line)
            if m:
                return m.group(1)
    return None


def detect_roles(lines):
    """
    Déduit le rôle de chaque camp à partir du GAME_SUMMARY.
    Retourne {"A": "ai"/"human"/"unknown", "B": ...}
    """
    roles = {"A": "unknown", "B": "unknown"}
    for line in lines:
        l = line.strip()
        if l.startswith("TURNS_PLAYER_A"):
            roles["A"] = "human"
        if l.startswith("TURNS_PLAYER_B"):
            roles["B"] = "human"
        if l.startswith("TURNS_IA_A"):
            roles["A"] = "ai"
        if l.startswith("TURNS_IA_B"):
            roles["B"] = "ai"
    return roles


def detect_factions(lines):
    """
    Récupère le nom de faction pour A et B à partir des lignes :
      FACTION_A: id=... name=Reptiliens – ... champ=...
      FACTION_B: id=... name=Cyborgs – ... champ=...
    """
    factions = {"A": "Unknown_A", "B": "Unknown_B"}
    for line in lines:
        l = line.strip()
        if l.startswith("FACTION_A:") and "name=" in l:
            part = l.split("name=", 1)[1]
            if " champ=" in part:
                part = part.split(" champ=", 1)[0]
            factions["A"] = part.strip()
        if l.startswith("FACTION_B:") and "name=" in l:
            part = l.split("name=", 1)[1]
            if " champ=" in part:
                part = part.split(" champ=", 1)[0]
            factions["B"] = part.strip()
    return factions


def phase_from_turn(turn_index: int) -> str:
    """
    Découpe le n° de tour du joueur en phase de partie.
    À ajuster si tu veux d'autres seuils.
    """
    if turn_index <= 10:
        return "early"
    elif turn_index <= 25:
        return "mid"
    else:
        return "late"


def extract_samples_with_state(path: Path):
    """
    Extrait les décisions d'invoc IA avec un 'state' enrichi :

      {
        "player": "A"/"B",
        "stars": int,
        "action": "invoke_L2"/"none"/...,
        "winner": "A"/"B",
        "state": "<FactionName>|<phase>",
        "turn_idx": int
      }
    """
    lines = read_lines(path)
    winner = parse_winner(lines)
    if winner not in ("A", "B"):
        # run incomplet ou sans GAME_END
        return []

    roles = detect_roles(lines)
    factions = detect_factions(lines)

    samples = []

    current_player = None
    star_count = 0
    turn_index = {"A": 0, "B": 0}

    for line in lines:
        line = line.strip()

        # Nouveau tour de dés
        if line.startswith("ROLL_START player="):
            # ex: ROLL_START player=A
            current_player = line.split("player=")[1].strip()
            if current_player in ("A", "B"):
                turn_index[current_player] += 1
                star_count = 0

        # Lancers individuels
        elif line.startswith("ROLL "):
            # ex: ROLL A: L4-Rouge-2(L4) -> STAR
            parts = line.split("->")
            if len(parts) == 2:
                face = parts[1].strip()
                if face.startswith("STAR"):
                    star_count += 1

        # Invocation réussie
        elif line.startswith("INVOC_IA:") and current_player in ("A", "B"):
            # On ne garde que si ce camp est IA
            if roles.get(current_player) != "ai":
                continue

            # ex: INVOC_IA: level=2 success=True
            m = re.search(r"level=(\d+)", line)
            if m:
                level = int(m.group(1))
                action = f"invoke_L{level}"
            else:
                action = "invoke"

            t_idx = turn_index[current_player]
            phase = phase_from_turn(t_idx)
            state_tag = f"{factions[current_player]}|{phase}"

            samples.append({
                "player": current_player,
                "stars": star_count,
                "action": action,
                "winner": winner,
                "state": state_tag,
                "turn_idx": t_idx,
            })

        # Pas d'invocation (INVOC_NONE)
        elif line.startswith("INVOC_NONE"):
            # ex: INVOC_NONE player=B stars=1
            m_player = re.search(r"player=([AB])", line)
            m_stars = re.search(r"stars=(\d+)", line)
            pl = m_player.group(1) if m_player else current_player
            st = int(m_stars.group(1)) if m_stars else star_count

            if pl in ("A", "B"):
                if roles.get(pl) != "ai":
                    continue

                t_idx = turn_index[pl]
                phase = phase_from_turn(t_idx)
                state_tag = f"{factions[pl]}|{phase}"

                samples.append({
                    "player": pl,
                    "stars": st,
                    "action": "none",
                    "winner": winner,
                    "state": state_tag,
                    "turn_idx": t_idx,
                })

    return samples


def main():
    if not LOG_DIR.exists():
        print(f"[ERREUR] Dossier introuvable : {LOG_DIR}")
        return

    log_files = sorted(LOG_DIR.rglob("*.log"))
    if not log_files:
        print(f"[INFO] Aucun .log trouvé dans {LOG_DIR}")
        return

    print(f"[INFO] {len(log_files)} log(s) à analyser.\n")

    all_samples = []
    for log_path in log_files:
        s = extract_samples_with_state(log_path)
        if s:
            print(f"[OK] {log_path.name}: {len(s)} décision(s) IA d'invoc (avec state)")
            all_samples.extend(s)
        else:
            print(f"[INFO] {log_path.name}: aucune décision IA exploitable")

    if not all_samples:
        print("\n[INFO] Aucun sample trouvé, rien à analyser.")
        return

    # Agrégation : (state, stars, action) -> stats
    stats = defaultdict(lambda: {"count": 0, "wins": 0})

    for sm in all_samples:
        state = sm["state"]
        stars = sm["stars"]
        action = sm["action"]
        player = sm["player"]
        winner = sm["winner"]

        key = (state, stars, action)
        stats[key]["count"] += 1
        if player == winner:
            stats[key]["wins"] += 1

    # Affichage
    print("\n=== POLICY INVOCATION (IA, par state=faction+phase) ===")
    rows = []
    for (state, stars, action), d in stats.items():
        c = d["count"]
        w = d["wins"]
        winrate = w / c if c > 0 else 0.0
        rows.append((state, stars, action, c, w, winrate))

    rows.sort(key=lambda r: (r[0], r[1], r[2]))

    for state, stars, action, c, w, winrate in rows:
        print(f"- state={state} | stars={stars:2d} | action={action:10s} | "
              f"n={c:4d} | wins={w:4d} | winrate={winrate:5.2f}")

    # JSON : state -> "stars::action" -> stats
    policy_state = {}
    for state, stars, action, c, w, winrate in rows:
        sa_key = f"{stars}::{action}"
        if state not in policy_state:
            policy_state[state] = {}
        policy_state[state][sa_key] = {
            "stars": stars,
            "action": action,
            "count": c,
            "wins": w,
            "winrate": winrate,
        }

    out_path = LOG_DIR / OUTPUT_JSON
    out_path.write_text(json.dumps(policy_state, indent=2), encoding="utf-8")
    print(f"\n[OK] Policy IA (avec state) écrite dans : {out_path}")


if __name__ == "__main__":
    main()
