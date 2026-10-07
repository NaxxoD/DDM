"""Génère un récap des combos de prédilection par agent RL.

Aggrège les données de tous les JSONL bracket / eval disponibles, calcule
le WR par (faction, champion) pour chaque agent, et sort un report markdown
avec les top N combos.

Usage :
    python tools/scripts/best_combos.py
    python tools/scripts/best_combos.py --top 5 --min-games 10
    python tools/scripts/best_combos.py --out reports/Report/best_combos.md
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ["jin", "jio", "cross", "jaeha", "neosia"]
LLM_PROFILES = ["chatgpt", "haiku", "gemini", "grok", "mistral", "opus", "sonnet", "deepseek", "qwen3", "glm"]


def collect_jsonl_sources() -> list[Path]:
    """Trouve tous les JSONL bracket pertinents."""
    sources = []
    bracket_dir = ROOT / "reports" / "bracket"
    if bracket_dir.exists():
        # Skip smoke tests
        for p in bracket_dir.rglob("*.jsonl"):
            name = p.name.lower()
            parts = {pp.lower() for pp in p.parts}
            if "smoke" in parts or "smoke" in name:
                continue
            sources.append(p)
    return sources


def load_games_from_jsonl(paths: list[Path]) -> list[dict]:
    games = []
    for p in paths:
        try:
            with p.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("event") == "game_end":
                        games.append(rec)
        except (OSError, PermissionError):
            pass
    return games


def aggregate_per_agent(games: list[dict]) -> dict:
    """Returns {agent: {(f, c): {wins, n}}}."""
    out = {a: defaultdict(lambda: {"wins": 0, "n": 0}) for a in AGENTS}
    for g in games:
        for who, agent in (("a", g.get("side_a")), ("b", g.get("side_b"))):
            if agent not in out:
                continue
            f = g.get(f"faction_{who}")
            c = g.get(f"champion_{who}")
            if f is None or c is None:
                continue
            key = (f, c)
            out[agent][key]["n"] += 1
            if g["winner"] == who:
                out[agent][key]["wins"] += 1
            elif g["winner"] == "draw":
                out[agent][key]["wins"] += 0.5
    return out


def add_eval_multiseed(per_agent: dict, eval_csv: Path):
    """Ajoute les data de eval_multiseed_v1_vs_v2.csv (vs opus)."""
    if not eval_csv.exists():
        return
    import csv
    with eval_csv.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            agent = r.get("agent")
            if agent not in per_agent:
                continue
            try:
                f_ = int(r["faction"])
                c  = r["champion"]
                # On utilise WR v2 (plus récent) sauf pour jin où v1 reste prod
                wr_field = "wr_v1" if agent == "jin" else "wr_v2"
                games_field = "games_v1" if agent == "jin" else "games_v2"
                wr = float(r[wr_field])
                n  = int(r[games_field])
                if n == 0:
                    continue
                per_agent[agent][(f_, c)]["n"] += n
                per_agent[agent][(f_, c)]["wins"] += wr * n
            except (KeyError, ValueError):
                pass


def load_llm_prefs(data_dir: Path) -> dict:
    """Charge les data/{llm}_prefs.json — historique games autorun per combo."""
    out = {p: defaultdict(lambda: {"wins": 0, "n": 0}) for p in LLM_PROFILES}
    for llm in LLM_PROFILES:
        fp = data_dir / f"{llm}_prefs.json"
        if not fp.exists():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key, entry in data.get("history", {}).items():
            # key format: "{faction}_{champion}" ex: "3_A"
            try:
                f_str, c = key.split("_", 1)
                f_ = int(f_str)
            except (ValueError, KeyError):
                continue
            n = int(entry.get("games", 0))
            w = int(entry.get("wins", 0))
            if n == 0:
                continue
            out[llm][(f_, c)]["n"] += n
            out[llm][(f_, c)]["wins"] += w
    return out


def fmt_top_llm(per_llm: dict, top_n: int, min_games: int) -> str:
    """Section markdown pour les profils LLM scriptés."""
    out = []
    out.append("# Combos de prédilection — profils LLM scriptés")
    out.append("")
    out.append(f"> Source : `data/{{llm}}_prefs.json` (historique cumulé games autorun). "
               f"Top {top_n} par profil, min {min_games} games.")
    out.append("")
    for llm in LLM_PROFILES:
        combos = per_llm.get(llm, {})
        rows = [(k, v) for k, v in combos.items() if v["n"] >= min_games]
        if not rows:
            out.append(f"## {llm.upper()}")
            out.append(f"_(aucune donnée >= {min_games} games)_")
            out.append("")
            continue
        rows.sort(key=lambda kv: -(kv[1]["wins"] / kv[1]["n"]))
        total_n = sum(v["n"] for v in combos.values())
        total_w = sum(v["wins"] for v in combos.values())
        mean_wr = (total_w / total_n * 100) if total_n else 0

        # Préférence officielle (depuis le JSON)
        pref_str = ""
        try:
            data = json.loads((ROOT / "data" / f"{llm}_prefs.json").read_text(encoding="utf-8"))
            p = data.get("preferred", {})
            pref_str = f" — préf : f{p.get('faction')}+{p.get('champion')}"
        except Exception:
            pass

        out.append(f"## {llm.upper()}{pref_str}")
        out.append(f"_Total : {total_w}/{total_n} games, mean WR {mean_wr:.1f}%_")
        out.append("")
        out.append("| Rang | Faction | Champion | WR | Games (W/T) |")
        out.append("|---|---|---|--:|--:|")
        for i, ((f_, c), v) in enumerate(rows[:top_n], 1):
            wr = v["wins"] / v["n"] * 100
            out.append(f"| {i} | f{f_} | {c} | **{wr:.1f}%** | {v['wins']}/{v['n']} |")

        # Faction/champion agrégés
        by_f = defaultdict(lambda: {"wins": 0, "n": 0})
        by_c = defaultdict(lambda: {"wins": 0, "n": 0})
        for (f_, c), v in combos.items():
            if v["n"] < min_games:
                continue
            by_f[f_]["wins"] += v["wins"]; by_f[f_]["n"] += v["n"]
            by_c[c]["wins"]  += v["wins"]; by_c[c]["n"]  += v["n"]
        if by_f:
            top_f = sorted(by_f.items(), key=lambda kv: -(kv[1]["wins"]/kv[1]["n"]))[:3]
            top_c = sorted(by_c.items(), key=lambda kv: -(kv[1]["wins"]/kv[1]["n"]))[:3]
            out.append("")
            out.append("**Préférences agrégées** :")
            f_str = " · ".join(f"f{f} ({v['wins']/v['n']*100:.1f}%)" for f, v in top_f)
            c_str = " · ".join(f"{c} ({v['wins']/v['n']*100:.1f}%)" for c, v in top_c)
            out.append(f"- Top factions : {f_str}")
            out.append(f"- Top champions : {c_str}")
        out.append("")
    return "\n".join(out)


def fmt_top(per_agent: dict, top_n: int, min_games: int) -> str:
    out = []
    out.append("# Combos de prédilection par agent RL")
    out.append("")
    out.append(f"> Agrégation tous brackets + eval multiseed. "
               f"Top {top_n} par agent, min {min_games} games.")
    out.append("")
    for a in AGENTS:
        combos = per_agent.get(a, {})
        rows = [(k, v) for k, v in combos.items() if v["n"] >= min_games]
        if not rows:
            out.append(f"## {a.upper()}")
            out.append(f"_(aucune donnée >= {min_games} games)_")
            out.append("")
            continue
        rows.sort(key=lambda kv: -(kv[1]["wins"] / kv[1]["n"]))
        total_n  = sum(v["n"] for v in combos.values())
        total_w  = sum(v["wins"] for v in combos.values())
        mean_wr  = (total_w / total_n * 100) if total_n else 0
        out.append(f"## {a.upper()}")
        out.append(f"_Total : {int(total_w)}/{total_n} games, mean WR {mean_wr:.1f}%_")
        out.append("")
        out.append("| Rang | Faction | Champion | WR | Games (W/T) |")
        out.append("|---|---|---|--:|--:|")
        for i, ((f_, c), v) in enumerate(rows[:top_n], 1):
            wr = v["wins"] / v["n"] * 100
            out.append(f"| {i} | f{f_} | {c} | **{wr:.1f}%** | {v['wins']:.0f}/{v['n']} |")
        # Top combos par faction (toutes champions confondus)
        by_f = defaultdict(lambda: {"wins": 0, "n": 0})
        by_c = defaultdict(lambda: {"wins": 0, "n": 0})
        for (f_, c), v in combos.items():
            if v["n"] < min_games:
                continue
            by_f[f_]["wins"] += v["wins"]; by_f[f_]["n"] += v["n"]
            by_c[c]["wins"]  += v["wins"]; by_c[c]["n"]  += v["n"]
        if by_f:
            top_f = sorted(by_f.items(), key=lambda kv: -(kv[1]["wins"]/kv[1]["n"]))[:3]
            top_c = sorted(by_c.items(), key=lambda kv: -(kv[1]["wins"]/kv[1]["n"]))[:3]
            out.append("")
            out.append("**Préférences agrégées** :")
            f_str = " · ".join(f"f{f} ({v['wins']/v['n']*100:.1f}%)" for f, v in top_f)
            c_str = " · ".join(f"{c} ({v['wins']/v['n']*100:.1f}%)" for c, v in top_c)
            out.append(f"- Top factions : {f_str}")
            out.append(f"- Top champions : {c_str}")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5, help="Top N combos par agent")
    ap.add_argument("--min-games", type=int, default=8,
                    help="Seuil min de games pour qu'un combo apparaisse")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "reports" / "Report" / "best_combos.md")
    args = ap.parse_args()

    # 1. JSONL brackets
    sources = collect_jsonl_sources()
    print(f"[best_combos] {len(sources)} JSONL files found")
    games = load_games_from_jsonl(sources)
    print(f"[best_combos] {len(games)} games chargés")

    per_agent = aggregate_per_agent(games)

    # 2. Add eval_multiseed CSV (vs opus, gros volume statistique)
    eval_csv = ROOT / "reports" / "Report" / "eval_multiseed_v1_vs_v2.csv"
    add_eval_multiseed(per_agent, eval_csv)
    print(f"[best_combos] +eval multiseed CSV : {eval_csv.name}")

    # 3. Stats
    for a in AGENTS:
        n = sum(v["n"] for v in per_agent[a].values())
        print(f"  {a:<8} : {n} games agg, {len(per_agent[a])} combos différents")

    # 4. LLM prefs (historique autorun)
    per_llm = load_llm_prefs(ROOT / "data")
    for llm in LLM_PROFILES:
        n = sum(v["n"] for v in per_llm[llm].values())
        print(f"  {llm:<8} : {n} games (LLM prefs)")

    # 5. Generate reports
    md_rl = fmt_top(per_agent, args.top, args.min_games)
    md_llm = fmt_top_llm(per_llm, args.top, args.min_games)
    md = md_rl + "\n\n---\n\n" + md_llm
    print()
    print(md)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"\n[OK] Écrit : {args.out}")


if __name__ == "__main__":
    main()
