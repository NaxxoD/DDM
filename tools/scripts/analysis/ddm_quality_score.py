#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ddm_quality_score.py â€” Score "qualitÃ©" des logs (0â†’1) + classification

V2:
- Ignore *.stderr.log par dÃ©faut (option: --include-stderr)
- Fallback rounds: si pas de TOUR/SUMMARY -> estime via count(ROLL A/B), puis count(MOVE A/B)

Outputs:
- <LOG_DIR>\output_DDM_QS\quality_report.csv
- <LOG_DIR>\output_DDM_QS\quality_report.json
"""

from __future__ import annotations
import re, json, csv, argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict


# ----------------------------
# Regex / patterns
# ----------------------------

RE_RUN_START = re.compile(r"\bRUN_START\b.*\bmode=([a-zA-Z0-9_]+)\b", re.IGNORECASE)
RE_FA_A = re.compile(r"\bFACTION_A:\s*.*\bname=([^\n]+?)\s+champ=", re.IGNORECASE)
RE_FA_B = re.compile(r"\bFACTION_B:\s*.*\bname=([^\n]+?)\s+champ=", re.IGNORECASE)

# UI stdout fallback
RE_UI_FA_A = re.compile(r"===\s*Joueur\s*A\s*\(Faction:\s*(.+?)\)\s*===", re.IGNORECASE)
RE_UI_FA_B = re.compile(r"===\s*Joueur\s*B\s*\(Faction:\s*(.+?)\)\s*===", re.IGNORECASE)

RE_GAME_END = re.compile(r"\bGAME_END:\s*winner=([A-Za-z]+)\s*reason=([A-Za-z0-9_\-]+)", re.IGNORECASE)
RE_QG_DESTROY = re.compile(r"QG\s*([AB])\s*dÃ©truit\s*!.*gagne", re.IGNORECASE)  # match aussi avec ***

RE_SUMMARY_TA = re.compile(r"^\s*Tours\s+Joueur\s+A\s*:\s*(\d+)", re.MULTILINE)
RE_SUMMARY_TB = re.compile(r"^\s*Tours\s+(?:IA\s+B|Joueur\s+B)\s*:\s*(\d+)", re.MULTILINE)

RE_TOUR = re.compile(r"===\s*TOUR\s*(\d+)\s*â€”", re.IGNORECASE)
RE_TOUR2 = re.compile(r"\[Tour\s*(\d+)\s*-\s*Joueur", re.IGNORECASE)

RE_TRACEBACK = re.compile(r"Traceback\s*\(most recent call last\)", re.IGNORECASE)
RE_EXCEPTION = re.compile(r"\b(Error|Exception|EOFError|JSONDecodeError)\b", re.IGNORECASE)

# Turn proxies
RE_ROLL_A = re.compile(r"^ROLL\s+A:", re.MULTILINE)
RE_ROLL_B = re.compile(r"^ROLL\s+B:", re.MULTILINE)
RE_MOVE_A = re.compile(r"^MOVE\s+A:", re.MULTILINE)
RE_MOVE_B = re.compile(r"^MOVE\s+B:", re.MULTILINE)

# Integrity blocks (issus de tes logs "canon")
INTEGRITY_PATTERNS = [
    re.compile(r"\bROLL_START\b", re.IGNORECASE),
    re.compile(r"^ROLL\s+[AB]:", re.MULTILINE),
    re.compile(r"^MOVE\s+[AB]:", re.MULTILINE),
    re.compile(r"\bINVOC_", re.IGNORECASE),
    re.compile(r"\bEND_PHASE_MOBS_[AB]\b", re.IGNORECASE),
]

# Progress scaling
PROG_MIN = 5
PROG_CAP = 30


@dataclass
class RunQuality:
    path: str
    size_bytes: int
    mode: str
    faction_A: str
    faction_B: str
    rounds: int
    end_type: str          # normal/timeout/interrupted/crash/incomplete
    winner: str            # A/B/draw/none/?
    reason: str            # max_rounds/keyboard_interrupt/...
    has_traceback: bool

    parse_score: float
    progress_score: float
    integrity_score: float
    end_score: float
    Q: float


def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def read_text_safely(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.read_text(errors="ignore")


def detect_mode(text: str) -> str:
    m = RE_RUN_START.search(text)
    if m:
        return m.group(1).lower()
    tl = text.lower()
    if "mode=iaia" in tl:
        return "iaia"
    if "mode=hvia" in tl:
        return "hvia"
    if "mode=hvh" in tl:
        return "hvh"
    return "unknown"


def detect_factions(text: str) -> Tuple[str, str]:
    fa = fb = ""
    mA = RE_FA_A.search(text)
    mB = RE_FA_B.search(text)
    if mA:
        fa = mA.group(1).strip()
    if mB:
        fb = mB.group(1).strip()

    if not fa:
        m = RE_UI_FA_A.search(text)
        if m:
            fa = m.group(1).strip()
    if not fb:
        m = RE_UI_FA_B.search(text)
        if m:
            fb = m.group(1).strip()

    return fa or "?", fb or "?"


def extract_rounds(text: str) -> int:
    # 1) Summary direct (le plus fiable)
    ta = RE_SUMMARY_TA.search(text)
    tb = RE_SUMMARY_TB.search(text)
    if ta or tb:
        a = int(ta.group(1)) if ta else 0
        b = int(tb.group(1)) if tb else 0
        return max(a, b)

    # 2) TOUR explicite
    vals = [int(x) for x in RE_TOUR.findall(text)]
    if vals:
        return max(vals)

    # 3) TOUR alt
    vals2 = [int(x) for x in RE_TOUR2.findall(text)]
    if vals2:
        return max(vals2)

    # 4) Fallback: compter les tours via ROLL A/B
    roll_a = len(RE_ROLL_A.findall(text))
    roll_b = len(RE_ROLL_B.findall(text))
    if max(roll_a, roll_b) > 0:
        return max(roll_a, roll_b)

    # 5) Dernier fallback: MOVE A/B
    move_a = len(RE_MOVE_A.findall(text))
    move_b = len(RE_MOVE_B.findall(text))
    if max(move_a, move_b) > 0:
        return max(move_a, move_b)

    return 0


def detect_end(text: str) -> Tuple[str, str, str]:
    # crash dur
    if RE_TRACEBACK.search(text):
        return "crash", "none", "traceback"

    # GAME_END canon (autoruns)
    m = RE_GAME_END.search(text)
    if m:
        winner = m.group(1).lower()
        reason = m.group(2).lower()
        if reason == "max_rounds":
            return "timeout", winner, reason
        if reason in ("keyboard_interrupt",):
            return "interrupted", winner, reason
        return "normal", winner, reason

    # QG dÃ©truit (stdout ou log), mÃªme avec ***
    m2 = RE_QG_DESTROY.search(text)
    if m2:
        destroyed = m2.group(1).upper()
        winner = "B" if destroyed == "A" else "A"
        return "normal", winner, "hq_destroyed"

    # interruption "soft"
    if "GAME_INTERRUPTED_BY_USER" in text:
        return "interrupted", "none", "user_interrupt"

    # erreurs lÃ©gÃ¨res (EOF/JSON/...)
    if RE_EXCEPTION.search(text) and "RÃ©sumÃ© de fin de partie" not in text:
        return "crash", "none", "exception"

    return "incomplete", "none", "no_end_marker"


def score_parse(mode: str, fa: str, fb: str, winner: str) -> float:
    # factions=0.4, mode=0.3, winner=0.3
    s = 0.0
    if fa != "?" and fb != "?":
        s += 0.4
    if mode != "unknown":
        s += 0.3
    if winner not in ("none", "?", ""):
        s += 0.3
    return clamp01(s)


def score_progress(rounds: int) -> float:
    # 0 si <5, 1 si >=30, linÃ©aire entre
    if rounds <= 0:
        return 0.0
    if rounds < PROG_MIN:
        return 0.0
    if rounds >= PROG_CAP:
        return 1.0
    return clamp01((rounds - PROG_MIN) / (PROG_CAP - PROG_MIN))


def score_integrity(text: str, has_traceback: bool) -> float:
    found = 0
    for rx in INTEGRITY_PATTERNS:
        if rx.search(text):
            found += 1
    base = found / float(len(INTEGRITY_PATTERNS))  # 0..1
    no_tb = 0.0 if has_traceback else 1.0
    return clamp01(0.7 * base + 0.3 * no_tb)


def score_end(end_type: str, reason: str) -> float:
    end_type = (end_type or "").lower()
    reason = (reason or "").lower()

    if end_type == "normal":
        return 1.0
    if end_type == "timeout" and reason == "max_rounds":
        return 0.75
    if end_type == "interrupted":
        return 0.20
    if end_type == "crash":
        return 0.10
    return 0.0


def analyze_log(p: Path) -> RunQuality:
    text = read_text_safely(p)
    mode = detect_mode(text)
    fa, fb = detect_factions(text)
    rounds = extract_rounds(text)
    end_type, winner, reason = detect_end(text)
    has_tb = bool(RE_TRACEBACK.search(text))

    ps = score_parse(mode, fa, fb, winner)
    pr = score_progress(rounds)
    it = score_integrity(text, has_tb)
    es = score_end(end_type, reason)

    Q = clamp01(0.25 * ps + 0.35 * pr + 0.25 * it + 0.15 * es)

    return RunQuality(
        path=str(p),
        size_bytes=p.stat().st_size,
        mode=mode,
        faction_A=fa,
        faction_B=fb,
        rounds=rounds,
        end_type=end_type,
        winner=winner,
        reason=reason,
        has_traceback=has_tb,
        parse_score=round(ps, 4),
        progress_score=round(pr, 4),
        integrity_score=round(it, 4),
        end_score=round(es, 4),
        Q=round(Q, 4),
    )


def summarize(rows: List[RunQuality]) -> Dict:
    if not rows:
        return {"total": 0}

    total = len(rows)
    avgQ = sum(r.Q for r in rows) / total

    by_end: Dict[str, int] = {}
    by_bucket: Dict[str, int] = {"Q>=0.7": 0, "0.4-0.7": 0, "Q<0.4": 0}

    for r in rows:
        by_end[r.end_type] = by_end.get(r.end_type, 0) + 1
        if r.Q >= 0.7:
            by_bucket["Q>=0.7"] += 1
        elif r.Q >= 0.4:
            by_bucket["0.4-0.7"] += 1
        else:
            by_bucket["Q<0.4"] += 1

    worst = sorted(rows, key=lambda x: x.Q)[:15]
    best = sorted(rows, key=lambda x: x.Q, reverse=True)[:15]

    return {
        "total": total,
        "avg_Q": round(avgQ, 4),
        "by_end_type": by_end,
        "by_Q_bucket": by_bucket,
        "sample_worst": [
            {"path": w.path, "Q": w.Q, "end_type": w.end_type, "reason": w.reason, "rounds": w.rounds}
            for w in worst
        ],
        "sample_best": [
            {"path": b.path, "Q": b.Q, "end_type": b.end_type, "reason": b.reason, "rounds": b.rounds}
            for b in best
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=str, default=r".\logs\log_data")
    ap.add_argument("--include-stderr", action="store_true", help="Inclure les *.stderr.log (sinon ignorÃ©s)")
    args = ap.parse_args()

    base = Path(args.dir)
    if not base.exists():
        print(f"[ERR] Dossier introuvable: {base}")
        return

    out_dir = base / "output_DDM_QS"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "quality_report.csv"
    out_json = out_dir / "quality_report.json"

    # collect
    exts = (".log", ".stdout.log")
    all_files = sorted([p for p in base.rglob("*") if p.is_file() and p.name.lower().endswith(exts)])

    ignored = 0
    files: List[Path] = []
    for p in all_files:
        name = p.name.lower()
        if (not args.include_stderr) and name.endswith(".stderr.log"):
            ignored += 1
            continue
        files.append(p)

    if not files:
        print("[WARN] Aucun log trouvÃ© aprÃ¨s filtrage.")
        return

    rows: List[RunQuality] = []

    total = len(files)
    step = max(1, total // 50)  # ~2% d'update

    print(f"[INFO] Analyse de {total} fichier(s) dans: {base}")
    if ignored:
        print(f"[INFO] IgnorÃ©s (stderr): {ignored}  (utilise --include-stderr pour les inclure)")
    print(f"[INFO] Outputs -> {out_dir}")

    for i, p in enumerate(files, 1):
        try:
            rows.append(analyze_log(p))
        except Exception as e:
            rows.append(RunQuality(
                path=str(p),
                size_bytes=p.stat().st_size if p.exists() else 0,
                mode="unknown",
                faction_A="?",
                faction_B="?",
                rounds=0,
                end_type="crash",
                winner="none",
                reason=f"analyze_error:{type(e).__name__}",
                has_traceback=False,
                parse_score=0.0,
                progress_score=0.0,
                integrity_score=0.0,
                end_score=0.10,
                Q=0.015,  # 0.15*0.10
            ))

        if i % step == 0 or i == total:
            avgq = sum(r.Q for r in rows) / len(rows)
            print(f"[{i:>5}/{total}] {p.name} | avgQ={avgq:.3f} | lastQ={rows[-1].Q:.3f}")

    # write CSV
    fieldnames = list(asdict(rows[0]).keys())
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

    # write JSON summary
    summary = summarize(rows)
    summary["ignored_stderr"] = ignored
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # recap
    print("\n=== RÃ‰SUMÃ‰ QUALITÃ‰ ===")
    print(f"  Logs analysÃ©s : {summary.get('total', 0)}")
    print(f"  IgnorÃ©s stderr: {summary.get('ignored_stderr', 0)}")
    print(f"  Q moyen       : {summary.get('avg_Q', 0)}")
    print("  Par fin :")
    for k, v in sorted(summary.get("by_end_type", {}).items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {k:11s} : {v}")
    print("  Buckets Q :")
    for k, v in summary.get("by_Q_bucket", {}).items():
        print(f"    {k:8s} : {v}")
    print(f"\n[OK] CSV  : {out_csv}")
    print(f"[OK] JSON : {out_json}")


if __name__ == "__main__":
    main()

