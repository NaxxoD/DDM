#!/usr/bin/env python3
"""
build_invocation_policy_from_logs.py

Analyse les logs DDM pour extraire une 'policy' simple :
pour un nombre d'Ã©toiles donnÃ©, quand l'IA choisit
d'invoquer (et Ã  quel niveau) ou de ne rien faire,
quel est son taux de victoire ?

Les logs doivent contenir des lignes comme :
  ROLL_START player=A
  ROLL A: L4-Rouge-2(L4) -> STAR
  INVOC_IA: level=3 success=True
  INVOC_NONE player=B stars=1
  GAME_END: winner=B reason=...
  # GAME_SUMMARY
  TURNS_PLAYER_A: 60
  TURNS_IA_B: 60

âš ï¸ V2 : on ne garde QUE les dÃ©cisions des camps marquÃ©s comme IA
dans le GAME_SUMMARY (IA vs IA ou IA dans humain vs IA).
"""

from pathlib import Path
import re
import json
from collections import defaultdict

# TODO: mets ici le dossier qui contient tes .log
# Exemple :
# LOG_DIR = Path(r".\logs")
LOG_DIR = Path(r".\logs\log_data\complete_runs")

# Si tu veux Ã©crire la policy dans un JSON :
OUTPUT_JSON = "ddm_invocation_policy.json"


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
    DÃ©duit le rÃ´le de chaque camp Ã  partir du GAME_SUMMARY.
    Retourne un dict comme : {"A": "ai"/"human"/"unknown", "B": ...}

    Exemples de lignes :
      TURNS_PLAYER_A: 60
      TURNS_IA_B: 60
    """
    roles = {"A": "unknown", "B": "unknown"}
    for line in lines:
        line = line.strip()
        if line.startswith("TURNS_PLAYER_A"):
            roles["A"] = "human"
        if line.startswith("TURNS_PLAYER_B"):
            roles["B"] = "human"
        if line.startswith("TURNS_IA_A"):
            roles["A"] = "ai"
        if line.startswith("TURNS_IA_B"):
            roles["B"] = "ai"
    return roles


def extract_samples_from_log(path: Path):
    """
    Extrait les dÃ©cisions d'invocation depuis un log :
    retourne une liste de dicts :
      {"player": "A"/"B", "stars": int, "action": str, "winner": "A"/"B"}

    V2 : ne garde que les dÃ©cisions des camps dont le rÃ´le == "ai".
    """
    lines = read_lines(path)
    winner = parse_winner(lines)
    if winner not in ("A", "B"):
        # run incomplet ou sans GAME_END -> on ignore pour l'apprentissage
        return []

    roles = detect_roles(lines)

    samples = []

    current_player = None
    star_count = 0

    for line in lines:
        line = line.strip()

        # Nouveau tour de dÃ©s
        if line.startswith("ROLL_START player="):
            # ex: ROLL_START player=A
            current_player = line.split("player=")[1].strip()
            star_count = 0

        # Lancers individuels
        elif line.startswith("ROLL "):
            # ex: ROLL A: L4-Rouge-2(L4) -> STAR
            parts = line.split("->")
            if len(parts) == 2:
                face = parts[1].strip()
                if face.startswith("STAR"):
                    star_count += 1

        # Invocation rÃ©ussie par l'IA
        elif line.startswith("INVOC_IA:") and current_player in ("A", "B"):
            # On ne garde que si le joueur courant est marquÃ© comme IA
            if roles.get(current_player) != "ai":
                continue

            # ex: INVOC_IA: level=3 success=True
            m = re.search(r"level=(\d+)", line)
            if m:
                level = int(m.group(1))
                action = f"invoke_L{level}"
            else:
                action = "invoke"

            samples.append({
                "player": current_player,
                "stars": star_count,
                "action": action,
                "winner": winner,
            })

        # Pas d'invocation
        elif line.startswith("INVOC_NONE"):
            # ex: INVOC_NONE player=B stars=1
            m_player = re.search(r"player=([AB])", line)
            m_stars = re.search(r"stars=(\d+)", line)
            pl = m_player.group(1) if m_player else current_player
            st = int(m_stars.group(1)) if m_stars else star_count

            if pl in ("A", "B"):
                # On ne garde que si ce camp est IA
                if roles.get(pl) != "ai":
                    continue

                samples.append({
                    "player": pl,
                    "stars": st,
                    "action": "none",
                    "winner": winner,
                })

    return samples


def main():
    if not LOG_DIR.exists():
        print(f"[ERREUR] Dossier introuvable : {LOG_DIR}")
        return

    log_files = sorted(LOG_DIR.rglob("*.log"))
    if not log_files:
        print(f"[INFO] Aucun .log trouvÃ© dans {LOG_DIR}")
        return

    print(f"[INFO] {len(log_files)} log(s) Ã  analyser.\n")

    all_samples = []
    for log_path in log_files:
        s = extract_samples_from_log(log_path)
        if s:
            print(f"[OK] {log_path.name}: {len(s)} dÃ©cision(s) IA d'invoc extraite(s)")
            all_samples.extend(s)
        else:
            print(f"[INFO] {log_path.name}: aucune dÃ©cision IA exploitable")

    if not all_samples:
        print("\n[INFO] Aucun sample trouvÃ©, rien Ã  analyser.")
        return

    # AgrÃ©gation : (stars, action) -> stats
    stats = defaultdict(lambda: {"count": 0, "wins": 0})

    for sm in all_samples:
        player = sm["player"]
        winner = sm["winner"]
        stars = sm["stars"]
        action = sm["action"]

        key = (stars, action)

        stats[key]["count"] += 1
        if player == winner:
            stats[key]["wins"] += 1

    # Affichage triÃ©
    print("\n=== POLICY INVOCATION (IA uniquement) ===")
    rows = []
    for (stars, action), d in stats.items():
        c = d["count"]
        w = d["wins"]
        winrate = w / c if c > 0 else 0.0
        rows.append((stars, action, c, w, winrate))

    rows.sort(key=lambda r: (r[0], r[1]))

    for stars, action, c, w, winrate in rows:
        print(f"- stars={stars:2d} | action={action:10s} | "
              f"n={c:4d} | wins={w:4d} | winrate={winrate:5.2f}")

    # Option : dump JSON
    policy = {}
    for stars, action, c, w, winrate in rows:
        key = f"{stars}::{action}"
        policy[key] = {
            "stars": stars,
            "action": action,
            "count": c,
            "wins": w,
            "winrate": winrate,
        }

    out_path = LOG_DIR / OUTPUT_JSON
    out_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    print(f"\n[OK] Policy IA Ã©crite dans : {out_path}")


if __name__ == "__main__":
    main()

