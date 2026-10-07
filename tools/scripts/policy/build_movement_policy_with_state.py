# build_movement_policy_with_state.py
# Analyse les déplacements depuis les logs (MOVE_A / MOVE_B et MOVE A / MOVE B).
# Sort un JSON (stats par state + global).

from __future__ import annotations
import json
import re
from pathlib import Path
from collections import defaultdict

WIN_RE_1 = re.compile(r"\bWINNER\b\s*[:=]\s*([AB])\b")
WIN_RE_2 = re.compile(r"\bVICTOIRE\s+([AB])\b", re.IGNORECASE)

MOVE_AI_RE = re.compile(
    r"^MOVE_([AB]):\s*unit=(.*?)\s+from=\(\s*(\-?\d+)\s*,\s*(\-?\d+)\s*\)\s+to=\(\s*(\-?\d+)\s*,\s*(\-?\d+)\s*\)"
)
MOVE_HUM_RE = re.compile(
    r"^MOVE\s+([AB]):\s*unit=(.*?)\s+from=\(\s*(\-?\d+)\s*,\s*(\-?\d+)\s*\)\s+to=\(\s*(\-?\d+)\s*,\s*(\-?\d+)\s*\)"
)

def read_lines(p: Path) -> list[str]:
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

def parse_winner(lines: list[str]) -> str | None:
    for line in reversed(lines):
        m = WIN_RE_1.search(line)
        if m:
            return m.group(1)
        m = WIN_RE_2.search(line)
        if m:
            return m.group(1).upper()
    return None

def detect_roles(lines: list[str]) -> dict[str, str]:
    roles = {"A": "unknown", "B": "unknown"}
    for line in lines:
        l = line.strip()
        if l.startswith("TURNS_IA_A"):
            roles["A"] = "ai"
        elif l.startswith("TURNS_HUMAN_A"):
            roles["A"] = "human"
        elif l.startswith("TURNS_IA_B"):
            roles["B"] = "ai"
        elif l.startswith("TURNS_HUMAN_B"):
            roles["B"] = "human"
    return roles

def detect_factions(lines: list[str]) -> dict[str, str]:
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
    if turn_index <= 10:
        return "early"
    elif turn_index <= 25:
        return "mid"
    else:
        return "late"

def forward_sign_for_side(side: str) -> int:
    # d'après create_board(): B en haut (row 0), A en bas (row HEIGHT-1)
    # Donc avancer pour A = dy négatif ; avancer pour B = dy positif
    return -1 if side == "A" else +1

def scan_log_for_moves(path: Path, include_incomplete: bool, include_human: bool) -> list[dict]:
    lines = read_lines(path)
    winner = parse_winner(lines)
    if (winner is None) and (not include_incomplete):
        return []

    roles = detect_roles(lines)
    factions = detect_factions(lines)

    turn_index = {"A": 0, "B": 0}
    current_player = None

    samples: list[dict] = []

    for raw in lines:
        line = raw.strip()

        if line.startswith("ROLL_START player="):
            current_player = line.split("player=")[1].strip()
            if current_player in ("A", "B"):
                turn_index[current_player] += 1

        m = MOVE_AI_RE.match(line) or MOVE_HUM_RE.match(line)
        if not m:
            continue

        pl = m.group(1)
        unit = m.group(2).strip()
        fr, fc = int(m.group(3)), int(m.group(4))
        tr, tc = int(m.group(5)), int(m.group(6))

        if not include_human:
            if roles.get(pl) != "ai":
                continue

        dy = tr - fr
        dx = tc - fc
        fsign = forward_sign_for_side(pl)
        dfwd = dy * fsign  # >0 = avance vers l'ennemi

        t_idx = turn_index.get(pl, 0)
        st = f"{factions[pl]}|{phase_from_turn(t_idx)}"

        kind = "forward" if dfwd > 0 else ("back" if dfwd < 0 else "side")
        step = "jump" if abs(dy) >= 2 else "step"

        samples.append({
            "log": path.name,
            "player": pl,
            "winner": winner,
            "turn_idx": t_idx,
            "state": st,
            "unit": unit,
            "dy": dy,
            "dx": dx,
            "dfwd": dfwd,
            "kind": kind,
            "step": step,
        })

    return samples

def agg_moves(samples: list[dict]) -> dict:
    out = defaultdict(lambda: defaultdict(lambda: {
        "n": 0,
        "wins": 0,
        "winrate": None,
        "forward": 0,
        "back": 0,
        "side": 0,
        "jump": 0,
        "step": 0,
        "avg_dfwd": 0.0,
        "avg_absdy": 0.0,
    }))

    for s in samples:
        st = s["state"]
        key = "ALL_MOVES"
        rec = out[st][key]
        rec["n"] += 1
        rec[s["kind"]] += 1
        rec[s["step"]] += 1
        rec["avg_dfwd"] += s["dfwd"]
        rec["avg_absdy"] += abs(s["dy"])

        w = s.get("winner")
        if w in ("A", "B") and w == s["player"]:
            rec["wins"] += 1

    for st, d in out.items():
        for key, rec in d.items():
            n = rec["n"]
            rec["avg_dfwd"] = round(rec["avg_dfwd"] / n, 4) if n else 0.0
            rec["avg_absdy"] = round(rec["avg_absdy"] / n, 4) if n else 0.0
            if n:
                rec["winrate"] = round(rec["wins"] / n, 4)
    return out

def main():
    print("=== Build Movement Policy (with state) ===")
    log_dir_in = input("Dossier logs (Enter = ./log_data) : ").strip()
    log_dir = Path(log_dir_in) if log_dir_in else Path.cwd() / "log_data"

    include_incomplete = input("Inclure runs incomplètes ? (o/N) : ").strip().lower() == "o"
    include_human = input("Inclure moves humains ? (o/N) : ").strip().lower() == "o"

    out_json = input("Nom JSON output (Enter = ddm_move_policy_state.json) : ").strip() or "ddm_move_policy_state.json"
    out_path = log_dir / out_json

    logs = sorted(list(log_dir.rglob("run_*.log")))
    if not logs:
        print(f"[WARN] Aucun run_*.log trouvé dans {log_dir}")
        return

    all_samples = []
    for p in logs:
        all_samples.extend(scan_log_for_moves(p, include_incomplete, include_human))

    if not all_samples:
        print("[WARN] 0 MOVE sample trouvé.")
        print("       Vérifie que tes logs contiennent MOVE_A:/MOVE_B: ou MOVE A:/MOVE B:.")
        return

    policy = agg_moves(all_samples)
    payload = {
        "meta": {
            "log_dir": str(log_dir),
            "logs_count": len(logs),
            "samples": len(all_samples),
            "include_incomplete": include_incomplete,
            "include_human": include_human,
        },
        "move_policy_by_state": policy,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] JSON écrit : {out_path}")
    print(f"     samples={len(all_samples)} states={len(policy)}")

if __name__ == "__main__":
    main()