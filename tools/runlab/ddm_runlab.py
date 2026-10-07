#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Proto_DDM RunLab (stdout + .log compatible) — v6

New vs v5 (v6):
- Paired sideflip check now includes *directional* counts (decisive pairs only):
    A->A, A->B, B->A, B->B
  for:
    base vs sideflip
    mirror vs mirror_sideflip
  Also prints a small 'net' tilt: (A->B - B->A)

Still includes:
- Robust CSV column mapping for fa/fb (faction ids)
- Parses end-of-game info from SUMMARY_END / GAME_END, or French stdout summary, or QG destroyed strings
- Forces reason=max_rounds to draw (winner=D)
- Outcomes by variant + sideflip aggregate + faction winrate

Usage (CMD):
  python ddm_runlab.py --logs-dir ".\logs\autorun_log_data" ^
    --runid-from 20260226_000725_00001 ^
    --runid-to   20260226_000725_00004 ^
    --max-rounds 120

  # Avec sessions HvIA fusionnées:
  python ddm_runlab.py --logs-dir ".\logs\autorun_log_data" ^
    --logs-dir-hvia ".\logs\log_data" ^
    --runid-from 20260226_000725_00001 ^
    --runid-to   20260226_000725_00004 ^
    --max-rounds 120

Usage (PowerShell): use backticks for line continuation.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, List, DefaultDict
from collections import defaultdict

FILE_RE = re.compile(r"^run_(?P<runid>\d{8}_\d{6}_\d{5})\.(?P<kind>stdout\.log|log)$", re.IGNORECASE)

RE_GAME_END = re.compile(r"\bGAME_END\b.*\bwinner=(?P<w>[ABD\?])\b.*\breason=(?P<reason>[A-Za-z0-9_]+)\b", re.IGNORECASE)
RE_SUMMARY_END = re.compile(r"\bSUMMARY_END\b.*\bwinner=(?P<w>[ABD\?])\b.*\brounds=(?P<rounds>\d+)\b.*\breason=(?P<reason>[A-Za-z0-9_]+)\b", re.IGNORECASE)

RE_QG_A_DESTROYED = re.compile(r"\bQG\s*A\s*d[Ã©e]truit\b", re.IGNORECASE)
RE_QG_B_DESTROYED = re.compile(r"\bQG\s*B\s*d[Ã©e]truit\b", re.IGNORECASE)

RE_TOURS_A = re.compile(r"^\s*Tours\s+Joueur\s+A\s*:\s*(?P<n>\d+)\s*$", re.IGNORECASE)
RE_TOURS_B = re.compile(r"^\s*Tours\s+(?:IA|Joueur)\s+B\s*:\s*(?P<n>\d+)\s*$", re.IGNORECASE)
RE_QG_A_HP = re.compile(r"^\s*QG\s*A\s*HP\s*:\s*(?P<hp>-?\d+)\s*/\s*(?P<max>\d+)\s*$", re.IGNORECASE)
RE_QG_B_HP = re.compile(r"^\s*QG\s*B\s*HP\s*:\s*(?P<hp>-?\d+)\s*/\s*(?P<max>\d+)\s*$", re.IGNORECASE)
RE_ROUND_HEADER = re.compile(r"^\s*\[\s*Tour\s+(?P<n>\d+)\s*-\s*Joueur\s+(?P<seat>[AB])\s*\]\s*$", re.IGNORECASE)

@dataclass
class CsvMeta:
    runid: str
    variant: str = ""
    seed: str = ""
    start: str = ""
    fa: str = ""
    fb: str = ""

@dataclass
class RunResult:
    runid: str
    winner: str = "?"
    reason: str = "unknown"
    rounds: int = 0
    complete: bool = False
    file_path: str = ""
    variant: str = ""
    seed: str = ""
    start: str = ""
    fa: str = ""
    fb: str = ""

def _pick_latest_csv(logs_dir: Path) -> Optional[Path]:
    """Cherche dans logs_dir/csv/ puis logs_dir/ (layout autorun_log_data)."""
    for search_dir in [logs_dir / "csv", logs_dir]:
        cands = sorted(search_dir.glob("auto_runs_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if cands:
            return cands[0]
    return None


def _resolve_log_dir(logs_dir: Path) -> Path:
    """Résout le dossier .log effectif selon la structure détectée.
    - autorun_log_data/log/  → sous-dossier log/
    - log_data/log/          → idem
    - sinon : logs_dir lui-même
    """
    sub = logs_dir / "log"
    if sub.exists():
        return sub
    return logs_dir

def _first_present(row: dict, keys: List[str]) -> str:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s != "":
            return s
    return ""

def load_csv_meta(csv_path: Path) -> Dict[str, CsvMeta]:
    meta: Dict[str, CsvMeta] = {}
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = _first_present(row, ["run_id", "runid", "id", "run", "runId"])
            if not rid:
                continue

            variant = _first_present(row, ["variant", "mode", "flip_variant"])
            seed    = _first_present(row, ["seed", "rng_seed"])
            start   = _first_present(row, ["start", "start_policy", "starter", "start_seat"])

            # Robust fa/fb extraction (schema drift friendly)
            fa = _first_present(row, ["fa", "fa_id", "faction_a", "factionA", "faction_a_id", "A_faction", "factionA_id"])
            fb = _first_present(row, ["fb", "fb_id", "faction_b", "factionB", "faction_b_id", "B_faction", "factionB_id"])

            meta[rid] = CsvMeta(runid=rid, variant=variant, seed=seed, start=start, fa=fa, fb=fb)
    return meta

def parse_run_file(path: Path, max_rounds: int) -> Tuple[str, str, int]:
    winner, reason, rounds = "?", "unknown", 0
    tours_a = tours_b = None
    qg_a_hp = qg_b_hp = None
    last_round_seen = 0

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ("?", "read_error", 0)

    # Prefer canonical markers if present
    for line in text.splitlines():
        m = RE_SUMMARY_END.search(line)
        if m:
            winner = m.group("w").upper()
            reason = m.group("reason")
            rounds = int(m.group("rounds"))
            break

    if rounds == 0:
        for line in text.splitlines():
            m = RE_GAME_END.search(line)
            if m:
                winner = m.group("w").upper()
                reason = m.group("reason")
                break

    # Stdout heuristics
    for line in text.splitlines():
        if RE_QG_A_DESTROYED.search(line):
            winner, reason = "B", "HQ_DESTROYED"
        if RE_QG_B_DESTROYED.search(line):
            winner, reason = "A", "HQ_DESTROYED"

        mh = RE_ROUND_HEADER.match(line)
        if mh:
            try:
                last_round_seen = max(last_round_seen, int(mh.group("n")))
            except Exception:
                pass

        if tours_a is None:
            ma = RE_TOURS_A.match(line)
            if ma:
                tours_a = int(ma.group("n"))
        if tours_b is None:
            mb = RE_TOURS_B.match(line)
            if mb:
                tours_b = int(mb.group("n"))
        if qg_a_hp is None:
            mqa = RE_QG_A_HP.match(line)
            if mqa:
                qg_a_hp = int(mqa.group("hp"))
        if qg_b_hp is None:
            mqb = RE_QG_B_HP.match(line)
            if mqb:
                qg_b_hp = int(mqb.group("hp"))

    # Infer rounds
    if rounds == 0:
        if (tours_a is not None) or (tours_b is not None):
            rounds = max(tours_a or 0, tours_b or 0)
        elif last_round_seen > 0:
            rounds = last_round_seen

    # Infer winner from HP if still unknown
    if winner == "?" and qg_a_hp is not None and qg_b_hp is not None:
        if qg_a_hp <= 0 < qg_b_hp:
            winner, reason = "B", "HQ_DESTROYED"
        elif qg_b_hp <= 0 < qg_a_hp:
            winner, reason = "A", "HQ_DESTROYED"
        elif qg_a_hp <= 0 and qg_b_hp <= 0:
            winner, reason = "D", "DOUBLE_KO"

    # Normalize max_rounds => draw
    if reason.lower() == "max_rounds":
        winner = "D"
        if rounds == 0:
            rounds = max_rounds

    # If still unknown but rounds hit max: draw
    if winner == "?" and rounds >= max_rounds and max_rounds > 0:
        winner, reason = "D", "max_rounds"

    return (winner, reason, rounds)

def list_run_files(logs_dir: Path, runid_from: str, runid_to: str) -> List[Path]:
    files: List[Path] = []
    for p in logs_dir.iterdir():
        if not p.is_file():
            continue
        m = FILE_RE.match(p.name)
        if not m:
            continue
        rid = m.group("runid")
        if runid_from <= rid <= runid_to:
            files.append(p)

    # Prefer .log over .stdout.log if both exist for same runid
    files.sort(key=lambda p: (FILE_RE.match(p.name).group("runid"), 0 if (p.name.lower().endswith(".log") and not p.name.lower().endswith(".stdout.log")) else 1))
    out: List[Path] = []
    seen = set()
    for p in files:
        rid = FILE_RE.match(p.name).group("runid")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(p)
    return out

def _seat_wr(results: List[RunResult]) -> float:
    a = sum(1 for x in results if x.winner == "A")
    b = sum(1 for x in results if x.winner == "B")
    return (a / (a + b)) if (a + b) else 0.0

def paired_sideflip_report(results: List[RunResult]) -> None:
    """Directional paired report for sideflip variants."""
    groups: DefaultDict[Tuple[str,str,str,str], Dict[str, str]] = defaultdict(dict)
    for r in results:
        if not r.seed:
            continue
        key = (r.seed, r.fa or "", r.fb or "", r.start or "")
        groups[key][(r.variant or "unknown").lower()] = r.winner

    pairs = [
        ("base", "sideflip"),
        ("mirror", "mirror_sideflip"),
    ]

    print("\nAnalyse sideflip appariée (par seed+fa+fb+départ) :")
    for a_var, b_var in pairs:
        n = flips = same = draws = unknown = 0
        dir_counts = {"A->A":0, "A->B":0, "B->A":0, "B->B":0}
        for _key, mp in groups.items():
            wa = mp.get(a_var)
            wb = mp.get(b_var)
            if not wa or not wb:
                continue
            n += 1

            if wa == "D" or wb == "D":
                draws += 1
                continue
            if wa == "?" or wb == "?":
                unknown += 1
                continue
            if wa not in ("A","B") or wb not in ("A","B"):
                unknown += 1
                continue

            dir_counts[f"{wa}->{wb}"] += 1
            if wa != wb:
                flips += 1
            else:
                same += 1

        dec = n - draws - unknown
        flip_rate = (flips / dec) if dec > 0 else 0.0
        print(f"  {a_var} vs {b_var} : paires={n}  décisives={dec}  inversions={flips}  identiques={same}  nuls={draws}  inconnus={unknown}  taux_inv={flip_rate:.3f}")
        if dec > 0:
            print(f"    directions : A→A={dir_counts['A->A']}  A→B={dir_counts['A->B']}  B→A={dir_counts['B->A']}  B→B={dir_counts['B->B']}")
            net = dir_counts["A->B"] - dir_counts["B->A"]
            print(f"    bilan : (A→B − B→A) = {net:+d} sur {dec} paires décisives")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs-dir", required=True)
    ap.add_argument("--runid-from", required=True)
    ap.add_argument("--runid-to", required=True)
    ap.add_argument("--max-rounds", type=int, default=120)
    ap.add_argument("--batch-csv", default="", help="Optional explicit auto_runs_*.csv path; if omitted, uses latest in logs-dir")
    ap.add_argument("--logs-dir-hvia", default="", help="Dossier log_data HvIA optionnel (ex: .\logs\log_data)")
    args = ap.parse_args()

    logs_dir = Path(args.logs_dir)
    if not logs_dir.exists():
        raise SystemExit(f"[ERR] logs-dir not found: {logs_dir}")

    # Résolution automatique du sous-dossier log/
    log_dir = _resolve_log_dir(logs_dir)

    # CSV : explicite > auto-découverte dans logs_dir/csv/ > logs_dir/
    csv_path = Path(args.batch_csv) if args.batch_csv else _pick_latest_csv(logs_dir)
    csv_meta = load_csv_meta(csv_path) if (csv_path and csv_path.exists()) else {}

    run_files = list_run_files(log_dir, args.runid_from, args.runid_to)

    # Fusion optionnelle avec log_data (HvIA)
    if args.logs_dir_hvia:
        hvia_dir = _resolve_log_dir(Path(args.logs_dir_hvia))
        if hvia_dir.exists():
            run_files += list_run_files(hvia_dir, args.runid_from, args.runid_to)
            hvia_csv = _pick_latest_csv(Path(args.logs_dir_hvia))
            if hvia_csv and hvia_csv.exists():
                csv_meta.update(load_csv_meta(hvia_csv))
    results: List[RunResult] = []

    for p in run_files:
        rid = FILE_RE.match(p.name).group("runid")
        w, r, rounds = parse_run_file(p, args.max_rounds)
        meta = csv_meta.get(rid, CsvMeta(runid=rid))
        results.append(RunResult(
            runid=rid, winner=w, reason=r, rounds=rounds,
            complete=(w in ("A", "B", "D") and rounds > 0),
            file_path=str(p),
            variant=meta.variant, seed=meta.seed, start=meta.start, fa=meta.fa, fb=meta.fb
        ))

    total = len(results)
    complete = sum(1 for x in results if x.complete)
    incomplete = total - complete
    A = sum(1 for x in results if x.winner == "A")
    B = sum(1 for x in results if x.winner == "B")
    D = sum(1 for x in results if x.winner == "D")

    print("=== Proto_DDM RunLab — Rapport d'analyse (v6) ===")
    print(f"Dossier  : {logs_dir}  (logs → {log_dir})")
    if args.logs_dir_hvia:
        print(f"         HvIA : {args.logs_dir_hvia}")
    if csv_path:
        print(f"          CSV : {csv_path.name}")
    print(f"Parties  : {total}  (complètes={complete}, incomplètes={incomplete})")
    print(f"Plage    : {args.runid_from}  →  {args.runid_to}")
    print(f"Résultats: A={A}  B={B}  Nul={D}")

    decisive = A + B
    if decisive:
        seatA_wr = A / decisive
        seatB_wr = B / decisive
        print(f"Taux de victoire par siège (décisifs) : siège A={seatA_wr:.3f}  siège B={seatB_wr:.3f}  écart={abs(seatA_wr-seatB_wr):.3f}")
    else:
        print("Taux de victoire par siège : aucune partie décisive")

    # Outcomes by variant
    variants: Dict[str, List[RunResult]] = {}
    for x in results:
        v = (x.variant or "unknown")
        variants.setdefault(v, []).append(x)

    if variants:
        print("\nRésultats par variante :")
        for v in sorted(variants.keys(), key=lambda s: s.lower()):
            xs = variants[v]
            n = len(xs)
            a = sum(1 for t in xs if t.winner == "A")
            b = sum(1 for t in xs if t.winner == "B")
            d = sum(1 for t in xs if t.winner == "D")
            q = n - (a + b + d)
            dec = a + b
            seatA_wr = (a / dec) if dec else 0.0
            draw_rate = (d / n) if n else 0.0
            print(f"  {v:<16} N={n:4d}  A={a:4d}  B={b:4d}  Nul={d:4d}  ?={q:4d}  tx_vic_A={seatA_wr:.3f}  tx_nul={draw_rate:.3f}")

        non_sf = [x for x in results if "sideflip" not in (x.variant or "").lower()]
        sf = [x for x in results if "sideflip" in (x.variant or "").lower()]
        print(f"Agrégat sideflip (décisifs) : sans_sideflip tx_A={_seat_wr(non_sf):.3f}  avec_sideflip tx_A={_seat_wr(sf):.3f}  écart={abs(_seat_wr(non_sf)-_seat_wr(sf)):.3f}")

    paired_sideflip_report(results)

    # Faction winrate (overall; draws separately)
    fac = {f"F{i:02d}": {"games": 0, "wins": 0, "draws": 0} for i in range(1, 9)}
    for x in results:
        if not x.fa or not x.fb:
            continue
        try:
            fa = f"F{int(x.fa):02d}"
            fb = f"F{int(x.fb):02d}"
        except Exception:
            continue

        fac[fa]["games"] += 1
        fac[fb]["games"] += 1
        if x.winner == "D":
            fac[fa]["draws"] += 1
            fac[fb]["draws"] += 1
        elif x.winner == "A":
            fac[fa]["wins"] += 1
        elif x.winner == "B":
            fac[fb]["wins"] += 1

    print("\nTaux de victoire par faction (nuls comptés séparément) :")
    for k in sorted(fac.keys()):
        g = fac[k]["games"]
        w = fac[k]["wins"]
        d = fac[k]["draws"]
        wr = (w / (g - d)) if (g - d) else 0.0
        print(f"  {k} : parties={g:4d}  victoires={w:4d}  nuls={d:4d}  tx_vic={wr:.3f}")

if __name__ == "__main__":
    main()

