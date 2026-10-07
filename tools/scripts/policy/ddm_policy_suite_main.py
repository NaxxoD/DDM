#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ddm_policy_suite_main.py

Un seul "main" qui lit tes logs et gÃ©nÃ¨re (dâ€™un coup) les 4 policies actuelles :
1) Invocation (simple) -> ddm_invocation_policy.json
2) Invocation + state  -> ddm_invocation_policy_state.json
3) Movement + state    -> ddm_move_policy_state.json
4) Shape placement     -> ddm_shape_policy_state.json (peut Ãªtre vide si pas de SHAPE_* dans les logs)

Objectif : Ã©viter de lancer 4 scripts Ã  la main, et centraliser les sorties.

USAGE (simple) :
  python ddm_policy_suite_main.py

USAGE (avec chemins custom) :
  python ddm_policy_suite_main.py --root "." --include-human --include-incomplete --progress-every 250

Par dÃ©faut, il cherche :
  <root>\log_data\complete_runs
  <root>\log_data\incomplete_runs
et Ã©crit dans :
  <root>\log_data\output_policies
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------
# Regex utiles (robustes)
# ---------------------------

# Winner / fin de partie
WIN_RE_1 = re.compile(r"\bWINNER\b\s*[:=]\s*([AB])\b")
WIN_RE_2 = re.compile(r"\bwinner\s*=\s*([AB])\b", re.IGNORECASE)
WIN_RE_3 = re.compile(r"\bIA cÃ´tÃ©\s+([AB])\s+gagne\b", re.IGNORECASE)
WIN_RE_4 = re.compile(r"\bVICTOIRE\s+([AB])\b", re.IGNORECASE)
END_QG_RE_A = re.compile(r"^QG A dÃ©truit", re.IGNORECASE)
END_QG_RE_B = re.compile(r"^QG B dÃ©truit", re.IGNORECASE)

# Factions / game summary (si prÃ©sent)
FACTION_A_RE = re.compile(r"^FACTION_A\s*[:=]\s*(.+)$")
FACTION_B_RE = re.compile(r"^FACTION_B\s*[:=]\s*(.+)$")
TURNS_IA_A_RE = re.compile(r"^TURNS_IA_A\s*[:=]\s*(\d+)\b")
TURNS_IA_B_RE = re.compile(r"^TURNS_IA_B\s*[:=]\s*(\d+)\b")

# ROLL / stars (plusieurs formats)
ROLL_STAR_RE = re.compile(r"^ROLL\s+([AB])\s*:.*->\s*STAR\b", re.IGNORECASE)
STARS_DETECTED_RE = re.compile(r"(\d+)\s+Ã©toiles\s+dÃ©tectÃ©es", re.IGNORECASE)
POOL_STAR_RE = re.compile(r"\bSTAR\s*=\s*(\d+)\b", re.IGNORECASE)

# Invocation (formats "policy")
INVOC_IA_RE = re.compile(r"^INVOC_IA:\s*level=(\d+)\s+success=(True|False)\b")
INVOC_IA_ALT_RE = re.compile(r"^INVOKE_IA:\s*level=(\d+)\b", re.IGNORECASE)
INVOC_NONE_RE = re.compile(r"^INVOC_NONE\b.*\bplayer=([AB])\b.*\bstars=(\d+)\b", re.IGNORECASE)

# Un fallback "humain" (console) : "Invoquer une crÃ©ature de niveau X ?"
HUMAN_INVOC_Q_RE = re.compile(r"^Invoquer une crÃ©ature de niveau\s+(\d+)\s*\?\s*\(O/N\)", re.IGNORECASE)
HUMAN_INVOC_IGNORED_RE = re.compile(r"Invocation\s+ignorÃ©e\.", re.IGNORECASE)

# Movement
MOVE_AI_RE = re.compile(
    r"^MOVE_([AB]):\s*unit=(.*?)\s+from=\(\s*(\-?\d+)\s*,\s*(\-?\d+)\s*\)\s+to=\(\s*(\-?\d+)\s*,\s*(\-?\d+)\s*\)"
)
MOVE_HUMAN_RE = re.compile(
    r"^MOVE\s+([AB])\s*:\s*(.*?)\s+from=\(\s*(\-?\d+)\s*,\s*(\-?\d+)\s*\)\s+to=\(\s*(\-?\d+)\s*,\s*(\-?\d+)\s*\)",
    re.IGNORECASE
)

# Shape placement
SHAPE_RE = re.compile(
    r"^SHAPE_([AB]):\s*lvl=(\d+)\s*idx=(\d+)\s*rot=(\d+)\s*anchor=\((\-?\d+),(\-?\d+)\)\s*cells=\[(.*)\]\s*$"
)


# ---------------------------
# Structures
# ---------------------------

@dataclass
class LogMeta:
    path: Path
    is_complete: bool
    winner: Optional[str]  # "A"/"B"/None
    factions: Dict[str, str]  # {"A": "...", "B": "..."}
    roles: Dict[str, str]     # {"A": "ai"/"human"/"unknown", ...}


# ---------------------------
# Helpers Ã©tat / phase
# ---------------------------

def phase_from_turn(turn_index: int) -> str:
    # mÃªmes seuils que la V2 (faciles Ã  ajuster plus tard)
    if turn_index <= 10:
        return "early"
    elif turn_index <= 25:
        return "mid"
    return "late"

def forward_sign_for_side(player: str) -> int:
    # Convention la plus courante dans tes discussions :
    # A avance "vers le bas" ? -> ici on garde le modÃ¨le de la policy existante :
    return -1 if player == "A" else 1



# ---------------------------
# Utilitaires robustes
# ---------------------------

_INT_RE = re.compile(r"-?\d+")

def safe_int(v, default=None):
    """Convertit v en int de faÃ§on tolÃ©rante.
    - accepte int/float('3.0')/str('3')/str('stars=3')
    - si rien de convertible -> default
    """
    if isinstance(v, int):
        return v
    if v is None:
        return default
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        return default
    s = str(v).strip()
    m = _INT_RE.search(s)
    if not m:
        return default
    try:
        return int(m.group(0))
    except Exception:
        return default

# ---------------------------
# Lecture + meta extraction
# ---------------------------

def detect_winner_and_complete(lines: List[str]) -> Tuple[Optional[str], bool]:
    winner = None
    complete = False

    for line in lines:
        line = line.strip()

        # winner
        for rex in (WIN_RE_1, WIN_RE_2, WIN_RE_3, WIN_RE_4):
            m = rex.search(line)
            if m:
                winner = m.group(1).upper()
                # winner => souvent fin de partie, mais pas toujours
        # end
        if END_QG_RE_A.search(line) or END_QG_RE_B.search(line):
            complete = True

        if "GAME_END" in line or "GAME_SUMMARY" in line:
            # ces marqueurs arrivent gÃ©nÃ©ralement en fin
            # on n'auto-complete pas sans QG/winner, mais Ã§a aide
            pass

    # Si winner explicite, on peut considÃ©rer "complete" si on a un marqueur clair de fin
    if winner and complete:
        return winner, True

    # Si winner explicite mais pas de "QG dÃ©truit", on accepte quand mÃªme comme complÃ¨te
    # (cas oÃ¹ la fin est loggÃ©e diffÃ©remment)
    if winner:
        return winner, True

    return None, complete


def extract_summary_meta(lines: List[str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    factions = {"A": "unknown", "B": "unknown"}
    roles = {"A": "unknown", "B": "unknown"}

    in_summary = False
    for raw in lines:
        line = raw.strip()

        if line.startswith("# GAME_SUMMARY") or line.startswith("GAME_SUMMARY") or line.startswith("=== GAME_SUMMARY"):
            in_summary = True
            continue

        if in_summary:
            if line.startswith("#") and "END_SUMMARY" in line:
                break

            m = FACTION_A_RE.match(line)
            if m:
                factions["A"] = m.group(1).strip()
                continue
            m = FACTION_B_RE.match(line)
            if m:
                factions["B"] = m.group(1).strip()
                continue

            m = TURNS_IA_A_RE.match(line)
            if m:
                roles["A"] = "ai" if int(m.group(1)) > 0 else "human"
                continue
            m = TURNS_IA_B_RE.match(line)
            if m:
                roles["B"] = "ai" if int(m.group(1)) > 0 else "human"
                continue

    return factions, roles



HUMAN_PROMPT_MARKERS = (
    'Id de faction',
    'Entrez les indices',
    'Choix :',
    'Appuyez',
    'Entrer un nombre',
)

def infer_roles_fallback(lines: list[str], roles: dict) -> dict:
    """
    Quand les logs n'ont pas d'info 'HUMAN_SIDE' / mode, on Ã©vite de jeter la moitiÃ© des dÃ©cisions.
    - Si on voit des prompts humains -> on suppose A=humain, B=IA.
    - Sinon -> IA vs IA (A et B IA).
    """
    if not isinstance(roles, dict) or not roles:
        roles = {'A': 'unknown', 'B': 'unknown'}
    if all(str(roles.get(s, 'unknown')) == 'unknown' for s in ('A','B')):
        joined = '\n'.join(lines)
        has_human_prompt = any(m in joined for m in HUMAN_PROMPT_MARKERS)
        if has_human_prompt:
            return {'A': 'human', 'B': 'ai'}
        return {'A': 'ai', 'B': 'ai'}
    return roles

def load_log_meta(path: Path) -> Tuple[List[str], LogMeta]:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    lines = txt.splitlines()

    winner, complete = detect_winner_and_complete(lines)
    factions, roles = extract_summary_meta(lines)
    roles = infer_roles_fallback(lines, roles)

    meta = LogMeta(
        path=path,
        is_complete=bool(complete),
        winner=winner,
        factions=factions,
        roles=roles,
    )
    return lines, meta


# ---------------------------
# Policy 1 : Invocation simple
# ---------------------------

def scan_invocation_simple(lines: List[str], meta: LogMeta, include_incomplete: bool, include_human: bool) -> List[dict]:
    samples: List[dict] = []
    winner = meta.winner if meta.is_complete else None

    # star_count par joueur, reset sur ROLL_START si prÃ©sent
    stars = {"A": 0, "B": 0}
    current_player: Optional[str] = None

    # fallback : quand on voit "X Ã©toiles dÃ©tectÃ©es", on lâ€™applique au joueur courant
    for raw in lines:
        line = raw.strip()

        # dÃ©tecte joueur courant pour les prompts console
        if "Joueur A" in line and "Lancer de dÃ©s" in line:
            current_player = "A"
        elif "Joueur B" in line and "Lancer de dÃ©s" in line:
            current_player = "B"

        m = re.search(r"ROLL_START\s+player=([AB])", line)
        if m:
            current_player = m.group(1)
            stars[current_player] = 0
            continue

        m = ROLL_STAR_RE.match(line)
        if m:
            pl = m.group(1)
            stars[pl] += 1
            current_player = pl
            continue

        m = STARS_DETECTED_RE.search(line)
        if m and current_player in ("A", "B"):
            try:
                stars[current_player] = int(m.group(1))
            except ValueError:
                pass

        # --- INVOC formats structurÃ©s ---
        m = INVOC_IA_RE.match(line)
        if m:
            pl = current_player  # souvent alignÃ© avec le tour courant
            if pl not in ("A", "B"):
                # si pas sÃ»r, on ignore
                continue

            if not include_human and meta.roles.get(pl) != "ai":
                continue
            if (not include_incomplete) and (not meta.is_complete):
                continue

            lvl = int(m.group(1))
            success = (m.group(2) == "True")
            action = f"invoke_L{lvl}" if success else f"invoke_L{lvl}_fail"

            samples.append({
                "player": pl,
                "stars": stars.get(pl, 0),
                "action": action,
                "winner": winner,  # None si incomplet
            })
            continue

        m = INVOC_NONE_RE.match(line)
        if m:
            pl = m.group(1)
            st = int(m.group(2))

            if not include_human and meta.roles.get(pl) != "ai":
                continue
            if (not include_incomplete) and (not meta.is_complete):
                continue

            samples.append({
                "player": pl,
                "stars": st,
                "action": "none",
                "winner": winner,
            })
            continue

        # --- fallback console humain (optionnel) ---
        m = HUMAN_INVOC_Q_RE.match(line)
        if m and current_player in ("A", "B"):
            pl = current_player
            lvl = int(m.group(1))

            if not include_human and meta.roles.get(pl) != "ai":
                continue
            if (not include_incomplete) and (not meta.is_complete):
                continue

            # on attend la ligne "Invocation ignorÃ©e." ou autre
            # si on ne la voit pas, on tag "asked"
            samples.append({
                "player": pl,
                "stars": stars.get(pl, 0),
                "action": f"asked_L{lvl}",
                "winner": winner,
            })
            continue

        if HUMAN_INVOC_IGNORED_RE.search(line) and current_player in ("A", "B"):
            pl = current_player
            if not include_human and meta.roles.get(pl) != "ai":
                continue
            if (not include_incomplete) and (not meta.is_complete):
                continue

            samples.append({
                "player": pl,
                "stars": stars.get(pl, 0),
                "action": "none",
                "winner": winner,
            })

    return samples


def build_invocation_simple_policy(samples: List[dict]) -> dict:
    # On sÃ©pare "complete" vs "incomplete" automatiquement via winner=None
    stats_complete = defaultdict(lambda: {"count": 0, "wins": 0})
    stats_all = defaultdict(lambda: {"count": 0})

    for s in samples:
        stars = safe_int(s.get("stars", 0), default=None)
        if stars is None:
            continue
        action = s.get("action", "unknown")
        pl = s.get("player", "?")
        key = f"{pl}|{stars}|{action}"

        stats_all[key]["count"] += 1

        winner = s.get("winner")
        if winner in ("A", "B"):
            stats_complete[key]["count"] += 1
            if winner == pl:
                stats_complete[key]["wins"] += 1

    policy = {}
    for key, d_all in stats_all.items():
        pl, stars, action = key.split("|", 2)

        stars_i = safe_int(stars, default=None)

        if stars_i is None:

            # cas rare : logs corrompus / anciens formats

            continue
        c_all = d_all["count"]
        d_c = stats_complete.get(key, {"count": 0, "wins": 0})
        c = d_c["count"]
        w = d_c["wins"]
        winrate = (w / c) if c > 0 else None

        policy[key] = {
            "player": pl,
            "stars": stars_i,
            "action": action,
            "count_all": c_all,       # complete + incomplete
            "count_complete": c,      # seulement complete
            "wins": w,                # seulement complete
            "winrate": winrate,       # None si pas assez de completes
        }

    return policy


# ---------------------------
# Policy 2 : Invocation + state (faction|phase)
# ---------------------------

def scan_invocation_with_state(lines: List[str], meta: LogMeta, include_incomplete: bool, include_human: bool) -> List[dict]:
    samples: List[dict] = []
    winner = meta.winner if meta.is_complete else None

    stars = {"A": 0, "B": 0}
    turn_idx = {"A": 0, "B": 0}
    current_player: Optional[str] = None

    def state_tag(pl: str) -> str:
        fac = meta.factions.get(pl, "unknown")
        ph = phase_from_turn(turn_idx.get(pl, 0))
        return f"{fac} | {ph}"

    for raw in lines:
        line = raw.strip()

        m = re.search(r"ROLL_START\s+player=([AB])", line)
        if m:
            current_player = m.group(1)
            stars[current_player] = 0
            turn_idx[current_player] += 1
            continue

        m = ROLL_STAR_RE.match(line)
        if m:
            pl = m.group(1)
            stars[pl] += 1
            current_player = pl
            continue

        m = STARS_DETECTED_RE.search(line)
        if m and current_player in ("A", "B"):
            try:
                stars[current_player] = int(m.group(1))
            except ValueError:
                pass

        # INVOC_IA (structurÃ©)
        m = INVOC_IA_RE.match(line)
        if m and current_player in ("A", "B"):
            pl = current_player
            if not include_human and meta.roles.get(pl) != "ai":
                continue
            if (not include_incomplete) and (not meta.is_complete):
                continue

            lvl = int(m.group(1))
            success = (m.group(2) == "True")
            action = f"invoke_L{lvl}" if success else f"invoke_L{lvl}_fail"

            samples.append({
                "player": pl,
                "stars": stars.get(pl, 0),
                "action": action,
                "winner": winner,
                "state": state_tag(pl),
                "turn_idx": turn_idx.get(pl, 0),
            })
            continue

        # INVOC_NONE (structurÃ©)
        m = INVOC_NONE_RE.match(line)
        if m:
            pl = m.group(1)
            st = int(m.group(2))
            if not include_human and meta.roles.get(pl) != "ai":
                continue
            if (not include_incomplete) and (not meta.is_complete):
                continue

            samples.append({
                "player": pl,
                "stars": st,
                "action": "none",
                "winner": winner,
                "state": state_tag(pl),
                "turn_idx": turn_idx.get(pl, 0),
            })
            continue

    return samples


def build_invocation_state_policy(samples: List[dict]) -> dict:
    stats = defaultdict(lambda: {"count": 0, "wins": 0})

    for s in samples:
        state = s.get("state", "unknown")
        pl = s.get("player", "?")
        stars = safe_int(s.get("stars", 0), default=None)
        if stars is None:
            continue
        action = s.get("action", "unknown")
        key = f"{state}|{pl}|{stars}|{action}"

        stats[key]["count"] += 1
        winner = s.get("winner")
        if winner in ("A", "B") and winner == pl:
            stats[key]["wins"] += 1

    policy = defaultdict(dict)
    for key, d in stats.items():
        state, pl, stars, action = key.split("|", 3)

        stars_i = safe_int(stars, default=None)

        if stars_i is None:

            continue
        c = d["count"]
        w = d["wins"]
        policy[state][f"{pl}::{stars}::{action}"] = {
            "player": pl,
            "stars": stars_i,
            "action": action,
            "count": c,
            "wins": w,
            "winrate": (w / c) if c > 0 else None,
        }

    return dict(policy)


# ---------------------------
# Policy 3 : Movement + state (copie lÃ©gÃ¨re de ton script)
# ---------------------------

def scan_moves(lines: List[str], meta: LogMeta, include_incomplete: bool, include_human: bool) -> List[dict]:
    samples: List[dict] = []

    winner = meta.winner if meta.is_complete else None

    turn_idx = {"A": 0, "B": 0}
    current_player: Optional[str] = None

    def state_tag(pl: str) -> str:
        fac = meta.factions.get(pl, "unknown")
        ph = phase_from_turn(turn_idx.get(pl, 0))
        return f"{fac} | {ph}"

    for raw in lines:
        line = raw.strip()

        m = re.search(r"ROLL_START\s+player=([AB])", line)
        if m:
            current_player = m.group(1)
            turn_idx[current_player] += 1
            continue

        # MOVE_ (IA) / MOVE (humain)
        m = MOVE_AI_RE.match(line)
        human = False
        if not m:
            m = MOVE_HUMAN_RE.match(line)
            human = True

        if not m:
            continue

        pl = m.group(1)
        unit = m.group(2).strip()
        fr, fc = int(m.group(3)), int(m.group(4))
        tr, tc = int(m.group(5)), int(m.group(6))

        if not include_human and human:
            continue
        if (not include_incomplete) and (not meta.is_complete):
            continue

        # si on veut exclure humains par rÃ´le (si summary le sait)
        if not include_human and meta.roles.get(pl) == "human":
            continue

        dy = tr - fr
        dx = tc - fc
        fsign = forward_sign_for_side(pl)
        dfwd = dy * fsign  # >0 = avance vers l'ennemi

        samples.append({
            "player": pl,
            "unit": unit,
            "from": [fr, fc],
            "to": [tr, tc],
            "dy": dy,
            "dx": dx,
            "dfwd": dfwd,
            "winner": winner,
            "state": state_tag(pl),
            "turn_idx": turn_idx.get(pl, 0),
        })

    return samples


def build_move_policy(samples: List[dict]) -> dict:
    # buckets simples : forward / back / side / stay
    def bucket(dfwd: int, dx: int, dy: int) -> str:
        if dx == 0 and dy == 0:
            return "stay"
        if dfwd > 0:
            return "forward"
        if dfwd < 0:
            return "back"
        return "side"

    stats = defaultdict(lambda: {"count": 0, "wins": 0})

    for s in samples:
        state = s.get("state", "unknown")
        pl = s.get("player", "?")
        b = bucket(int(s.get("dfwd", 0)), int(s.get("dx", 0)), int(s.get("dy", 0)))
        key = f"{state}|{pl}|{b}"

        stats[key]["count"] += 1
        winner = s.get("winner")
        if winner in ("A", "B") and winner == pl:
            stats[key]["wins"] += 1

    policy = defaultdict(dict)
    for key, d in stats.items():
        state, pl, b = key.split("|", 2)
        c = d["count"]
        w = d["wins"]
        policy[state][f"{pl}::{b}"] = {
            "player": pl,
            "bucket": b,
            "count": c,
            "wins": w,
            "winrate": (w / c) if c > 0 else None,
        }

    return dict(policy)


# ---------------------------
# Policy 4 : Shape placement + state
# ---------------------------

def parse_cells(cells_str: str) -> List[Tuple[int,int]]:
    # cells_str: "(r,c),(r,c),..."
    out = []
    parts = [p.strip() for p in cells_str.split("),") if p.strip()]
    for p in parts:
        p = p.strip().lstrip("(").rstrip(")").strip()
        if not p:
            continue
        if "," not in p:
            continue
        a, b = p.split(",", 1)
        try:
            out.append((int(a.strip()), int(b.strip())))
        except ValueError:
            pass
    return out

def scan_shapes(lines: List[str], meta: LogMeta, include_incomplete: bool, include_human: bool) -> List[dict]:
    samples: List[dict] = []
    winner = meta.winner if meta.is_complete else None

    turn_idx = {"A": 0, "B": 0}
    current_player: Optional[str] = None

    def state_tag(pl: str) -> str:
        fac = meta.factions.get(pl, "unknown")
        ph = phase_from_turn(turn_idx.get(pl, 0))
        return f"{fac} | {ph}"

    for raw in lines:
        line = raw.strip()

        m = re.search(r"ROLL_START\s+player=([AB])", line)
        if m:
            current_player = m.group(1)
            turn_idx[current_player] += 1
            continue

        m = SHAPE_RE.match(line)
        if not m:
            continue

        pl = m.group(1)
        lvl = int(m.group(2))
        shape_idx = int(m.group(3))
        rot = int(m.group(4))
        ar = int(m.group(5))
        ac = int(m.group(6))
        cells = parse_cells(m.group(7))

        if not include_human and meta.roles.get(pl) == "human":
            continue
        if (not include_incomplete) and (not meta.is_complete):
            continue

        samples.append({
            "player": pl,
            "lvl": lvl,
            "shape_idx": shape_idx,
            "rot": rot,
            "anchor": [ar, ac],
            "cells": [[r,c] for (r,c) in cells],
            "winner": winner,
            "state": state_tag(pl),
            "turn_idx": turn_idx.get(pl, 0),
        })

    return samples

def build_shape_policy(samples: List[dict]) -> dict:
    stats = defaultdict(lambda: {"count": 0, "wins": 0})

    for s in samples:
        state = s.get("state", "unknown")
        pl = s.get("player", "?")
        lvl = int(s.get("lvl", 0))
        idx = int(s.get("shape_idx", -1))
        rot = int(s.get("rot", 0))
        key = f"{state}|{pl}|L{lvl}|idx{idx}|rot{rot}"

        stats[key]["count"] += 1
        winner = s.get("winner")
        if winner in ("A","B") and winner == pl:
            stats[key]["wins"] += 1

    policy = defaultdict(dict)
    for key, d in stats.items():
        state, pl, Llvl, idx, rot = key.split("|", 4)
        c = d["count"]
        w = d["wins"]
        policy[state][f"{pl}::{Llvl}::{idx}::{rot}"] = {
            "player": pl,
            "level": int(Llvl.lstrip("L")),
            "shape_idx": int(idx.lstrip("idx")),
            "rot": int(rot.lstrip("rot")),
            "count": c,
            "wins": w,
            "winrate": (w / c) if c > 0 else None,
        }

    return dict(policy)


# ---------------------------
# MAIN
# ---------------------------

def collect_logs(complete_dir: Path, incomplete_dir: Path) -> Tuple[List[Path], List[Path]]:
    complete = sorted(list(complete_dir.rglob("run_*.log")))
    incomplete = sorted(list(incomplete_dir.rglob("run_*.log")))
    return complete, incomplete


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r".", help="Racine projet (ex: .)")
    ap.add_argument("--include-incomplete", action="store_true", help="Inclure les logs incomplets dans les stats de frÃ©quence")
    ap.add_argument("--include-human", action="store_true", help="Inclure aussi les actions humaines (si dÃ©tectables)")
    ap.add_argument("--progress-every", type=int, default=300, help="Affiche une progression toutes les N logs")
    args = ap.parse_args()

    root = Path(args.root)
    log_data = root / "log_data"
    complete_dir = log_data / "complete_runs"
    incomplete_dir = log_data / "incomplete_runs"
    out_dir = log_data / "output_policies"
    out_dir.mkdir(parents=True, exist_ok=True)

    complete_logs, incomplete_logs = collect_logs(complete_dir, incomplete_dir)
    all_logs = complete_logs + (incomplete_logs if args.include_incomplete else [])

    if not complete_logs and not all_logs:
        print("[ERREUR] Aucun run_*.log trouvÃ©.")
        print("  Attendu :", complete_dir)
        print("  (et)    :", incomplete_dir)
        return

    print("=== DDM Policy Suite ===")
    print(f"Root             : {root}")
    print(f"Complete logs    : {len(complete_logs)}")
    print(f"Incomplete logs  : {len(incomplete_logs)} (pris en compte={args.include_incomplete})")
    print(f"Output dir       : {out_dir}")
    print(f"Include human    : {args.include_human}")
    print("")

    # Accumulateurs
    inv_simple_samples: List[dict] = []
    inv_state_samples: List[dict] = []
    move_samples: List[dict] = []
    shape_samples: List[dict] = []

    # meta count
    meta_counts = {"complete": 0, "incomplete": 0, "winner_known": 0}

    for i, path in enumerate(all_logs, 1):
        try:
            lines, meta = load_log_meta(path)
        except Exception as e:
            # on ne crash pas la suite
            continue

        if meta.is_complete:
            meta_counts["complete"] += 1
        else:
            meta_counts["incomplete"] += 1
        if meta.winner in ("A","B"):
            meta_counts["winner_known"] += 1

        inv_simple_samples.extend(scan_invocation_simple(lines, meta, args.include_incomplete, args.include_human))
        inv_state_samples.extend(scan_invocation_with_state(lines, meta, args.include_incomplete, args.include_human))
        move_samples.extend(scan_moves(lines, meta, args.include_incomplete, args.include_human))
        shape_samples.extend(scan_shapes(lines, meta, args.include_incomplete, args.include_human))

        if args.progress_every > 0 and (i % args.progress_every == 0):
            print(f"[...] {i}/{len(all_logs)} logs | inv={len(inv_simple_samples)} inv_state={len(inv_state_samples)} move={len(move_samples)} shape={len(shape_samples)}")

    # Build policies
    inv_simple_policy = build_invocation_simple_policy(inv_simple_samples)
    inv_state_policy = build_invocation_state_policy(inv_state_samples)
    move_policy = build_move_policy(move_samples)
    shape_policy = build_shape_policy(shape_samples)

    # Write
    out_inv_simple = out_dir / "ddm_invocation_policy.json"
    out_inv_state = out_dir / "ddm_invocation_policy_state.json"
    out_move = out_dir / "ddm_move_policy_state.json"
    out_shape = out_dir / "ddm_shape_policy_state.json"

    write_json(out_inv_simple, inv_simple_policy)
    write_json(out_inv_state, inv_state_policy)
    write_json(out_move, {"meta": {"samples": len(move_samples), "logs": len(all_logs)}, "move_policy_by_state": move_policy})
    write_json(out_shape, {"meta": {"samples": len(shape_samples), "logs": len(all_logs)}, "shape_policy_by_state": shape_policy})

    suite_report = {
        "meta": {
            "logs_total": len(all_logs),
            "logs_complete": len(complete_logs),
            "logs_incomplete": len(incomplete_logs),
            "include_incomplete": args.include_incomplete,
            "include_human": args.include_human,
            "meta_counts": meta_counts,
        },
        "outputs": {
            "invocation_simple": str(out_inv_simple),
            "invocation_state": str(out_inv_state),
            "movement_state": str(out_move),
            "shape_state": str(out_shape),
        },
        "samples": {
            "invocation_simple": len(inv_simple_samples),
            "invocation_state": len(inv_state_samples),
            "movement": len(move_samples),
            "shape": len(shape_samples),
        },
        "states_count": {
            "invocation_state": len(inv_state_policy),
            "movement_state": len(move_policy),
            "shape_state": len(shape_policy),
        }
    }
    write_json(out_dir / "policy_suite_report.json", suite_report)

    print("\n=== OK ===")
    print("Ã‰crits dans :", out_dir)
    print(" - ddm_invocation_policy.json")
    print(" - ddm_invocation_policy_state.json")
    print(" - ddm_move_policy_state.json")
    print(" - ddm_shape_policy_state.json")
    print(" - policy_suite_report.json")
    print("")
    print("RÃ©sumÃ© samples :", suite_report["samples"])
    print("RÃ©sumÃ© states  :", suite_report["states_count"])


if __name__ == "__main__":
    main()
