#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
policy_viewer_ddm.py
--------------------
Lecture/synthÃ¨se des sorties de policies (invocation/move/shape) gÃ©nÃ©rÃ©es depuis les logs DDM.

Objectif: t'Ã©viter d'ouvrir des gros JSON Ã  la main.
- Affiche un "coverage report"
- Sort le Top des actions par camp et par STAR
- Sort le Top des buckets de mouvement
- GÃ¨re les fichiers vides (ex: invocation_state vide aprÃ¨s un crash, shape vide si pas loggÃ©)

Usage (depuis .) :
    python policy_viewer_ddm.py --dir ".\logs\log_data\output_policies"

Par dÃ©faut, il cherche dans .\log_data\output_policies
et Ã©crit:
    policy_view_report.txt
    policy_view_report.json
dans le mÃªme dossier.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import defaultdict

def load_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

def safe_int(x, default=None):
    try:
        return int(str(x).strip())
    except Exception:
        return default

def top_k(items, k=10, key=lambda x: x[1], reverse=True):
    return sorted(items, key=key, reverse=reverse)[:k]

def summarize_invocation_simple(inv: dict, min_count: int):
    """
    Format attendu:
      key = "A|2|invoke_L3"
      val = {player, stars, action, count_all, count_complete, wins, winrate}
    """
    out = {"type": "invocation_simple", "entries": 0, "players": {}, "global": {}}
    if not isinstance(inv, dict) or not inv:
        out["empty"] = True
        return out

    out["entries"] = len(inv)

    # stats globales
    total_all = 0
    total_complete = 0
    for v in inv.values():
        if isinstance(v, dict):
            total_all += safe_int(v.get("count_all"), 0) or 0
            total_complete += safe_int(v.get("count_complete"), 0) or 0
    out["global"] = {"count_all_sum": total_all, "count_complete_sum": total_complete}

    # group by player + stars
    grp = defaultdict(list)
    for k, v in inv.items():
        if not isinstance(v, dict):
            continue
        p = str(v.get("player", "")).strip() or (k.split("|")[0] if "|" in k else "?"
        )
        s = safe_int(v.get("stars"), None)
        a = str(v.get("action", "")).strip() or (k.split("|")[2] if k.count("|") >= 2 else k)
        c = safe_int(v.get("count_all"), 0) or 0
        w = float(v.get("winrate", 0.0) or 0.0)
        grp[(p, s)].append((a, c, w))

    # build per player report
    by_player = defaultdict(dict)
    for (p, s), rows in grp.items():
        # top freq
        tf = top_k(rows, k=10, key=lambda r: r[1], reverse=True)
        # top winrate (avec min_count)
        tw = top_k([r for r in rows if r[1] >= min_count], k=10, key=lambda r: (r[2], r[1]), reverse=True)
        by_player[p][str(s)] = {
            "top_by_frequency": [{"action": a, "count": c, "winrate": w} for a, c, w in tf],
            "top_by_winrate":   [{"action": a, "count": c, "winrate": w} for a, c, w in tw],
        }
    out["players"] = by_player
    return out

def summarize_move_policy(move: dict):
    """
    Format attendu:
      { "meta": {...}, "move_policy_by_state": { state: { key: {player,bucket,count,wins,winrate}, ... }, ... } }
    """
    out = {"type": "movement_state", "states": 0, "samples": 0, "top": {}}
    if not isinstance(move, dict) or not move:
        out["empty"] = True
        return out
    meta = move.get("meta", {}) if isinstance(move.get("meta"), dict) else {}
    out["samples"] = safe_int(meta.get("samples"), 0) or 0

    mp = move.get("move_policy_by_state")
    if not isinstance(mp, dict) or not mp:
        out["empty"] = True
        out["states"] = 0
        return out

    out["states"] = len(mp)

    # top buckets global (tous Ã©tats confondus)
    agg = defaultdict(lambda: {"count": 0, "wins": 0})
    for state, entries in mp.items():
        if not isinstance(entries, dict):
            continue
        for _, v in entries.items():
            if not isinstance(v, dict):
                continue
            bucket = str(v.get("bucket", "")).strip() or "?"
            c = safe_int(v.get("count"), 0) or 0
            w = safe_int(v.get("wins"), 0) or 0
            agg[bucket]["count"] += c
            agg[bucket]["wins"] += w

    top_global = []
    for b, d in agg.items():
        c = d["count"]
        w = d["wins"]
        wr = (w / c) if c else 0.0
        top_global.append((b, c, wr))
    top_global = sorted(top_global, key=lambda t: (t[1], t[2]), reverse=True)[:15]
    out["top"]["global_buckets"] = [{"bucket": b, "count": c, "winrate": wr} for b, c, wr in top_global]
    return out

def summarize_shape_policy(shape: dict):
    """
    Format attendu:
      { "meta": {...}, "shape_policy_by_state": {...} }
    """
    out = {"type": "shape_state", "states": 0, "samples": 0}
    if not isinstance(shape, dict) or not shape:
        out["empty"] = True
        return out
    meta = shape.get("meta", {}) if isinstance(shape.get("meta"), dict) else {}
    out["samples"] = safe_int(meta.get("samples"), 0) or 0

    sp = shape.get("shape_policy_by_state")
    if not isinstance(sp, dict) or not sp:
        out["empty"] = True
        out["states"] = 0
        return out
    out["states"] = len(sp)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(Path("log_data") / "output_policies"), help="Dossier contenant les JSON de policies")
    ap.add_argument("--min-count", type=int, default=25, help="Seuil min de count pour classer par winrate")
    args = ap.parse_args()

    out_dir = Path(args.dir)
    inv_p = out_dir / "ddm_invocation_policy.json"
    invs_p = out_dir / "ddm_invocation_policy_state.json"
    move_p = out_dir / "ddm_move_policy_state.json"
    shape_p = out_dir / "ddm_shape_policy_state.json"
    suite_p = out_dir / "policy_suite_report.json"

    inv = load_json(inv_p)
    invs = load_json(invs_p)
    move = load_json(move_p)
    shape = load_json(shape_p)
    suite = load_json(suite_p)

    report = {"dir": str(out_dir), "suite": suite or {}, "summaries": {}}
    report["summaries"]["invocation_simple"] = summarize_invocation_simple(inv or {}, args.min_count)
    # invocation_state peut Ãªtre {} (ex: run interrompu / crash)
    report["summaries"]["invocation_state"] = {"empty": True} if not invs else {"keys": len(invs)}
    report["summaries"]["movement"] = summarize_move_policy(move or {})
    report["summaries"]["shape"] = summarize_shape_policy(shape or {})

    # Ã‰criture
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "policy_view_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # TXT lisible
    lines = []
    lines.append("=== DDM Policy Viewer ===")
    lines.append(f"Dossier: {out_dir}")
    if suite:
        lines.append(f"Logs total: {suite.get('meta', {}).get('logs_total')} | include_incomplete={suite.get('meta', {}).get('include_incomplete')}")
        lines.append(f"Samples: inv={suite.get('samples', {}).get('invocation_simple')} inv_state={suite.get('samples', {}).get('invocation_state')} move={suite.get('samples', {}).get('movement')} shape={suite.get('samples', {}).get('shape')}")
    lines.append("")

    invsum = report["summaries"]["invocation_simple"]
    if invsum.get("empty"):
        lines.append("[INV] invocation_simple: VIDE")
    else:
        lines.append(f"[INV] invocation_simple: entries={invsum['entries']} count_all_sum={invsum['global']['count_all_sum']}")
        for player, d in invsum["players"].items():
            lines.append(f"  Player {player}:")
            # stars sorted numeric if possible
            for stars_key in sorted(d.keys(), key=lambda x: (safe_int(x, 9999) if x != 'None' else 9999, x)):
                lines.append(f"    stars={stars_key}:")
                topfreq = d[stars_key]["top_by_frequency"][:5]
                topwr = d[stars_key]["top_by_winrate"][:5]
                if topfreq:
                    lines.append("      Top freq: " + ", ".join([f"{r['action']}({r['count']})" for r in topfreq]))
                if topwr:
                    lines.append("      Top WR  : " + ", ".join([f"{r['action']}({r['count']}|{r['winrate']:.2f})" for r in topwr]))
    lines.append("")

    if not invs:
        lines.append("[INV_STATE] ddm_invocation_policy_state.json : VIDE (probable crash/filtre) -> Ã  rÃ©gÃ©nÃ©rer avec le main patchÃ©.")
    else:
        lines.append(f"[INV_STATE] keys={len(invs)} (viewer basique)")

    movesum = report["summaries"]["movement"]
    if movesum.get("empty"):
        lines.append("[MOVE] movement_policy: VIDE ou pas assez de patterns")
    else:
        lines.append(f"[MOVE] samples={movesum.get('samples')} states={movesum.get('states')}")
        gb = movesum.get("top", {}).get("global_buckets", [])
        if gb:
            lines.append("  Top buckets: " + ", ".join([f"{x['bucket']}({x['count']})" for x in gb[:10]]))
    shapesum = report["summaries"]["shape"]
    if shapesum.get("empty"):
        lines.append("[SHAPE] shape_policy: VIDE (normal si pas de logs SHAPE_*)")
    else:
        lines.append(f"[SHAPE] samples={shapesum.get('samples')} states={shapesum.get('states')}")

    (out_dir / "policy_view_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[OK] Rapports Ã©crits dans: {out_dir}")

if __name__ == "__main__":
    main()

