#!/usr/bin/env python3
"""
analyze_batch.py — Analyse complète DDM en une commande
  → Logs DDM (dés, invocations, L5)
  → Reward RL (winrate, breakdown, qualité des actions)

Usage :
  python analyze_batch.py                          # chemins par défaut
  python analyze_batch.py --log-dir logs/autorun_log_data/log
  python analyze_batch.py --rl-dir rl/rl_logs/v0.1.0
  python analyze_batch.py --detail                 # détail reward par partie

Auto-export : si > 500 parties RL → fichier analyze_batch_YYYYMMDD_HHMMSS.md
"""

import sys
import contextlib
import io
import time
import argparse
from pathlib import Path
from collections import defaultdict

# ── Import des modules d'analyse ──────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "logs"))
sys.path.insert(0, str(ROOT / "rl"))

import analyze_ddm_logs as ddm_logs
import analyze_jsonl_v2 as rl_reward

AUTO_EXPORT_THRESHOLD = 500


# ── Résolution des fichiers ────────────────────────────────────────────────────

def latest_session_logs(log_dir):
    """
    Dans un dossier de fichiers run_YYYYMMDD_HHMMSS_NNNNN.log,
    retourne uniquement les fichiers de la session la plus récente
    (même préfixe YYYYMMDD_HHMMSS).
    Fallback sur les N fichiers les plus récents si nommage différent.
    """
    import re
    all_logs = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
    if not all_logs:
        return []
    pat = re.compile(r"run_(\d{8}_\d{6})_")
    # Trouver le timestamp de la session la plus récente
    latest_ts = None
    for p in reversed(all_logs):
        m = pat.match(p.name)
        if m:
            latest_ts = m.group(1)
            break
    if latest_ts:
        return [p for p in all_logs if pat.match(p.name) and pat.match(p.name).group(1) == latest_ts]
    # Fallback : les 500 plus récents
    return all_logs[-500:]


def resolve_log_paths(log_dir_arg):
    # Chemin explicite → on prend tout (l'utilisateur sait ce qu'il veut)
    if log_dir_arg:
        d = Path(log_dir_arg)
        if d.is_dir():
            paths = sorted(d.glob("*.log"))
            if paths:
                return paths

    # Dossier logs principal → session la plus récente uniquement
    for candidate in [
        ROOT / "logs" / "autorun_log_data" / "log",
        ROOT / "logs",
    ]:
        if candidate.is_dir():
            paths = latest_session_logs(candidate)
            if paths:
                return paths
    return []


def resolve_rl_files(rl_dir_arg):
    if rl_dir_arg:
        d = Path(rl_dir_arg)
        if d.is_dir():
            files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
            if files:
                return files
    # rl_logs racine en premier (autorun courant, non archivé)
    for candidate in [
        ROOT / "rl" / "rl_logs",
        ROOT / "rl_logs",
    ]:
        files = sorted(Path(candidate).glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if files:
            return files
    # Fallback : sous-dossiers archivés
    for candidate in [
        ROOT / "rl" / "rl_logs" / "v0.1.0",
        Path("."),
    ]:
        files = sorted(Path(candidate).glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if files:
            return files
    return []


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Analyse complète DDM")
    ap.add_argument("--log-dir", default="", help="Dossier des .log DDM")
    ap.add_argument("--rl-dir",  default="", help="Dossier des .jsonl reward")
    ap.add_argument("--detail",  action="store_true", help="Détail reward par partie")
    ap.add_argument("--no-logs", action="store_true", help="Skip analyse logs DDM")
    ap.add_argument("--no-rl",   action="store_true", help="Skip analyse reward RL")
    args = ap.parse_args()

    log_paths = [] if args.no_logs else resolve_log_paths(args.log_dir)
    rl_files  = [] if args.no_rl  else resolve_rl_files(args.rl_dir)

    # Compter les parties RL pour auto-export
    runs = defaultdict(list)
    for path in rl_files:
        parts  = path.stem.rsplit("_", 1)
        run_id = parts[0] if len(parts) == 2 and parts[1].isdigit() else path.stem
        lines  = rl_reward.load_jsonl(path)
        if lines:
            runs[run_id].append(rl_reward.parse_game(lines))

    total_rl_games = sum(len(g) for g in runs.values())
    use_file = total_rl_games > AUTO_EXPORT_THRESHOLD

    if use_file:
        out_path = Path(f"analyze_batch_{time.strftime('%Y%m%d_%H%M%S')}.md")
        buf = io.StringIO()
        cm  = contextlib.redirect_stdout(buf)
    else:
        out_path = None
        buf      = None
        cm       = contextlib.nullcontext()

    with cm:
        # ── 1. Logs DDM ──────────────────────────────────────────────────────
        if log_paths:
            print(f"\n{'═' * 70}")
            print(f"  SECTION 1/2 — LOGS DDM  ({len(log_paths)} fichier(s))")
            print(f"{'═' * 70}")
            data_logs = ddm_logs.scan_logs(log_paths)
            ddm_logs.render(data_logs)
        else:
            print(f"\n[SKIP] Logs DDM : aucun .log trouvé"
                  f"  (utilisez --log-dir pour spécifier le dossier)")

        # ── 2. Reward RL ──────────────────────────────────────────────────────
        if runs:
            print(f"\n{'═' * 70}")
            print(f"  SECTION 2/2 — REWARD RL  ({total_rl_games} parties, {len(runs)} run(s))")
            print(f"{'═' * 70}")
            for run_id, games in sorted(runs.items()):
                rl_reward.render_run(run_id, games, detail=args.detail)
            if len(runs) > 1:
                rl_reward.render_global(runs)
            print()
        else:
            print(f"\n[SKIP] Reward RL : aucun .jsonl trouvé"
                  f"  (utilisez --rl-dir pour spécifier le dossier)")

    if use_file:
        out_path.write_text(buf.getvalue(), encoding="utf-8")
        print(f"\n[auto-export] {total_rl_games} parties → {out_path.resolve()}")


if __name__ == "__main__":
    main()
