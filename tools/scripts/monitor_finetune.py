"""Live monitor for jaeha_finetune (or any train_ppo run with training.csv).

Reads:
  - logs/jaeha_finetune/*.log (mtime = start time)
  - rl/checkpoints/<save_dir>/<agent>/<agent>_<opp>_training.csv (progress)

Outputs synthetic dashboard (see launch_jaeha_finetune.bat for default paths).

Usage:
    python tools/scripts/monitor_finetune.py
    python tools/scripts/monitor_finetune.py --save-dir rl/checkpoints/v1.6 --target-steps 500000
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]


def fmt_dt(seconds: float) -> str:
    """Format seconds as e.g. '1h18m' or '45m12s'."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h{m:02d}m"


def latest_log_mtime(log_dir: Path) -> datetime | None:
    if not log_dir.exists():
        return None
    logs = list(log_dir.glob("*.log"))
    if not logs:
        return None
    latest = max(logs, key=lambda p: p.stat().st_mtime)
    # Use mtime of the FIRST creation (when bat started) — use ctime if mtime drifted
    return datetime.fromtimestamp(latest.stat().st_mtime)


def find_training_csv(save_dir: Path, agent: str) -> Path | None:
    agent_dir = save_dir / agent
    if not agent_dir.exists():
        return None
    csvs = list(agent_dir.glob(f"{agent}_*_training.csv"))
    if not csvs:
        return None
    return max(csvs, key=lambda p: p.stat().st_mtime)


def read_training_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "step":     int(r["step"]),
                    "stage":    int(r["stage"]),
                    "opponent": r["opponent"],
                    "wr":       float(r["wr"]) if r["wr"] != "nan" else None,
                    "avg_len":  float(r["avg_len"]) if r["avg_len"] != "nan" else None,
                    "total_ep": int(r["total_ep"]),
                })
            except (KeyError, ValueError):
                pass
    return rows


def stage_summary(rows: list[dict]) -> list[dict]:
    """Group CSV rows by stage and return summary per stage."""
    by_stage: dict[int, list[dict]] = {}
    for r in rows:
        by_stage.setdefault(r["stage"], []).append(r)
    out = []
    for stage_idx in sorted(by_stage):
        rs = by_stage[stage_idx]
        # Final WR = last non-nan wr in this stage
        final_wr = None
        for r in reversed(rs):
            if r["wr"] is not None:
                final_wr = r["wr"]
                break
        avg_len_last = None
        for r in reversed(rs):
            if r["avg_len"] is not None:
                avg_len_last = r["avg_len"]
                break
        out.append({
            "stage": stage_idx,
            "opponent": rs[0]["opponent"],
            "steps_in_stage": rs[-1]["step"] - rs[0]["step"],
            "final_wr": final_wr,
            "avg_len": avg_len_last,
            "n_rows": len(rs),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save-dir",      default="rl/checkpoints/v1.6")
    ap.add_argument("--agent",         default="jaeha")
    ap.add_argument("--log-dir",       default="logs/jaeha_finetune")
    ap.add_argument("--target-steps",  type=int, default=500_000)
    ap.add_argument("--n-stages",      type=int, default=7)
    args = ap.parse_args()

    save_dir = ROOT / args.save_dir
    log_dir  = ROOT / args.log_dir

    csv_path = find_training_csv(save_dir, args.agent)
    rows = read_training_csv(csv_path) if csv_path else []
    start_dt = latest_log_mtime(log_dir)

    now = datetime.now()
    elapsed_s = (now - start_dt).total_seconds() if start_dt else 0

    print("=" * 60)
    print(f"  FINETUNE MONITOR — {args.agent}")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not rows:
        print()
        print(f"  ⏳ Pas encore de données (training.csv vide ou inexistant)")
        if start_dt:
            print(f"  Démarré il y a {fmt_dt(elapsed_s)}")
        print(f"  → Premier flush SB3 attendu après ~3-5 min")
        return

    first_step = rows[0]["step"]
    last_step  = rows[-1]["step"]
    steps_done = last_step - first_step
    target     = args.target_steps
    pct        = steps_done / target * 100

    speed = steps_done / elapsed_s if elapsed_s > 0 else 0
    eta_s = (target - steps_done) / speed if speed > 0 else 0
    eta_dt = now + timedelta(seconds=eta_s) if speed > 0 else None
    total_est = elapsed_s + eta_s

    bar_len = 40
    fill = int(bar_len * min(1.0, steps_done / target))
    bar = "█" * fill + "░" * (bar_len - fill)

    print()
    print(f"  Progress     : [{bar}] {pct:5.1f}%")
    print(f"  Steps        : {steps_done:>7,} / {target:,}  (start={first_step:,})")
    print(f"  Speed        : ~{speed:.1f} steps/s")
    print()
    if start_dt:
        print(f"  Démarré      : {start_dt.strftime('%H:%M:%S')}  (il y a {fmt_dt(elapsed_s)})")
    print(f"  Maintenant   : {now.strftime('%H:%M:%S')}")
    if eta_dt:
        print(f"  ETA fin      : {eta_dt.strftime('%H:%M:%S')}  (reste {fmt_dt(eta_s)})")
        print(f"  Total estimé : {fmt_dt(total_est)}")

    # Stage table
    stages = stage_summary(rows)
    print()
    print("  Stages :")
    print(f"    {'Stage':<5} {'Opponent':<8} {'Steps':>8} {'WR':>6} {'AvgLen':>7} {'État':<14}")
    target_per_stage = target // args.n_stages
    for s in stages:
        stage_pct = s["steps_in_stage"] / target_per_stage * 100
        state = "✓ done" if stage_pct >= 95 else f"⏳ {stage_pct:.0f}%"
        wr_s   = f"{s['final_wr']*100:.1f}%" if s["final_wr"] is not None else "—"
        len_s  = f"{s['avg_len']:.1f}" if s["avg_len"] is not None else "—"
        print(f"    {s['stage']:<5} {s['opponent']:<8} {s['steps_in_stage']:>8,} {wr_s:>6} {len_s:>7} {state}")
    if len(stages) < args.n_stages:
        print(f"    ({args.n_stages - len(stages)} stage(s) restant(s))")


if __name__ == "__main__":
    main()
