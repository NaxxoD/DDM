# build_shape_policy_with_state.py
# Analyse les placements de shapes (anchor/shape/rot/cells) depuis les logs.
# Sort un JSON exploitable + un rÃ©sumÃ© console.
#
# IMPORTANT: ton code actuel ne log pas les SHAPE_*.
# Il faut ajouter un log dans attempt_place_human() et attempt_place_ai()
# (voir notes en bas).

from __future__ import annotations
import json
import re
from pathlib import Path
from collections import defaultdict

# --- Defaults (adapted for your Proto_DDM folder) ---
DEFAULT_LOG_DIR = Path(r".\logs\log_data")
DEFAULT_OUT_DIR = DEFAULT_LOG_DIR / "output_policies"

def ensure_out_dir() -> Path:
    """Create output dir and return it."""
    DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_OUT_DIR

# ---------- Helpers communs (copiÃ©s/esprit build_invocation_policy_with_state.py) ----------

WIN_RE_1 = re.compile(r"\bWINNER\b\s*[:=]\s*([AB])\b")
WIN_RE_2 = re.compile(r"\bVICTOIRE\s+([AB])\b", re.IGNORECASE)

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
    # "ai" / "human" si prÃ©sent dans GAME_SUMMARY
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

# ---------- Parse SHAPE logs ----------
# Format attendu (Ã  logguer chez toi) :
# SHAPE_A: lvl=3 shape=2 rot=1 anchor=(18,6) cells=[(18,6),(17,6)...]
SHAPE_RE = re.compile(
    r"^SHAPE_([AB]):\s*lvl=(\d+)\s+shape=(\d+)\s+rot=(\d+)\s+anchor=\((\-?\d+),(\-?\d+)\)\s+cells=(.*)$"
)

CELL_RE = re.compile(r"\((\-?\d+)\s*,\s*(\-?\d+)\)")

def parse_cells(s: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in CELL_RE.findall(s)]

def scan_log_for_shapes(path: Path, include_incomplete: bool, include_human: bool) -> list[dict]:
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

        m = SHAPE_RE.match(line)
        if not m:
            continue

        pl = m.group(1)
        lvl = int(m.group(2))
        shape_idx = int(m.group(3))
        rot = int(m.group(4))
        ar = int(m.group(5))
        ac = int(m.group(6))
        cells_str = m.group(7)
        cells = parse_cells(cells_str)

        # filtre humain/IA
        if not include_human:
            if roles.get(pl) != "ai":
                continue

        t_idx = turn_index.get(pl, 0)
        st = f"{factions[pl]}|{phase_from_turn(t_idx)}"

        # mÃ©triques simples (style â€œprogress_scoreâ€)
        rows = [r for (r, _c) in cells] if cells else [ar]
        if pl == "A":
            progress_score = -min(rows)   # comme attempt_place_ai (A)
        else:
            progress_score = max(rows)    # comme attempt_place_ai (B)

        samples.append({
            "log": path.name,
            "player": pl,
            "winner": winner,     # peut Ãªtre None si run incomplÃ¨te
            "turn_idx": t_idx,
            "state": st,
            "lvl": lvl,
            "shape": shape_idx,
            "rot": rot,
            "anchor": [ar, ac],
            "cells_n": len(cells),
            "progress_score": float(progress_score),
        })

    return samples

def agg_shapes(samples: list[dict]) -> dict:
    # state -> key -> stats
    out = defaultdict(lambda: defaultdict(lambda: {
        "n": 0,
        "wins": 0,
        "winrate": None,
        "avg_progress": 0.0,
        "avg_cells": 0.0,
    }))

    for s in samples:
        st = s["state"]
        key = f"Lv{s['lvl']}::S{s['shape']}::R{s['rot']}"
        rec = out[st][key]
        rec["n"] += 1
        rec["avg_progress"] += s["progress_score"]
        rec["avg_cells"] += s["cells_n"]

        w = s.get("winner")
        if w in ("A", "B") and w == s["player"]:
            rec["wins"] += 1

    # finalize
    for st, d in out.items():
        for key, rec in d.items():
            n = rec["n"]
            rec["avg_progress"] = round(rec["avg_progress"] / n, 4) if n else 0.0
            rec["avg_cells"] = round(rec["avg_cells"] / n, 4) if n else 0.0
            if n:
                rec["winrate"] = round(rec["wins"] / n, 4)
    return out

def main():
    print("=== Build Shape Policy (with state) ===")
    log_dir_in = input(r"Dossier logs (Enter = .\logs\log_data) : ").strip()
    log_dir = Path(log_dir_in) if log_dir_in else DEFAULT_LOG_DIR

    include_incomplete = input("Inclure runs incomplÃ¨tes ? (o/N) : ").strip().lower() == "o"
    include_human = input("Inclure placements humains ? (o/N) : ").strip().lower() == "o"

    out_json = input("Nom JSON output (Enter = ddm_shape_policy_state.json) : ").strip() or "ddm_shape_policy_state.json"
    out_dir = ensure_out_dir()
    out_path = out_dir / out_json

    logs = sorted(list(log_dir.rglob("run_*.log")))
    if not logs:
        print(f"[WARN] Aucun run_*.log trouvÃ© dans {log_dir}")
        print("       -> JSON vide quand mÃªme (pour tracer le chemin de sortie).")
        logs = []

    all_samples = []
    for p in logs:
        all_samples.extend(scan_log_for_shapes(p, include_incomplete, include_human))

    if not all_samples:
        print("[WARN] 0 sample SHAPE trouvÃ©. (Normal si tu n'as pas encore loggÃ© SHAPE_*)")
        print("       -> JSON vide quand mÃªme (policy vide).")
        policy = {}
    else:
        policy = agg_shapes(all_samples)

    payload = {
        "meta": {
            "log_dir": str(log_dir),
            "logs_count": len(logs),
            "samples": len(all_samples),
            "include_incomplete": include_incomplete,
            "include_human": include_human,
        },
        "shape_policy_by_state": policy,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] JSON Ã©crit : {out_path}")
    print(f"     samples={len(all_samples)} states={len(policy)}")

if __name__ == "__main__":
    main()
