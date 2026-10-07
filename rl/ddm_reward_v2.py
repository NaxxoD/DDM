from __future__ import annotations

import atexit
import json
import os
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass
class RewardCfg:
    # Terminal
    win: float = 1.0
    loss: float = -1.0
    draw: float = 0.0

    # Offense
    qg_damage_per_point: float = 0.05
    mate_threat: float = 0.3
    kill_enemy: float = 0.1

    # Defense / risk
    lose_self: float = -0.15
    my_hq_reachable: float = -0.4
    hq_threat_delta: float = 0.03  # (threats_start - threats_end) * weight
    # ally_intercept continu supprimé — remplacé par signaux one-shot
    new_infiltrator: float = 0.25  # 1er tour de détection d'un infiltrateur ET allié en position
    intercept_kill:  float = 0.35  # kill ce tour ET ally_intercept était True au tour précédent

    # Tempo
    tempo_step: float = 0.02      # (min_dist_start - min_dist_end) * weight

    # Waste / inefficiency
    void_action: float = -0.05
    pass_avoidable: float = -0.02
    unused_pool_per_point: float = -0.001  # pool CAP/ATK/DEF/MOVE inutilisés (réduit: signal trop dominant)

    # Time pressure
    turn_tax: float = -0.001


def _normalize_event(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    # normalisation douce : TURN_END / EPISODE_END
    s = s.replace(" ", "_").replace("-", "_").upper()
    return s


def _guess_episode_id(obj: Dict[str, Any]) -> str:
    """Best-effort id for grouping records."""
    for k in ("episode_id", "game_id", "match_id", "episode", "uid"):
        v = obj.get(k)
        if v is not None and str(v).strip():
            return str(v)
    # fallback: sometimes only run_id exists (less ideal)
    v = obj.get("run_id")
    if v is not None and str(v).strip():
        return str(v)
    return "NO_EPISODE_ID"


def _extract_reward(obj: Dict[str, Any]) -> float:
    for k in ("reward", "r", "delta_reward", "dr"):
        v = obj.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    # episode mode may already produce a total
    v = obj.get("total_reward")
    if isinstance(v, (int, float)):
        return float(v)
    return 0.0


def _infer_event(obj: Dict[str, Any]) -> str:
    """Infer a coarse event type for one JSONL record.

    Default: TURN_END (logger called once per turn).
    If we detect a terminal signal we return EPISODE_END so 'episode' granularity works.
    """
    # explicit event / type fields
    for k in ("event", "type", "ev", "kind", "tag", "name"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return _normalize_event(v)

    terminal = obj.get("terminal")
    if terminal is not None and terminal != "" and terminal is not False:
        return "EPISODE_END"

    # Best-effort terminal detection from HQ values (works even if the engine didn't set 'terminal')
    hq = obj.get("hq")
    if isinstance(hq, dict):
        a = hq.get("A")
        b = hq.get("B")
        try:
            if a is not None and b is not None and (a <= 0 or b <= 0):
                return "EPISODE_END"
        except Exception:
            pass

    return "TURN_END"


@dataclass
class _EpisodeAgg:
    episode_id: str
    started_at: float = field(default_factory=time.time)
    n_records: int = 0
    n_turns: int = 0
    total_reward: float = 0.0
    breakdown_sum: Dict[str, float] = field(default_factory=dict)

    # optional metadata (keep last seen)
    winner: Any = None
    reason: Any = None
    terminal: Any = None

    def add(self, record: Dict[str, Any], event: str) -> None:
        self.n_records += 1
        if event == "TURN_END":
            self.n_turns += 1

        r = _extract_reward(record)
        self.total_reward += r

        bd = record.get("breakdown")
        if isinstance(bd, dict):
            for k, v in bd.items():
                if isinstance(v, (int, float)):
                    self.breakdown_sum[k] = self.breakdown_sum.get(k, 0.0) + float(v)

        if "winner" in record:
            self.winner = record.get("winner")
        if "reason" in record:
            self.reason = record.get("reason")
        if "terminal" in record:
            self.terminal = record.get("terminal")


class RLLogger:
    """
    JSONL logger for reward traces.

    Env vars:
      - DDM_RL_PATH: full output file path (overrides everything)
      - DDM_RL_RUN_ID: explicit run id (default timestamp)
      - DDM_RL_GRANULARITY: 'turn' (default) or 'episode'

    In 'turn' mode: writes one line per write() call.
    In 'episode' mode: buffers by episode_id, and writes ONE aggregated line at EPISODE_END.
    """

    def __init__(self, run_id: Optional[str] = None, path: Optional[str] = None):
        self.run_id = run_id or os.environ.get("DDM_RL_RUN_ID") or time.strftime("%Y%m%d_%H%M%S")
        self.granularity = (os.environ.get("DDM_RL_GRANULARITY") or "turn").strip().lower()
        if self.granularity not in ("turn", "episode"):
            self.granularity = "turn"

        # 1) env override
        env_path = os.environ.get("DDM_RL_PATH")
        if env_path:
            self.path = Path(env_path)
        elif path:
            self.path = Path(path)
        else:
            # Optional override for log directory (handy for Autoruns / multiple workspaces)
            outdir_env = os.environ.get("DDM_RL_LOGDIR")
            if outdir_env:
                outdir = Path(outdir_env)
            else:
                # default: rl/rl_logs alongside this file
                base = Path(__file__).resolve().parent
                outdir = base / "rl_logs"

            outdir.mkdir(parents=True, exist_ok=True)
            self.path = outdir / f"reward_{self.run_id}.jsonl"

        self._episodes: Dict[str, _EpisodeAgg] = {}

        # flush best-effort at exit (only meaningful in episode mode)
        atexit.register(self.close)

    def _write_line(self, record: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write(self, record: Dict[str, Any]) -> None:
        # add stable fields
        if "run_id" not in record:
            record["run_id"] = self.run_id

        # ensure a non-null game_id (helps analysis; default = run_id)
        if record.get("game_id") is None:
            record["game_id"] = record["run_id"]

        event = _infer_event(record)
        record["event"] = event

        if self.granularity == "turn":
            # keep as-is, just ensure event field exists
            self._write_line(record)
            return

        # --- episode granularity ---
        eid = _guess_episode_id(record)
        agg = self._episodes.get(eid)
        if agg is None:
            agg = _EpisodeAgg(episode_id=eid)
            self._episodes[eid] = agg

        agg.add(record, event)

        if event == "EPISODE_END":
            out = {
                "event": "EPISODE_END",
                "granularity": "episode",
                "run_id": self.run_id,
                "game_id": eid,
                "total_reward": agg.total_reward,
                "turns": agg.n_turns,
                "records": agg.n_records,
                "breakdown_sum": agg.breakdown_sum,
                "winner": agg.winner,
                "reason": agg.reason,
                "terminal": agg.terminal,
                "started_at": agg.started_at,
                "ended_at": time.time(),
            }
            self._write_line(out)
            del self._episodes[eid]

    def close(self) -> None:
        """Flush any unfinished episodes (best-effort)."""
        if self.granularity != "episode":
            return
        # avoid double flush (atexit)
        if not self._episodes:
            return

        now = time.time()
        for eid, agg in list(self._episodes.items()):
            out = {
                "event": "EPISODE_END",
                "granularity": "episode",
                "run_id": self.run_id,
                "game_id": eid,
                "total_reward": agg.total_reward,
                "turns": agg.n_turns,
                "records": agg.n_records,
                "breakdown_sum": agg.breakdown_sum,
                "winner": agg.winner,
                "reason": agg.reason or "FORCED_FLUSH",
                "terminal": agg.terminal,
                "started_at": agg.started_at,
                "ended_at": now,
            }
            self._write_line(out)
            del self._episodes[eid]


def compute_reward_12(ctx: Dict[str, Any], cfg: Optional[RewardCfg] = None) -> Tuple[float, Dict[str, float]]:
    """Return (reward, breakdown). Missing fields default to 0/False."""
    cfg = cfg or RewardCfg()

    dmg_qg = float(ctx.get("dmg_qg", 0) or 0)
    mate_threat = 1.0 if ctx.get("mate_threat", False) else 0.0
    kills_enemy = float(ctx.get("kills_enemy", 0) or 0)
    losses_self = float(ctx.get("losses_self", 0) or 0)

    my_hq_reachable  = 1.0 if ctx.get("my_hq_reachable", False) else 0.0
    new_infiltrator  = 1.0 if ctx.get("new_infiltrator", False) else 0.0
    intercept_kill   = 1.0 if ctx.get("intercept_kill", False) else 0.0

    threats_start = float(ctx.get("hq_threats_start", 0) or 0)
    threats_end = float(ctx.get("hq_threats_end", 0) or 0)
    threat_delta = threats_start - threats_end

    dist_start = float(ctx.get("min_dist_enemy_hq_start", 0) or 0)
    dist_end = float(ctx.get("min_dist_enemy_hq_end", 0) or 0)
    tempo_delta = dist_start - dist_end

    void_action = 1.0 if ctx.get("void_action", False) else 0.0
    pass_avoidable = 1.0 if ctx.get("pass_avoidable", False) else 0.0

    unused_total = float(ctx.get("unused_pool_total", 0) or 0)
    # Pass forcé (pas de ressource) → pas de pénalité sur les pools inutilisés
    pass_forced = bool(ctx.get("pass_forced", False))
    if pass_forced:
        unused_total = 0.0

    # Terminal
    terminal = ctx.get("terminal")  # 'win'|'loss'|'draw'|None
    terminal_r = 0.0
    if terminal == "win":
        terminal_r = cfg.win
    elif terminal == "loss":
        terminal_r = cfg.loss
    elif terminal == "draw":
        terminal_r = cfg.draw

    breakdown = {
        "terminal": terminal_r,
        "qg_damage": dmg_qg * cfg.qg_damage_per_point,
        "mate_threat": mate_threat * cfg.mate_threat,
        "kill_enemy": kills_enemy * cfg.kill_enemy,
        "lose_self": losses_self * cfg.lose_self,
        "my_hq_reachable": my_hq_reachable * cfg.my_hq_reachable,
        "new_infiltrator": new_infiltrator * cfg.new_infiltrator,
        "intercept_kill":  intercept_kill  * cfg.intercept_kill,
        "hq_threat_delta": threat_delta * cfg.hq_threat_delta,
        "tempo": tempo_delta * cfg.tempo_step,
        "void_action": void_action * cfg.void_action,
        "pass_avoidable": pass_avoidable * cfg.pass_avoidable,
        "unused_pool": unused_total * cfg.unused_pool_per_point,  # 0 si pass_forced
        "turn_tax": cfg.turn_tax,
    }

    reward = sum(breakdown.values())
    return reward, breakdown


def default_cfg_dict() -> Dict[str, Any]:
    return asdict(RewardCfg())
