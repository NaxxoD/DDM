"""
analyze_jsonl_v2.py — Dashboard RL pour DDM
Usage :
  python analyze_jsonl_v2.py reward_*.jsonl
  python analyze_jsonl_v2.py --dir rl/rl_logs
  python analyze_jsonl_v2.py reward_*.jsonl --detail
"""
import argparse
import contextlib
import io
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

AUTO_EXPORT_THRESHOLD = 500  # au-delà → fichier .md plutôt que console


# ─── Helpers visuels ──────────────────────────────────────────────────────────

def bar(value, max_val, width=8, char="█", empty="░"):
    if max_val == 0:
        return empty * width
    filled = min(int(round(abs(value) / max_val * width)), width)
    return char * filled + empty * (width - filled)

def pct_bar(pct, width=10):
    filled = min(int(round(pct / 100 * width)), width)
    return "█" * filled + "░" * (width - filled)

def sparkline(values, width=10):
    blocks = " ▁▂▃▄▅▆▇█"
    if not values:
        return " " * width
    mn, mx = min(values), max(values)
    rng = mx - mn or 1
    step = max(1, len(values) // width)
    sampled = (values[::step])[:width]
    result = ""
    for v in sampled:
        idx = int((v - mn) / rng * (len(blocks) - 1))
        result += blocks[idx]
    return result.ljust(width)


# ─── Parsing ──────────────────────────────────────────────────────────────────

def load_jsonl(path):
    lines = []
    with open(path, encoding="utf-8") as f:
        for l in f:
            l = l.strip()
            if not l:
                continue
            try:
                lines.append(json.loads(l))
            except json.JSONDecodeError:
                pass
    return lines


def parse_game(lines):
    turns    = [l for l in lines if l.get("event") != "EPISODE_END"]
    episodes = [l for l in lines if l.get("event") == "EPISODE_END"]

    ep       = episodes[0] if episodes else {}
    terminal = ep.get("features", {}).get("terminal") or ep.get("terminal", "?")
    if terminal == "win":
        winner = ep.get("player", "?")
    elif terminal in ("draw", "max_rounds", "timeout", "stalemate"):
        winner   = "draw"
        terminal = "draw"
    else:
        hq   = ep.get("hq", {})
        hq_a = hq.get("A", 1)
        hq_b = hq.get("B", 1)
        if hq_a <= 0 and hq_b > 0:
            winner, terminal = "B", "win"
        elif hq_b <= 0 and hq_a > 0:
            winner, terminal = "A", "win"
        else:
            winner   = "draw"
            terminal = "draw"
    # Crash moteur : terminal inconnu ET les deux QG intacts = partie interrompue
    if winner not in ("A", "B", "draw"):
        winner, terminal = "error", "error"
    n_turns = ep.get("turn_idx", len(turns))

    sides = {}
    for side in ("A", "B"):
        t = [l for l in turns if l.get("player") == side]
        if not t:
            continue

        bd = defaultdict(float)
        for l in t:
            for k, v in (l.get("breakdown") or {}).items():
                bd[k] += v

        feats      = [l.get("features") or {} for l in t]
        dmg_series = [f.get("dmg_qg", 0) for f in feats]
        void_turns = sum(1 for f in feats if f.get("void_action"))
        avoid_turns= sum(1 for f in feats if f.get("pass_avoidable"))
        kills      = sum(f.get("kills_enemy", 0) for f in feats)
        # void_real : void seulement sur les tours où des unités existent
        turns_with_units = [f for f in feats if f.get("units_count", 1) > 0]
        void_with_units  = sum(1 for f in turns_with_units if f.get("void_action"))
        # void_midlate : void sur tours mid/late (>= 3 unités) — exclut le void structurel early
        turns_midlate    = [f for f in feats if f.get("units_count", 0) >= 3]
        void_midlate     = sum(1 for f in turns_midlate if f.get("void_action"))

        # urgence dynamique si loggée
        aggro_vals = [f.get("aggro_final", 0) for f in feats if f.get("aggro_final")]

        sides[side] = {
            "n_turns"   : len(t),
            "bd"        : dict(bd),
            "reward"    : sum(bd.values()),
            "dmg_series": dmg_series,
            "dmg_total" : sum(dmg_series),
            "dmg_mean"  : sum(dmg_series) / len(dmg_series) if dmg_series else 0,
            "void"      : void_turns,
            "avoid"         : avoid_turns,
            "kills"         : kills,
            "turns_w_units" : len(turns_with_units),
            "void_real"     : void_with_units,
            "turns_midlate" : len(turns_midlate),
            "void_midlate"  : void_midlate,
            "aggro_vals": aggro_vals,
        }

    return {
        "terminal": terminal,
        "winner"  : winner,
        "n_turns" : n_turns,
        "sides"   : sides,
        "faction_A" : ep.get("faction_A") or (turns[0].get("faction_A") if turns else "?") or "?",
        "faction_B" : ep.get("faction_B") or (turns[0].get("faction_B") if turns else "?") or "?",
        "champion_A": ep.get("champion_A") or (turns[0].get("champion_A") if turns else "?") or "?",
        "champion_B": ep.get("champion_B") or (turns[0].get("champion_B") if turns else "?") or "?",
    }


# ─── Dashboard ────────────────────────────────────────────────────────────────

VARIANTS = ["base", "mirror", "sideflip", "mirror_sideflip"]

def _variant_name(game_idx):
    """Index global → nom de variant (cycle de 4)."""
    return VARIANTS[game_idx % 4]

def _pair_label(game_idx):
    """Index global → numéro de paire (1-based)."""
    return game_idx // 4 + 1

def render_run(run_id, games, detail=False):
    n      = len(games)
    errors = sum(1 for g in games if g["winner"] == "error")
    wins_A = sum(1 for g in games if g["winner"] == "A")
    wins_B = sum(1 for g in games if g["winner"] == "B")
    draws  = sum(1 for g in games if g["terminal"] == "draw")
    pct_A  = wins_A / n * 100 if n else 0
    pct_B  = wins_B / n * 100 if n else 0

    # Agrégats
    agg      = {"A": defaultdict(float), "B": defaultdict(float)}
    dmg_A_all, dmg_B_all = [], []
    turns_A = turns_B = void_A = void_B = avoid_A = avoid_B = 0
    tunits_A = tunits_B = vreal_A = vreal_B = 0
    tml_A = tml_B = vml_A = vml_B = 0

    for g in games:
        for side in ("A", "B"):
            s = g["sides"].get(side, {})
            for k, v in s.get("bd", {}).items():
                agg[side][k] += v
            if side == "A":
                dmg_A_all.append(s.get("dmg_total", 0))
                turns_A  += s.get("n_turns", 0)
                void_A   += s.get("void", 0)
                avoid_A  += s.get("avoid", 0)
                tunits_A += s.get("turns_w_units", 0)
                vreal_A  += s.get("void_real", 0)
                tml_A    += s.get("turns_midlate", 0)
                vml_A    += s.get("void_midlate", 0)
            else:
                dmg_B_all.append(s.get("dmg_total", 0))
                turns_B  += s.get("n_turns", 0)
                void_B   += s.get("void", 0)
                avoid_B  += s.get("avoid", 0)
                tunits_B += s.get("turns_w_units", 0)
                vreal_B  += s.get("void_real", 0)
                tml_B    += s.get("turns_midlate", 0)
                vml_B    += s.get("void_midlate", 0)

    dmg_A_mean   = sum(dmg_A_all) / len(dmg_A_all) if dmg_A_all else 0
    dmg_B_mean   = sum(dmg_B_all) / len(dmg_B_all) if dmg_B_all else 0
    dmg_max      = max(max(dmg_A_all or [0]), max(dmg_B_all or [0])) or 1
    void_A_pct   = void_A  / turns_A * 100 if turns_A else 0
    void_B_pct   = void_B  / turns_B * 100 if turns_B else 0
    avoid_A_pct  = avoid_A / turns_A * 100 if turns_A else 0
    avoid_B_pct  = avoid_B / turns_B * 100 if turns_B else 0
    vreal_A_pct  = vreal_A / tunits_A * 100 if tunits_A else 0
    vreal_B_pct  = vreal_B / tunits_B * 100 if tunits_B else 0
    vml_A_pct    = vml_A   / tml_A    * 100 if tml_A    else 0
    vml_B_pct    = vml_B   / tml_B    * 100 if tml_B    else 0

    # Breakdown fusionné A+B
    bd_total = defaultdict(float)
    for side in ("A", "B"):
        for k, v in agg[side].items():
            bd_total[k] += v
    bd_max = max((abs(v) for v in bd_total.values()), default=1)
    bd_sum = sum(abs(v) for v in bd_total.values()) or 1

    # ─ Affichage ─
    W = 62
    short_id = run_id.split("_")[-2] if "_" in run_id else run_id
    n_pairs = max(1, (n + 3) // 4)
    print(f"\nRun {short_id} — {n} {'partie' if n==1 else 'parties'} ({n_pairs} paire{'s' if n_pairs>1 else ''} × 4 variants)")
    print("━" * W)

    # Winrate global
    print(f"  Winrate")
    bias = " ⚠️  biais" if max(pct_A, pct_B) >= 75 else ""
    print(f"    A  {pct_bar(pct_A)}  {wins_A}/{n}  ({pct_A:.0f}%)")
    print(f"    B  {pct_bar(pct_B)}  {wins_B}/{n}  ({pct_B:.0f}%){bias}")
    if draws:
        print(f"    Draw : {draws}")
    if errors:
        print(f"    Error: {errors}  ⚠️  (crash moteur — exclus des stats)")

    # Winrate + factions par paire
    if n_pairs > 1:
        print(f"  ── Par paire ──")
        for p_idx in range(n_pairs):
            pair_games = games[p_idx*4:(p_idx+1)*4]
            if not pair_games:
                continue
            pA = sum(1 for g in pair_games if g["winner"] == "A")
            pB = sum(1 for g in pair_games if g["winner"] == "B")
            pD = sum(1 for g in pair_games if g["terminal"] == "draw")
            res = ("A×" + str(pA) if pA else "") + (" B×" + str(pB) if pB else "") + (" D×" + str(pD) if pD else "")
            g0  = pair_games[0]
            fa  = (g0.get("faction_A") or "?").split("–")[-1].strip()
            fb  = (g0.get("faction_B") or "?").split("–")[-1].strip()
            ca  = g0.get("champion_A", "?")
            cb  = g0.get("champion_B", "?")
            print(f"    P{p_idx+1}  {res.strip():<12}  A:{fa} [{ca}]  vs  B:{fb} [{cb}]")

    # dmg_QG
    print(f"\n  dmg_QG (total / partie)")
    spark_A = sparkline(dmg_A_all)
    spark_B = sparkline(dmg_B_all)
    print(f"    A  {spark_A}  moy: {dmg_A_mean:.1f}")
    print(f"    B  {spark_B}  moy: {dmg_B_mean:.1f}")

    # Qualité des actions
    print(f"\n  Qualité des actions")
    va_flag  = "⚠️ " if max(void_A_pct, void_B_pct)   > 20 else "ok ✓"
    vr_flag  = "⚠️ " if max(vreal_A_pct, vreal_B_pct)  > 15 else "ok ✓"
    vml_flag = "⚠️ " if max(vml_A_pct,   vml_B_pct)    > 15 else "ok ✓"
    av_flag  = "⚠️ " if max(avoid_A_pct, avoid_B_pct)  > 15 else "ok ✓"
    print(f"    void_action     A={void_A_pct:4.1f}%  B={void_B_pct:4.1f}%  {va_flag}  (tous tours)")
    print(f"    void_réel       A={vreal_A_pct:4.1f}%  B={vreal_B_pct:4.1f}%  {vr_flag}  (≥1 unité)")
    print(f"    void_mid/late   A={vml_A_pct:4.1f}%  B={vml_B_pct:4.1f}%  {vml_flag}  (≥3 unités — hors early)")
    print(f"    pass_avoidable  A={avoid_A_pct:4.1f}%  B={avoid_B_pct:4.1f}%  {av_flag}")

    # Breakdown
    print(f"\n  Breakdown reward")
    for k, v in sorted(bd_total.items(), key=lambda x: abs(x[1]), reverse=True):
        if abs(v) < 0.01:
            continue
        b    = bar(v, bd_max)
        sign = "+" if v >= 0 else ""
        pct  = abs(v) / bd_sum * 100
        is_dominant = abs(v) == bd_max
        flag = " (dominant ⚠️)" if is_dominant and v < 0 \
               else " (dominant ✓)" if is_dominant and v > 0 \
               else f" (ok ✓)" if pct < 15 else ""
        print(f"    {k:<22s}  {b}  {sign}{v:6.1f}  {flag}")

    # Détail par partie
    if detail:
        print(f"\n  ── Détail ──")
        for i, g in enumerate(games):
            var   = _variant_name(i)
            pair  = _pair_label(i)
            label = f"P{pair}/{var}" if n_pairs > 1 else var
            if g["terminal"] == "win":
                res = f"WIN {g['winner']}"
            elif g["terminal"] == "error":
                res = "ERROR ⚠️"
            else:
                res = "DRAW"
            sA    = g["sides"].get("A", {})
            sB    = g["sides"].get("B", {})
            print(f"\n    [{label}]  {res}  {g['n_turns']} tours")
            print(f"      A: dmg={sA.get('dmg_total',0):5.0f}  kills={sA.get('kills',0)}  "
                  f"void={sA.get('void',0)}  avoid={sA.get('avoid',0)}  "
                  f"reward={sA.get('reward',0):+.2f}")
            print(f"      B: dmg={sB.get('dmg_total',0):5.0f}  kills={sB.get('kills',0)}  "
                  f"void={sB.get('void',0)}  avoid={sB.get('avoid',0)}  "
                  f"reward={sB.get('reward',0):+.2f}")
            # Breakdown court par partie
            if detail:
                bd_A = sA.get("bd", {})
                bd_B = sB.get("bd", {})
                all_keys = set(bd_A) | set(bd_B)
                for k in sorted(all_keys, key=lambda k: abs(bd_A.get(k,0)+bd_B.get(k,0)), reverse=True)[:6]:
                    va = bd_A.get(k, 0)
                    vb = bd_B.get(k, 0)
                    print(f"        {k:<22s}  A:{va:+6.2f}  B:{vb:+6.2f}")


def render_global(all_runs):
    all_games = [g for games in all_runs.values() for g in games]
    total     = len(all_games)
    if total == 0:
        return

    wins_A = sum(1 for g in all_games if g["winner"] == "A")
    wins_B = sum(1 for g in all_games if g["winner"] == "B")
    draws  = sum(1 for g in all_games if g["terminal"] == "draw")

    bd_global = defaultdict(float)
    for g in all_games:
        for side in ("A", "B"):
            for k, v in g["sides"].get(side, {}).get("bd", {}).items():
                bd_global[k] += v

    bd_max = max((abs(v) for v in bd_global.values()), default=1)
    bd_sum = sum(abs(v) for v in bd_global.values()) or 1

    print(f"\n{'═' * 62}")
    print(f"  SYNTHÈSE GLOBALE  —  {len(all_runs)} runs  /  {total} parties")
    print(f"{'═' * 62}")
    print(f"    A: {wins_A}/{total} ({wins_A/total*100:.0f}%)")
    print(f"    B: {wins_B}/{total} ({wins_B/total*100:.0f}%)")
    if draws:
        print(f"    Draw: {draws}")

    print(f"\n  Breakdown global")
    for k, v in sorted(bd_global.items(), key=lambda x: abs(x[1]), reverse=True):
        if abs(v) < 0.01:
            continue
        b    = bar(v, bd_max)
        sign = "+" if v >= 0 else ""
        pct  = abs(v) / bd_sum * 100
        print(f"    {k:<22s}  {b}  {sign}{v:8.1f}  ({pct:.1f}%)")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Dashboard RL DDM")
    ap.add_argument("paths",   nargs="*", help="Fichiers .jsonl")
    ap.add_argument("--dir",   default="", help="Dossier de logs")
    ap.add_argument("--detail",action="store_true", help="Détail par partie")
    args = ap.parse_args()

    # Collecter les fichiers
    files = []
    for p in args.paths:
        if "*" in p:
            files.extend(sorted(Path(".").glob(p)))
        else:
            files.append(Path(p))

    if not files and args.dir:
        files = sorted(Path(args.dir).glob("*.jsonl"), key=lambda p: p.stat().st_mtime)

    if not files:
        for candidate in ["rl/rl_logs", "rl_logs", "."]:
            d = Path(candidate)
            found = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
            if found:
                files = found  # pas de limite — supporte N×4 runs
                break

    if not files:
        sys.exit("Aucun .jsonl trouvé. Usage: python analyze_jsonl_v2.py reward_*.jsonl")

    # Grouper par run_id (tout sauf le suffixe _0000N)
    runs = defaultdict(list)
    for path in sorted(files, key=lambda p: p.stat().st_mtime):
        parts = path.stem.rsplit("_", 1)
        run_id = parts[0] if len(parts) == 2 and parts[1].isdigit() else path.stem
        lines = load_jsonl(path)
        if lines:
            runs[run_id].append(parse_game(lines))

    total_games = sum(len(g) for g in runs.values())
    use_file    = total_games > AUTO_EXPORT_THRESHOLD

    if use_file:
        out_path = Path(f"analyze_{time.strftime('%Y%m%d_%H%M%S')}.md")
        buf = io.StringIO()
        cm  = contextlib.redirect_stdout(buf)
    else:
        out_path = None
        buf      = None
        cm       = contextlib.nullcontext()

    with cm:
        for run_id, games in sorted(runs.items()):
            render_run(run_id, games, detail=args.detail)

        if len(runs) > 1:
            render_global(runs)

        print()

    if use_file:
        out_path.write_text(buf.getvalue(), encoding="utf-8")
        print(f"\n[auto-export] {total_games} parties → {out_path.resolve()}")


if __name__ == "__main__":
    main()
