# AutoRuns Proto_DDM (v8.0) — point d'entrée engine.cli_main (refacto 2026-02)
# Lance via: python -m engine.cli_main --mode iaia ...
# Depuis la racine du projet DDM (ou définis DDM_ROOT).

from __future__ import annotations

import csv
import os
import random
import re
import subprocess
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List


# ---------------------------
# Helpers (CLI)
# ---------------------------

def _norm(s: str) -> str:
    return (s or "").strip().lower()


def parse_seed_base(inp: str) -> Optional[int]:
    s = _norm(inp)
    if s in ("", "alea", "aléa", "aleatoire", "aléatoire", "random", "rand", "r"):
        return None
    try:
        return int(s)
    except Exception:
        raise ValueError(f"Seed base invalide: {inp!r}. Mets un entier ou Enter pour aléatoire.")


def ask(prompt: str, default: str = "") -> str:
    if default:
        return input(f"  {prompt} (Enter = {default}) : ").strip()
    return input(f"  {prompt} : ").strip()


def ask_yn(prompt: str, default: str = "o") -> bool:
    d_label = "O/n" if default.lower() in ("o", "y") else "o/N"
    s = input(f"  {prompt} [{d_label}] : ").strip().lower()
    if not s:
        s = default.lower()
    return s in ("y", "yes", "o", "oui", "1", "true", "vrai")


def ask_int(prompt: str, default: int) -> int:
    s = input(f"  {prompt} (Enter = {default}) : ").strip()
    if not s:
        return default
    try:
        return int(s)
    except ValueError:
        print(f"    Invalide, on garde {default}.")
        return default


def ask_menu(title: str, options: List[Tuple[str, object]], default_idx: int = 0) -> object:
    """Menu numéroté — retourne la valeur associée à l'option choisie."""
    print(f"\n  {title}")
    for i, (label, _) in enumerate(options):
        marker = ">" if i == default_idx else " "
        print(f"   {marker} [{i + 1}] {label}")
    s = input(f"    Choix (Enter = {options[default_idx][0]}) : ").strip()
    if not s:
        return options[default_idx][1]
    # Accepter le numéro
    try:
        idx = int(s) - 1
        if 0 <= idx < len(options):
            return options[idx][1]
    except ValueError:
        pass
    # Accepter la valeur directement (ex: "IAIA", "11")
    for label, value in options:
        if s.upper() == str(value).upper() or s.lower() == label.lower().split()[0]:
            return value
    print(f"    Choix non reconnu, défaut : {options[default_idx][0]}")
    return options[default_idx][1]


def _sep(label: str = "", width: int = 60) -> None:
    if label:
        pad = width - len(label) - 6
        print(f"\n  ── {label} {'─' * max(pad, 2)}")
    else:
        print("  " + "─" * width)


# ask_choice conservé pour compat interne
def ask_choice(prompt: str, choices: List[str], default: str) -> str:
    s = ask(f"{prompt} ({'/'.join(choices)})", default=default)
    s = (s.strip() or default).strip()
    if s not in choices:
        print(f"Choix invalide: {s!r} ; attendu: {choices}. On prend {default}.")
        return default
    return s


# ---------------------------
# Project root detection
# ---------------------------

def _find_project_root() -> Path:
    """
    Locate Proto_DDM project root robustly.
    Priority:
      1) env DDM_ROOT
      2) current working directory
      3) script directory and its parents
    Root must contain DDM_Main_split.py or Proto_DDM_Main_split.py.
    """
    def is_root(p: Path) -> bool:
        # Layout refacto: engine/cli_main.py est le point d'entrée
        if (p / "engine" / "cli_main.py").exists():
            return True
        # Fallback legacy
        if (p / "engine" / "Proto_DDM_Main_split.py").exists() or (p / "engine" / "DDM_Main_split.py").exists():
            return True
        return (p / "DDM_Main_split.py").exists() or (p / "Proto_DDM_Main_split.py").exists()

    # 1) explicit override
    env_root = os.environ.get("DDM_ROOT", "").strip()
    if env_root:
        p = Path(env_root).resolve()
        if is_root(p):
            return p

    # 2) script-derived root (robust when launched from tools/autoruns)
    here = Path(__file__).resolve()
    try:
        # If the script is inside .../tools/autoruns/, project root is two levels above.
        if here.parent.name.lower() == "autoruns" and here.parent.parent.name.lower() == "tools":
            cand = here.parents[2]
            if is_root(cand):
                return cand
    except Exception:
        pass

    # 2) CWD (most common when you run from project root)
    cwd = Path.cwd().resolve()
    if is_root(cwd):
        return cwd

    # 3) script folder then parents
    here = Path(__file__).resolve()
    for p in [here.parent, *here.parents]:
        if is_root(p):
            return p

    # last resort: return cwd (and main() will print a clear error)
    return cwd


def _engine_entrypoint_module(root: Path) -> Optional[str]:
    """Return module spec for engine entrypoint if present."""
    if (root / "engine" / "cli_main.py").exists():
        return "engine.cli_main"
    # Fallback legacy
    if (root / "engine" / "Proto_DDM_Main_split.py").exists():
        return "engine.Proto_DDM_Main_split"
    if (root / "engine" / "DDM_Main_split.py").exists():
        return "engine.DDM_Main_split"
    return None


def _entrypoint_py(root: Path) -> Path:
    """
    Priorité: engine/cli_main.py (refacto).
    Fallback: anciens entrypoints à la racine.
    """
    p = root / "engine" / "cli_main.py"
    if p.exists():
        return p
    p2 = root / "DDM_Main_split.py"
    if p2.exists():
        return p2
    p3 = root / "Proto_DDM_Main_split.py"
    if p3.exists():
        return p3
    return p  # will fail later with clear message


def _load_faction_ids(root: Path) -> List[int]:
    """
    Load faction ids deterministically by importing ddm_p1_core and reading FACTIONS_DATA.
    Falls back to [1..8] if anything fails.
    """
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            from engine import ddm_p1_core as P1  # type: ignore
        except Exception:
            import ddm_p1_core as P1  # type: ignore
        if not getattr(P1, "FACTIONS_DATA", None):
            P1.load_factions_data()
        data = getattr(P1, "FACTIONS_DATA", None) or []
        ids: List[int] = []
        for i, f in enumerate(data):
            if isinstance(f, dict) and "id" in f and isinstance(f["id"], int):
                ids.append(int(f["id"]))
            else:
                ids.append(i + 1)
        ids = sorted(list(dict.fromkeys(ids)))
        return ids or list(range(1, 9))
    except Exception:
        return list(range(1, 9))


# ---------------------------
# Parsing engine outputs
# ---------------------------

@dataclass
class RunResult:
    status: str               # OK / DRAW / INCOMPLETE / ERROR / TIMEOUT
    winner: str               # A / B / D / ?
    reason: str               # HQ_DESTROYED / max_rounds / timeout / error / unknown
    elapsed_s: float
    stdout_log: str
    run_id: str


REASON_RE = re.compile(r"\b(?:end_reason|reason)\s*=\s*([a-zA-Z0-9_]+)\b", re.IGNORECASE)


def _parse_winner_and_reason(text: str) -> Tuple[str, str]:
    """
    Parse winner + end reason from engine stdout.
    Prefer SUMMARY_END / GAME_END lines.

    Winner normalization:
      - "A"/"B" = decisive
      - "D"/"DRAW" = draw
      - "?" = unknown (treated as INCOMPLETE)
    """
    low = text.lower()

    if "traceback (most recent call last)" in low:
        # still try to extract winner if present
        m = re.search(r"\bwinner\s*=\s*([a-zA-Z?]+)\b", text, re.IGNORECASE)
        w = (m.group(1) or "?").upper() if m else "?"
        if w in ("DRAW", "D", "TIE"):
            w = "D"
        elif w not in ("A", "B"):
            w = "?"
        return w, "error"

    winner: str = "?"
    reason: str = "unknown"

    # Prefer last SUMMARY_END / GAME_END
    for line in reversed(text.splitlines()):
        if ("SUMMARY_END" in line) or ("GAME_END" in line):
            mw = re.search(r"\bwinner\s*=\s*([a-zA-Z?]+)\b", line, re.IGNORECASE)
            mr = REASON_RE.search(line)
            if mw:
                winner = (mw.group(1) or "?").upper()
            if mr:
                reason = (mr.group(1) or "unknown").lower()
            if mw or mr:
                break

    # normalize winner
    if winner in ("DRAW", "D", "TIE"):
        winner = "D"
    elif winner not in ("A", "B"):
        winner = "?"

    # legacy heuristics
    if winner == "?":
        if ("ia côté a gagne" in low) or ("ia cote a gagne" in low):
            winner, reason = "A", "HQ_DESTROYED"
        elif ("ia côté b gagne" in low) or ("ia cote b gagne" in low):
            winner, reason = "B", "HQ_DESTROYED"

    if reason == "unknown" and "timeout" in low:
        reason = "timeout"

    return winner, reason


# ---------------------------
# Runner
# ---------------------------

def run_one(
    root: Path,
    run_id: str,
    seed: int,
    start: str,
    bag: int,
    max_rounds: int,
    timeout_s: int,
    fa: Optional[int],
    fb: Optional[int],
    mirror: bool,
    sideflip: bool,
    stdout_dir: Path,
    log_dir: Path,
    mode: str = "iaia",
    rl: bool = True,
) -> RunResult:

    main_py = _entrypoint_py(root)
    if not main_py.exists():
        raise FileNotFoundError(f"engine/cli_main.py introuvable depuis root={root}")

    # Build command
    engine_mod = _engine_entrypoint_module(root)
    if engine_mod:
        cmd: List[str] = [
            sys.executable, "-m", engine_mod,
            "--mode", mode.lower(),
            "--seed", str(seed),
            "--bag", str(bag),
            "--max-rounds", str(max_rounds),
            "--start", start,
        ]
    else:
        cmd = [
            sys.executable, str(main_py),
            "--mode", mode.lower(),
            "--seed", str(seed),
            "--bag", str(bag),
            "--max-rounds", str(max_rounds),
            "--start", start,
        ]

    # Factions: if mirror enabled, swap A/B in args (seat-invariant)
    use_fa, use_fb = fa, fb
    if mirror:
        use_fa, use_fb = fb, fa

    if use_fa is not None:
        cmd += ["--faction-a", str(use_fa)]
    if use_fb is not None:
        cmd += ["--faction-b", str(use_fb)]

    if sideflip:
        cmd += ["--sideflip"]

    # Variant label
    if mirror and sideflip:
        variant = "mirror_sideflip"
    elif mirror:
        variant = "mirror"
    elif sideflip:
        variant = "sideflip"
    else:
        variant = "base"

    stdout_log = stdout_dir / f"stdout_run_{run_id}.txt"

    t0 = time.time()
    try:
        env = dict(os.environ)
        env.update({
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "DDM_ROOT": str(root),
            "DDM_AUTORUN": "1",
            "DDM_RL": "1" if rl else "0",
            "DDM_LOG_FAMILY": "autorun",
            "DDM_CAPTURE_STDOUT": "0",
            "DDM_RUN_ID": run_id,
            "DDM_RL_RUN_ID": run_id,  # pour RLLogger game_id
            "DDM_MIRROR": "1" if mirror else "0",
            "DDM_SIDEFLIP": "1" if sideflip else "0",
            "DDM_VARIANT": variant,
            "DDM_LOG_CANON": os.environ.get("DDM_LOG_CANON", "FULL"),
            "DDM_LOG_DIR": str(log_dir),
            "DDM_STDOUT_DIR": str(stdout_dir),
        })

        # Write stdout+stderr to file (and optionally tee to console)
        tee_stdout = os.environ.get("DDM_TEE_STDOUT", "0") == "1"

        with stdout_log.open("w", encoding="utf-8", errors="replace") as f:
            if not tee_stdout:
                cp = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    cwd=str(root),
                    timeout=timeout_s,
                )
            else:
                # Stream lines to both file and this console (useful in autoruns debugging)
                start_t = time.time()
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    cwd=str(root),
                    bufsize=1,
                )
                try:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        f.write(line)
                        f.flush()
                        sys.stdout.write(line)
                        sys.stdout.flush()
                        if timeout_s and (time.time() - start_t) > timeout_s:
                            proc.kill()
                            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_s)
                    rc = proc.wait()
                finally:
                    try:
                        if proc.stdout:
                            proc.stdout.close()
                    except Exception:
                        pass
                cp = subprocess.CompletedProcess(cmd, rc)

        # Best-effort: collect engine-side run logs into log_dir (if engine didn't honor DDM_LOG_DIR)
        try:
            cand_dirs = [
                root / "engine" / "log_data" / "log",
                root / "engine" / "log_data",
                root / "engine" / "logs",
                root / "logs" / "log_data" / "log",
            ]
            cand_names = [
                f"run_{run_id}.log",
                f"run_{run_id}.canon.log",
                f"run_{run_id}.canon.full.log",
            ]
            for d in cand_dirs:
                if not d.exists():
                    continue
                for name in cand_names:
                    src = d / name
                    if src.exists():
                        dst = log_dir / name
                        if src.resolve() != dst.resolve():
                            shutil.copy2(src, dst)
        except Exception:
            pass

        elapsed = time.time() - t0
        txt = stdout_log.read_text(encoding="utf-8", errors="replace")
        winner, reason = _parse_winner_and_reason(txt)

        if cp.returncode != 0:
            return RunResult("ERROR", winner, reason, elapsed, stdout_log.name, run_id)

        if winner == "D":
            return RunResult("DRAW", "D", reason, elapsed, stdout_log.name, run_id)

        if winner not in ("A", "B"):
            # max_rounds sans winner clair = draw
            if reason == "max_rounds":
                return RunResult("DRAW", "D", reason, elapsed, stdout_log.name, run_id)
            return RunResult("INCOMPLETE", "?", reason, elapsed, stdout_log.name, run_id)

        # winner A ou B — max_rounds = nul par convention (pas de vrai vainqueur)
        if reason == "max_rounds":
            return RunResult("DRAW", "D", reason, elapsed, stdout_log.name, run_id)
        return RunResult("OK", winner, reason, elapsed, stdout_log.name, run_id)

    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        return RunResult("TIMEOUT", "?", "timeout", elapsed, stdout_log.name, run_id)


# ---------------------------
# Main
# ---------------------------

def main() -> None:
    W = 62

    print("\n" + "=" * W)
    print("  DDM AutoRuns  v8.0")
    print("=" * W)

    # ─────────────────────────────────────────────────────────────
    #  SECTION 1 — Configuration
    # ─────────────────────────────────────────────────────────────
    _sep("1/4  Configuration")

    pairs     = ask_int("Paires  (1 paire = 1 seed, ×variants)", default=200)

    mode = ask_menu("Mode de jeu", [
        ("IAIA  — IA greedy vs IA greedy",      "IAIA"),
        ("CVIA  — Claude bot vs IA greedy",     "CVIA"),
        ("MVIA  — Mistral bot vs IA greedy",    "MVIA"),
        ("GVIA  — Grok bot vs IA greedy",       "GVIA"),
        ("GEMVIA  — Gemini bot vs IA greedy",   "GEMVIA"),
        ("CGPTVIA — ChatGPT bot vs IA greedy",  "CGPTVIA"),
        ("SNETVIA — Sonnet 4.6 bot vs IA greedy", "SNETVIA"),
        ("OPUSVIA — Opus 4.7 bot vs IA greedy",   "OPUSVIA"),
    ], default_idx=0)

    rl_on = ask_yn("Activer RL  (logs JSONL reward) ?", default="o")

    bag = ask_menu("Sac de dés", [
        ("11 dés  (standard, rapide)", 11),
        ("22 dés  (étendu)",           22),
    ], default_idx=0)

    max_rounds  = ask_int("Max rounds par partie",    default=150)
    timeout_run = ask_int("Timeout par run (s)",      default=900)

    seed_s    = ask("Seed base  (entier ou Enter = aléatoire)", default="")
    seed_base = parse_seed_base(seed_s)

    start_policy = ask_menu("Premier joueur", [
        ("alternate  — A/B en alternance", "alternate"),
        ("random     — aléatoire",         "random"),
        ("A          — toujours A",        "A"),
        ("B          — toujours B",        "B"),
    ], default_idx=0)

    # ─────────────────────────────────────────────────────────────
    #  SECTION 2 — Matchups
    # ─────────────────────────────────────────────────────────────
    _sep("2/4  Matchups")

    # Charger les factions pour affichage + résolution
    root = _find_project_root()
    faction_ids = _load_faction_ids(root)

    _KEYWORD_MAP = {
        "lycan": "lunaire", "loup": "lunaire", "meute": "lunaire",
        "orc": "fureur", "clan": "fureur", "fer": "fureur",
        "abyssal": "abyssal", "demon": "abyssal", "démon": "abyssal", "conclave": "abyssal",
        "egypte": "solaire", "égypte": "solaire", "sphinx": "solaire", "solaire": "solaire",
        "reptil": "scaille", "serpent": "scaille", "scaille": "scaille", "légion": "scaille",
        "humain": "nexus", "citadelle": "nexus", "nexus": "nexus",
        "cyborg": "omega", "omega": "omega", "oméga": "omega",
        "abomination": "abomination", "fractaux": "abomination", "onirique": "abomination",
    }

    _id2name: dict = {}
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            from engine import ddm_p1_core as _P1pre  # type: ignore
        except Exception:
            import ddm_p1_core as _P1pre              # type: ignore
        if not getattr(_P1pre, "FACTIONS_DATA", None):
            _P1pre.load_factions_data()
        _id2name = {
            f.get("id"): (f.get("name") or f.get("nom") or "?")
            for f in (_P1pre.FACTIONS_DATA or [])
        }
        print("\n  Factions disponibles :")
        for fid, fname in sorted(_id2name.items()):
            print(f"    {fid:2}  {fname}")
    except Exception:
        pass

    def _resolve_faction(s: str) -> Optional[int]:
        s = s.strip()
        if s.isdigit():
            return int(s)
        key = s.lower().replace("_", "").replace("-", "").replace("fa", "").replace("fb", "").strip()
        fragment = next((frag for kw, frag in _KEYWORD_MAP.items() if kw in key or key in kw), key)
        try:
            matches = [
                f.get("id") for f in (_P1pre.FACTIONS_DATA or [])
                if fragment in ((f.get("name") or f.get("nom") or "")).lower()
            ]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                print(f"    Ambiguïté '{s}' → ids={matches}, on prend {matches[0]}")
                return matches[0]
            print(f"    Faction introuvable '{s}' — utilise un ID entier")
        except Exception as e:
            print(f"    Erreur résolution '{s}': {e}")
        return None

    print()
    matchup_s = ask(
        "Matchups fixes  ex: 3:5,1:6  (Enter = aléatoire à chaque paire)",
        default=""
    ).strip()

    matchup_list: List[Tuple[Optional[int], Optional[int]]] = []
    if matchup_s:
        for tok in matchup_s.split(","):
            parts = tok.strip().split(":")
            try:
                fam = _resolve_faction(parts[0]) if parts[0].strip() else None
                fbm = _resolve_faction(parts[1]) if len(parts) > 1 and parts[1].strip() else None
                matchup_list.append((fam, fbm))
            except Exception:
                pass
        if matchup_list:
            print("  Matchups résolus :")
            for idx, (fam, fbm) in enumerate(matchup_list):
                na = _id2name.get(fam, f"id={fam}") if fam else "aléatoire"
                nb = _id2name.get(fbm, f"id={fbm}") if fbm else "aléatoire"
                print(f"    P{idx + 1}: A = {na}  vs  B = {nb}")

    fa_fixed: Optional[int] = None
    fb_fixed: Optional[int] = None
    if not matchup_list:
        fa_s = ask("Faction A fixe  (id ou Enter = aléatoire)", default="")
        fb_s = ask("Faction B fixe  (id ou Enter = aléatoire)", default="")
        fa_fixed = int(fa_s) if fa_s.strip().isdigit() else None
        fb_fixed = int(fb_s) if fb_s.strip().isdigit() else None

    # ─────────────────────────────────────────────────────────────
    #  SECTION 3 — Variantes
    # ─────────────────────────────────────────────────────────────
    _sep("3/4  Variantes  (mirror / sideflip)")

    print("  Mirror   : swap A⟷B factions (élimine le biais de côté)")
    mirror_on   = ask_yn("Activer mirror ?",   default="o")
    print("  Sideflip : swap spawns A⟷B (élimine le biais de spawn)")
    sideflip_on = ask_yn("Activer sideflip ?", default="o")

    variants: List[Tuple[str, bool, bool]] = [("base", False, False)]
    if mirror_on:
        variants.append(("mirror",   True,  False))
    if sideflip_on:
        variants.append(("sideflip", False, True))
    if mirror_on and sideflip_on:
        variants.append(("mirror_sideflip", True, True))

    total_runs = pairs * len(variants)

    # ─────────────────────────────────────────────────────────────
    #  SECTION 4 — Récapitulatif + confirmation
    # ─────────────────────────────────────────────────────────────
    _sep("4/4  Récapitulatif")

    ep = _entrypoint_py(root)
    if not ep.exists():
        print(f"\n  Entrypoint introuvable depuis root={root}")
        print(f"  CWD = {Path.cwd().resolve()}")
        print("  Lance depuis la racine du projet DDM  ou définis DDM_ROOT")
        sys.exit(2)

    engine_mod = _engine_entrypoint_module(root)
    ep_label   = engine_mod if engine_mod else ep.name
    seed_label = str(seed_base) if seed_base is not None else "aléatoire"

    v_labels = " + ".join(v[0] for v in variants)
    if matchup_list:
        mu_label = f"{len(matchup_list)} matchup(s) fixes (cycle)"
    elif fa_fixed or fb_fixed:
        fa_n = _id2name.get(fa_fixed, f"id={fa_fixed}") if fa_fixed else "aléatoire"
        fb_n = _id2name.get(fb_fixed, f"id={fb_fixed}") if fb_fixed else "aléatoire"
        mu_label = f"A={fa_n}  B={fb_n}"
    else:
        mu_label = "aléatoire à chaque paire"

    print(f"\n  {'Entrypoint':<16}: {ep_label}")
    print(f"  {'Root':<16}: {root}")
    print()
    print(f"  {'Mode':<16}: {mode}")
    print(f"  {'RL (JSONL)':<16}: {'oui' if rl_on else 'non'}")
    print(f"  {'Paires':<16}: {pairs}")
    print(f"  {'Variantes':<16}: {len(variants)}  ({v_labels})")
    print(f"  {'Total runs':<16}: {total_runs}")
    print(f"  {'Bag':<16}: {bag} dés")
    print(f"  {'Max rounds':<16}: {max_rounds}")
    print(f"  {'Timeout/run':<16}: {timeout_run}s")
    print(f"  {'Seed base':<16}: {seed_label}")
    print(f"  {'Start policy':<16}: {start_policy}")
    print(f"  {'Matchups':<16}: {mu_label}")
    print()

    if not ask_yn("Lancer le batch ?", default="o"):
        print("\n  Annulé.")
        return

    # ─────────────────────────────────────────────────────────────
    #  RUN
    # ─────────────────────────────────────────────────────────────
    base_out   = root / "logs" / "autorun_log_data"
    stdout_dir = base_out / "stdout"
    log_dir    = base_out / "log"
    csv_dir    = base_out / "csv"
    for d in (stdout_dir, log_dir, csv_dir):
        d.mkdir(parents=True, exist_ok=True)

    batch_id = time.strftime("%Y%m%d_%H%M%S")
    csv_path = csv_dir / f"auto_runs_{batch_id}.csv"

    print(f"\n  Batch : {batch_id}  ({total_runs} runs)")
    print("  " + "─" * W)

    rng_global  = random.Random(seed_base) if seed_base is not None else random.Random()
    run_counter = 0

    with csv_path.open("w", newline="", encoding="utf-8") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=[
            "batch_id", "run_id", "pair_idx", "variant",
            "seed", "start", "mirror", "sideflip",
            "faction_a", "faction_b",
            "status", "winner", "reason",
            "elapsed_s", "stdout_log",
        ])
        w.writeheader()

        for i in range(1, pairs + 1):
            seed = rng_global.getrandbits(31)
            if start_policy == "alternate":
                start = "A" if (i % 2 == 1) else "B"
            elif start_policy == "random":
                start = rng_global.choice(["A", "B"])
            else:
                start = start_policy

            if matchup_list:
                fam, fbm = matchup_list[(i - 1) % len(matchup_list)]
                fa = fam if fam is not None else rng_global.choice(faction_ids)
                fb = fbm if fbm is not None else rng_global.choice(faction_ids)
            else:
                fa = fa_fixed if fa_fixed is not None else rng_global.choice(faction_ids)
                fb = fb_fixed if fb_fixed is not None else rng_global.choice(faction_ids)
            if fb_fixed is None and not matchup_list and fa == fb and len(faction_ids) > 1:
                for _ in range(10):
                    cand = rng_global.choice(faction_ids)
                    if cand != fa:
                        fb = cand
                        break

            for vname, mir, sflip in variants:
                run_counter += 1
                run_id = f"{batch_id}_{run_counter:05d}"

                res = run_one(
                    root=root,
                    run_id=run_id,
                    seed=seed,
                    start=start,
                    bag=bag,
                    max_rounds=max_rounds,
                    timeout_s=timeout_run,
                    fa=fa,
                    fb=fb,
                    mirror=mir,
                    sideflip=sflip,
                    stdout_dir=stdout_dir,
                    log_dir=log_dir,
                    mode=mode,
                    rl=rl_on,
                )

                fa_n = _id2name.get(fa, str(fa))
                fb_n = _id2name.get(fb, str(fb))
                print(
                    f"  [{run_counter:04d}/{total_runs}]  {vname:<16}"
                    f"  {fa_n[:18]:<18} vs {fb_n[:18]:<18}"
                    f"  {res.status:<8}  W={res.winner}  {res.elapsed_s:.1f}s"
                )

                w.writerow({
                    "batch_id":   batch_id,
                    "run_id":     run_id,
                    "pair_idx":   i,
                    "variant":    vname,
                    "seed":       seed,
                    "start":      start,
                    "mirror":     int(mir),
                    "sideflip":   int(sflip),
                    "faction_a":  fa,
                    "faction_b":  fb,
                    "status":     res.status,
                    "winner":     res.winner,
                    "reason":     res.reason,
                    "elapsed_s":  f"{res.elapsed_s:.3f}",
                    "stdout_log": res.stdout_log,
                })

    print("\n  " + "─" * W)
    print(f"  Termine.  {total_runs} runs  |  CSV : {csv_path}")
    print(f"  Logs stdout : {stdout_dir}")


if __name__ == "__main__":
    main()
