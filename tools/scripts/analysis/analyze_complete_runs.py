#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Proto_DDM Complete Runs Analyzer (patch-agnostic)
- Scans .log files
- Extracts run timestamp, factions, winner, HQ HP, turns, remaining units/dice
- Counts feature markers (POISON_, ZONE_, DASH_END_TURN, TRAP_, HQ_DMG_)
- Exports:
    runs_summary.csv
    daily_summary.csv
    feature_summary.csv

Usage (Windows):
  python analyze_complete_runs.py --dir ".\logs\log_data\complete_runs" --out ".\logs\log_data\analysis"

If --out is omitted, it writes next to --dir (./analysis).

Option 1 â€” PowerShell (recommandÃ©)
$csv = Import-Csv ".\logs\log_data\analysis\runs_summary.csv"
$csv | Where-Object { $_.run_date -eq "2025-12-21" } |
  Export-Csv ".\logs\log_data\analysis\runs_2025-12-21.csv" -NoTypeInformation -Encoding UTF8

  Option 2 - CMD
  python ".\logs\log_data\analysis\analyze_complete_runs.py" --dir ".\logs\log_data\complete_runs"  --out ".\logs\log_data\analysis"
"""

from __future__ import annotations
import argparse
import csv
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple, List


RUN_HDR_RE = re.compile(r"^#\s*Proto_DDM\s+run\s+(\d{8}_\d{6})\s*$", re.M)
FILENAME_TS_RE = re.compile(r"(\d{8}_\d{6})")
GAME_END_RE = re.compile(r"^GAME_END:\s*winner=([AB]|None|Draw)\b(?:\s+reason=([^\n\r]+))?", re.M)

# Summary keys (some may be missing depending on patch)
KEY_INT_PATTERNS = {
    "turns_a": re.compile(r"^TURNS_PLAYER_A:\s*(-?\d+)\s*$", re.M),
    "turns_b": re.compile(r"^TURNS_IA_B:\s*(-?\d+)\s*$", re.M),
    "hq_a_hp": re.compile(r"^HQ_A_HP:\s*(-?\d+)\s*$", re.M),
    "hq_b_hp": re.compile(r"^HQ_B_HP:\s*(-?\d+)\s*$", re.M),
    "units_a_remaining": re.compile(r"^UNITS_A_REMAINING:\s*(-?\d+)\s*$", re.M),
    "units_b_remaining": re.compile(r"^UNITS_B_REMAINING:\s*(-?\d+)\s*$", re.M),
    "dice_a_remaining": re.compile(r"^DICE_A_REMAINING:\s*(-?\d+)\s*$", re.M),
    "dice_b_remaining": re.compile(r"^DICE_B_REMAINING:\s*(-?\d+)\s*$", re.M),
}

# Faction line is sometimes truncated with "..." inside, so keep it simple
FACTION_A_RE = re.compile(r"^FACTION_A:\s*id=(\d+)\s+name=([^#\n\r]+?)\s+champ=", re.M)
FACTION_B_RE = re.compile(r"^FACTION_B:\s*id=(\d+)\s+name=([^#\n\r]+?)\s+champ=", re.M)

# Feature markers (patch-agnostic)
MARKERS = {
    "poison_apply": "POISON_APPLY",
    "poison_tick": "POISON_TICK",
    "poison_expire": "POISON_EXPIRE",
    "zone_create": "ZONE_CREATE",
    "zone_tick": "ZONE_TICK",
    "zone_expire": "ZONE_EXPIRE",
    "dash_end_turn": "DASH_END_TURN",
    "trap_any": "TRAP_",
    "hq_dmg_a": "HQ_DMG_A",
    "hq_dmg_b": "HQ_DMG_B",
}


@dataclass
class RunRow:
    file: str
    run_id: str
    run_dt: str
    run_date: str

    winner: str
    reason: str

    faction_a_id: str
    faction_a_name: str
    faction_b_id: str
    faction_b_name: str

    turns_a: str
    turns_b: str
    hq_a_hp: str
    hq_b_hp: str
    units_a_remaining: str
    units_b_remaining: str
    dice_a_remaining: str
    dice_b_remaining: str

    poison_apply: int
    poison_tick: int
    poison_expire: int
    zone_create: int
    zone_tick: int
    zone_expire: int
    dash_end_turn: int
    trap_any: int
    hq_dmg_a: int
    hq_dmg_b: int

    lines: int
    features: str


def _last_match_group(pattern: re.Pattern, text: str, group: int = 1) -> Optional[str]:
    m = None
    for m in pattern.finditer(text):
        pass
    return m.group(group).strip() if m else None


def _parse_run_id(text: str, file_path: Path) -> str:
    # 1) header
    rid = _last_match_group(RUN_HDR_RE, text, 1)
    if rid:
        return rid
    # 2) filename
    m = FILENAME_TS_RE.search(file_path.stem)
    if m:
        return m.group(1)
    # 3) mtime fallback
    dt = datetime.fromtimestamp(file_path.stat().st_mtime)
    return dt.strftime("%Y%m%d_%H%M%S")


def _parse_dt(run_id: str) -> datetime:
    # run_id is YYYYMMDD_HHMMSS
    return datetime.strptime(run_id, "%Y%m%d_%H%M%S")


def _parse_factions(text: str) -> Tuple[str, str, str, str]:
    fa_id = fa_name = fb_id = fb_name = ""
    ma = FACTION_A_RE.search(text)
    if ma:
        fa_id = ma.group(1).strip()
        fa_name = ma.group(2).strip()
    mb = FACTION_B_RE.search(text)
    if mb:
        fb_id = mb.group(1).strip()
        fb_name = mb.group(2).strip()
    return fa_id, fa_name, fb_id, fb_name


def _parse_winner(text: str) -> Tuple[str, str]:
    w = "?"
    r = ""
    # pick last GAME_END
    m_last = None
    for m in GAME_END_RE.finditer(text):
        m_last = m
    if m_last:
        w = (m_last.group(1) or "?").strip()
        r = (m_last.group(2) or "").strip()
    # normalize
    if w == "None":
        w = "None"
    if w == "Draw":
        w = "Draw"
    return w, r


def _parse_summary_ints(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, pat in KEY_INT_PATTERNS.items():
        v = _last_match_group(pat, text, 1)
        out[key] = v if v is not None else ""
    return out


def _count_marker(text: str, marker: str) -> int:
    # line-based for TRAP_ to avoid counting "TRAP_" in random contexts
    if marker == "TRAP_":
        return sum(1 for ln in text.splitlines() if "TRAP_" in ln)
    return text.count(marker)


def _compute_features(counts: Dict[str, int]) -> str:
    # Compact feature signature to compare mixed patches:
    feats = []
    if counts.get("poison_apply", 0) or counts.get("poison_tick", 0) or counts.get("poison_expire", 0):
        feats.append("POISON")
    if counts.get("zone_create", 0) or counts.get("zone_tick", 0) or counts.get("zone_expire", 0):
        feats.append("ZONES")
    if counts.get("dash_end_turn", 0):
        feats.append("DASH")
    if counts.get("trap_any", 0):
        feats.append("TRAPS")
    # Always include HQ damage markers if present (helps detect older formats)
    if counts.get("hq_dmg_a", 0) or counts.get("hq_dmg_b", 0):
        feats.append("HQDMG")
    return "+".join(feats) if feats else "BASE"


def parse_one_log(file_path: Path) -> RunRow:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    run_id = _parse_run_id(text, file_path)
    run_dt = _parse_dt(run_id)

    fa_id, fa_name, fb_id, fb_name = _parse_factions(text)
    winner, reason = _parse_winner(text)
    summary = _parse_summary_ints(text)

    counts = {k: _count_marker(text, v) for k, v in MARKERS.items()}
    features = _compute_features(counts)
    lines = len(text.splitlines())

    return RunRow(
        file=str(file_path),
        run_id=run_id,
        run_dt=run_dt.isoformat(sep=" "),
        run_date=run_dt.date().isoformat(),

        winner=winner,
        reason=reason,

        faction_a_id=fa_id,
        faction_a_name=fa_name,
        faction_b_id=fb_id,
        faction_b_name=fb_name,

        turns_a=summary.get("turns_a", ""),
        turns_b=summary.get("turns_b", ""),
        hq_a_hp=summary.get("hq_a_hp", ""),
        hq_b_hp=summary.get("hq_b_hp", ""),
        units_a_remaining=summary.get("units_a_remaining", ""),
        units_b_remaining=summary.get("units_b_remaining", ""),
        dice_a_remaining=summary.get("dice_a_remaining", ""),
        dice_b_remaining=summary.get("dice_b_remaining", ""),

        poison_apply=counts["poison_apply"],
        poison_tick=counts["poison_tick"],
        poison_expire=counts["poison_expire"],
        zone_create=counts["zone_create"],
        zone_tick=counts["zone_tick"],
        zone_expire=counts["zone_expire"],
        dash_end_turn=counts["dash_end_turn"],
        trap_any=counts["trap_any"],
        hq_dmg_a=counts["hq_dmg_a"],
        hq_dmg_b=counts["hq_dmg_b"],

        lines=lines,
        features=features,
    )


def scan_logs(root: Path, recursive: bool = True, pattern: str = "*.log") -> List[Path]:
    if recursive:
        return sorted(root.rglob(pattern))
    return sorted(root.glob(pattern))


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def agg_daily(runs: List[RunRow]) -> List[dict]:
    # Per date: counts + winrates
    by_date: Dict[str, dict] = {}
    for rr in runs:
        d = rr.run_date
        by_date.setdefault(d, {
            "date": d,
            "runs": 0,
            "A_wins": 0,
            "B_wins": 0,
            "Draw": 0,
            "None": 0,
        })
        by_date[d]["runs"] += 1
        if rr.winner == "A":
            by_date[d]["A_wins"] += 1
        elif rr.winner == "B":
            by_date[d]["B_wins"] += 1
        elif rr.winner == "Draw":
            by_date[d]["Draw"] += 1
        elif rr.winner == "None":
            by_date[d]["None"] += 1

    out = []
    for d in sorted(by_date.keys()):
        row = by_date[d]
        runs_n = row["runs"] or 1
        row["A_winrate"] = round(row["A_wins"] / runs_n, 4)
        row["B_winrate"] = round(row["B_wins"] / runs_n, 4)
        out.append(row)
    return out


def agg_features(runs: List[RunRow]) -> List[dict]:
    by_feat: Dict[str, dict] = {}
    for rr in runs:
        f = rr.features
        by_feat.setdefault(f, {"features": f, "runs": 0, "A_wins": 0, "B_wins": 0, "Draw": 0, "None": 0})
        by_feat[f]["runs"] += 1
        if rr.winner == "A":
            by_feat[f]["A_wins"] += 1
        elif rr.winner == "B":
            by_feat[f]["B_wins"] += 1
        elif rr.winner == "Draw":
            by_feat[f]["Draw"] += 1
        elif rr.winner == "None":
            by_feat[f]["None"] += 1

    out = []
    for f in sorted(by_feat.keys(), key=lambda x: (-by_feat[x]["runs"], x)):
        row = by_feat[f]
        n = row["runs"] or 1
        row["A_winrate"] = round(row["A_wins"] / n, 4)
        row["B_winrate"] = round(row["B_wins"] / n, 4)
        out.append(row)
    return out


def print_report(runs: List[RunRow]) -> None:
    if not runs:
        print("No runs found.")
        return

    runs_sorted = sorted(runs, key=lambda r: r.run_id)
    first = runs_sorted[0]
    last = runs_sorted[-1]

    total = len(runs_sorted)
    A = sum(1 for r in runs_sorted if r.winner == "A")
    B = sum(1 for r in runs_sorted if r.winner == "B")
    D = sum(1 for r in runs_sorted if r.winner == "Draw")
    N = sum(1 for r in runs_sorted if r.winner in ("None", "?"))

    print("=== Proto_DDM Runs Report ===")
    print(f"Runs: {total}")
    print(f"Range: {first.run_id} -> {last.run_id}")
    print(f"Wins A: {A} ({A/total:.2%}) | Wins B: {B} ({B/total:.2%}) | Draw: {D} | Unknown/None: {N}")

    # Daily snapshot
    daily = agg_daily(runs_sorted)
    print("\n--- Daily winrates (last 10 days shown) ---")
    for row in daily[-10:]:
        print(f"{row['date']}  runs={row['runs']:>3}  A={row['A_wins']:>3} ({row['A_winrate']:.0%})  B={row['B_wins']:>3} ({row['B_winrate']:.0%})")

    # Feature snapshot
    feat = agg_features(runs_sorted)
    print("\n--- By detected features ---")
    for row in feat:
        print(f"{row['features']:<20} runs={row['runs']:>3}  A={row['A_wins']:>3} ({row['A_winrate']:.0%})  B={row['B_wins']:>3} ({row['B_winrate']:.0%})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze Proto_DDM complete run logs (patch-agnostic).")
    ap.add_argument("--dir", required=True, help="Directory containing .log files (complete_runs).")
    ap.add_argument("--out", default="", help="Output directory (default: <dir>/analysis).")
    ap.add_argument("--pattern", default="*.log", help="Glob pattern (default: *.log).")
    ap.add_argument("--no-recursive", action="store_true", help="Disable recursive scan.")
    args = ap.parse_args()

    root = Path(args.dir)
    if not root.exists():
        print(f"[ERR] Directory not found: {root}")
        return 2

    out_dir = Path(args.out) if args.out else root / "analysis"
    logs = scan_logs(root, recursive=not args.no_recursive, pattern=args.pattern)

    runs: List[RunRow] = []
    for fp in logs:
        try:
            runs.append(parse_one_log(fp))
        except Exception as e:
            print(f"[WARN] Failed to parse {fp}: {e}")

    if not runs:
        print("[ERR] No runs parsed.")
        return 1

    # Write runs_summary.csv
    runs_rows = [asdict(r) for r in runs]
    runs_csv = out_dir / "runs_summary.csv"
    write_csv(runs_csv, runs_rows, fieldnames=list(runs_rows[0].keys()))

    # Write daily_summary.csv
    daily = agg_daily(runs)
    daily_csv = out_dir / "daily_summary.csv"
    write_csv(daily_csv, daily, fieldnames=list(daily[0].keys()))

    # Write feature_summary.csv
    feat = agg_features(runs)
    feat_csv = out_dir / "feature_summary.csv"
    write_csv(feat_csv, feat, fieldnames=list(feat[0].keys()))

    print_report(runs)
    print(f"\n[OK] Wrote:\n - {runs_csv}\n - {daily_csv}\n - {feat_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

