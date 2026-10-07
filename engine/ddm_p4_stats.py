"""
ddm_p4_stats.py
Tracker de statistiques persistant (faction_stats.json, schema v2).
Extrait de ddm_p4_loop.py lors du refacto 2026-02.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

_STATS_SCHEMA_VERSION = 2


def _ddm_stats_default_path() -> str:
    p = os.environ.get("DDM_STATS_PATH")
    if p:
        return p
    try:
        base = os.path.dirname(__file__)
        return os.path.join(base, "..", "data", "faction_stats.json")
    except Exception:
        return os.path.join("data", "faction_stats.json")


def _utc_now_iso() -> str:
    try:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return str(datetime.utcnow())


def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


class DDMStatsTracker:
    """Agrégateur de stats persistant sur JSON (schema v2)."""

    def __init__(self, path: str):
        self.path = path
        self.data = None
        self._dirty = False
        self._run_meta = {
            "run_id": None,
            "mode": None,
            "seed": None,
            "bag": None,
            "variant": os.environ.get("DDM_VARIANT", "base"),
            "started_utc": _utc_now_iso(),
            "factionA": None,
            "factionB": None,
            "champA": None,
            "champB": None,
            "sideflip": None,
        }
        self._load_or_reset()

    def _blank(self):
        return {
            "schema_version": _STATS_SCHEMA_VERSION,
            "generated_utc": _utc_now_iso(),
            "runs": {"total": 0, "by_mode": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0}},
            "factions": {},
            "units": {},
            "ttk": {"sum_turns": 0, "n": 0},
            "hq_damage": {"A": {"sum": 0, "n": 0}, "B": {"sum": 0, "n": 0}},
            "last_runs": [],
        }

    def _backup(self, reason: str):
        try:
            if os.path.exists(self.path):
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                bak = f"{self.path}.bak_{reason}_{ts}"
                os.replace(self.path, bak)
        except Exception:
            pass

    def _load_or_reset(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and d.get("schema_version") == _STATS_SCHEMA_VERSION:
                    self.data = d
                    return
                self._backup("schema_mismatch")
        except Exception:
            self._backup("unreadable")
        self.data = self._blank()
        self._dirty = True

    def set_run_meta(self, **kw):
        for k, v in kw.items():
            if k in self._run_meta:
                self._run_meta[k] = v
        self._dirty = True

    def _ensure_faction(self, faction_name: str):
        if faction_name not in self.data["factions"]:
            self.data["factions"][faction_name] = {
                "picks": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "wins": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "losses": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "draws": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "games": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
            }

    def _ensure_unit(self, unit_name: str, faction_name: str | None = None,
                     level: int | None = None, unit_type: str | None = None):
        u = self.data["units"].get(unit_name)
        if not u:
            u = {
                "faction": faction_name or "?",
                "type": unit_type or "?",
                "level": level if level is not None else None,
                "offered": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "picked": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "spawns": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "deaths": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "kills": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "damage_done": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "damage_taken": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "ttk_sum": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
                "ttk_n": {"iaia": 0, "hvia": 0, "hvh": 0, "console": 0},
            }
            self.data["units"][unit_name] = u
        if faction_name and (u.get("faction") in (None, "", "?")):
            u["faction"] = faction_name
        if unit_type and (u.get("type") in (None, "", "?")):
            u["type"] = unit_type
        if level is not None and u.get("level") is None:
            u["level"] = level
        return u

    def start_game(self, mode: str, factionA: str, factionB: str):
        mode = mode or "console"
        self._run_meta["mode"] = mode
        self._ensure_faction(factionA)
        self._ensure_faction(factionB)
        self.data["factions"][factionA]["picks"][mode] += 1
        self.data["factions"][factionB]["picks"][mode] += 1
        self.data["factions"][factionA]["games"][mode] += 1
        self.data["factions"][factionB]["games"][mode] += 1
        self.data["runs"]["total"] += 1
        if mode not in self.data["runs"]["by_mode"]:
            self.data["runs"]["by_mode"][mode] = 0
        self.data["runs"]["by_mode"][mode] += 1
        self._dirty = True

    def note_unit_offered(self, mode: str, unit_name: str, faction_name: str,
                          level: int, unit_type: str = "mob"):
        mode = mode or "console"
        u = self._ensure_unit(unit_name, faction_name=faction_name, level=level, unit_type=unit_type)
        u["offered"][mode] += 1
        self._dirty = True

    def note_unit_picked(self, mode: str, unit_name: str, faction_name: str,
                         level: int, unit_type: str = "mob"):
        mode = mode or "console"
        u = self._ensure_unit(unit_name, faction_name=faction_name, level=level, unit_type=unit_type)
        u["picked"][mode] += 1
        self._dirty = True

    def note_unit_spawn(self, mode: str, unit_name: str, faction_name: str,
                        level: int, unit_type: str = "mob"):
        mode = mode or "console"
        u = self._ensure_unit(unit_name, faction_name=faction_name, level=level, unit_type=unit_type)
        u["spawns"][mode] += 1
        self._dirty = True

    def note_unit_death(self, mode: str, unit_name: str, faction_name: str,
                        level: int, ttk_turns: int | None = None, unit_type: str = "mob"):
        mode = mode or "console"
        u = self._ensure_unit(unit_name, faction_name=faction_name, level=level, unit_type=unit_type)
        u["deaths"][mode] += 1
        if ttk_turns is not None and ttk_turns >= 0:
            u["ttk_sum"][mode] += int(ttk_turns)
            u["ttk_n"][mode] += 1
            self.data["ttk"]["sum_turns"] += int(ttk_turns)
            self.data["ttk"]["n"] += 1
        self._dirty = True

    def note_unit_kill(self, mode: str, killer_name: str, faction_name: str | None = None,
                       level: int | None = None, unit_type: str = "?"):
        mode = mode or "console"
        u = self._ensure_unit(killer_name, faction_name=faction_name, level=level, unit_type=unit_type)
        u["kills"][mode] += 1
        self._dirty = True

    def note_damage(self, mode: str, attacker_name: str | None, target_name: str | None,
                    dmg: int, attacker_meta: dict | None = None, target_meta: dict | None = None):
        mode = mode or "console"
        dmg = _safe_int(dmg, 0)
        if dmg <= 0:
            return
        if attacker_name:
            a = self._ensure_unit(attacker_name,
                                  faction_name=(attacker_meta or {}).get("faction"),
                                  level=(attacker_meta or {}).get("level"),
                                  unit_type=(attacker_meta or {}).get("type"))
            a["damage_done"][mode] += dmg
        if target_name:
            t = self._ensure_unit(target_name,
                                  faction_name=(target_meta or {}).get("faction"),
                                  level=(target_meta or {}).get("level"),
                                  unit_type=(target_meta or {}).get("type"))
            t["damage_taken"][mode] += dmg
        self._dirty = True

    def note_hq_damage(self, mode: str, hq_side: str, dmg: int):
        mode = mode or "console"
        dmg = _safe_int(dmg, 0)
        if dmg <= 0 or hq_side not in ("A", "B"):
            return
        self.data["hq_damage"][hq_side]["sum"] += dmg
        self.data["hq_damage"][hq_side]["n"] += 1
        self._dirty = True

    def finish_game(self, winner: str, rounds: int, reason: str):
        mode = self._run_meta.get("mode") or "console"
        factionA = self._run_meta.get("factionA") or "?"
        factionB = self._run_meta.get("factionB") or "?"
        self._ensure_faction(factionA)
        self._ensure_faction(factionB)
        if winner in ("A", "B"):
            win_f = factionA if winner == "A" else factionB
            lose_f = factionB if winner == "A" else factionA
            self.data["factions"][win_f]["wins"][mode] += 1
            self.data["factions"][lose_f]["losses"][mode] += 1
        else:
            self.data["factions"][factionA]["draws"][mode] += 1
            self.data["factions"][factionB]["draws"][mode] += 1
        try:
            entry = dict(self._run_meta)
            entry.update({
                "ended_utc": _utc_now_iso(),
                "winner": winner,
                "rounds": _safe_int(rounds, 0),
                "reason": reason,
            })
            self.data["last_runs"].append(entry)
            if len(self.data["last_runs"]) > 80:
                self.data["last_runs"] = self.data["last_runs"][-80:]
        except Exception:
            pass
        self.data["generated_utc"] = _utc_now_iso()
        self._dirty = True
        self.save()

    def save(self):
        if not self._dirty:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except Exception:
            pass
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self._dirty = False
        except Exception:
            pass


def attach_stats_tracker(state, mode: str, run_id: str | None, *,
                         bag_size: int | None = None,
                         seed: int | None = None,
                         factionA: str | None = None,
                         factionB: str | None = None,
                         champA: str | None = None,
                         champB: str | None = None,
                         sideflip: int | None = None):
    """Attache un DDMStatsTracker au state + wrap damage_hq pour agréger les dégâts QG."""
    try:
        tracker = DDMStatsTracker(_ddm_stats_default_path())
        state.stats = tracker
        state.run_mode = mode or "console"
        tracker.set_run_meta(
            run_id=run_id,
            mode=state.run_mode,
            seed=seed,
            bag=bag_size,
            factionA=factionA,
            factionB=factionB,
            champA=champA,
            champB=champB,
            sideflip=sideflip,
        )
        if factionA and factionB:
            tracker.start_game(state.run_mode, factionA, factionB)

        if hasattr(state, "damage_hq") and not getattr(state.damage_hq, "_stats_wrapped", False):
            orig = state.damage_hq

            def _wrapped_damage_hq(side, dmg, *a, **kw):
                try:
                    tracker.note_hq_damage(state.run_mode, str(side), int(dmg))
                except Exception:
                    pass
                return orig(side, dmg, *a, **kw)

            try:
                _wrapped_damage_hq._stats_wrapped = True
            except Exception:
                pass
            state.damage_hq = _wrapped_damage_hq
    except Exception:
        pass
