# =============================================================================
# ddm_command_reader.py — Lecteur de commandes GUI
#
# Lit command.json écrit par le renderer Pygame et applique la commande
# au GameState. Appelé au début du tour humain à la place de input().
#
# Format command.json :
# {
#   "action":    "invoke",
#   "player":    "A",
#   "ancrage":   [col, row],
#   "shape_idx": 0,
#   "rotation":  2,
#   "niveau":    3,
#   "timestamp": 1234567890
# }
# =============================================================================

import json
import time
import pathlib
import os

# Path relatif au package engine (jamais hardcoder un absolu — cf CLAUDE.md PyGame)
_DEFAULT_COMMAND_PATH = pathlib.Path(__file__).parent / "snapshots" / "_command"

COMMAND_PATH = pathlib.Path(
    os.environ.get("DDM_COMMAND_PATH", str(_DEFAULT_COMMAND_PATH))
)

POLL_INTERVAL = 0.2   # secondes entre deux lectures
TIMEOUT       = 120.0 # secondes avant abandon

# Signal de pause envoyé par le renderer
_PAUSE_PATH = pathlib.Path(__file__).parent / "snapshots" / "pause.json"


def wait_for_command(player: str, timeout: float = TIMEOUT) -> dict | None:
    """
    Attend qu'un command.json valide soit disponible pour ce joueur.
    Retourne le dict de commande ou None si timeout.
    Le timeout est suspendu pendant qu'une pause est active (pause.json présent).
    """
    deadline = time.time() + timeout
    paused_at = None
    while time.time() < deadline:
        # Pause sync : suspend le compte-à-rebours pendant la pause
        if _PAUSE_PATH.exists():
            if paused_at is None:
                paused_at = time.time()
            time.sleep(POLL_INTERVAL)
            continue
        elif paused_at is not None:
            # Reprise : décale la deadline du temps passé en pause
            deadline += time.time() - paused_at
            paused_at = None

        cmd = _read_command()
        if cmd and cmd.get("player") == player:
            _clear_command()
            return cmd
        time.sleep(POLL_INTERVAL)
    print(f"[CMD_READER] Timeout : aucune commande reçue pour J{player}")
    return None


def _read_command() -> dict | None:
    """Lit command.json si présent et valide — avec retry sur erreur JSON."""
    if not COMMAND_PATH.exists():
        return None
    for _ in range(3):
        try:
            with open(COMMAND_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                time.sleep(0.05)
                continue
            return json.loads(content)
        except Exception:
            time.sleep(0.05)
    return None


def _clear_command():
    """Supprime command.json après lecture."""
    try:
        if COMMAND_PATH.exists():
            COMMAND_PATH.unlink()
    except Exception as e:
        print(f"[CMD_READER] Erreur suppression : {e}")


def apply_invocation(cmd: dict, state, player_id: int) -> bool:
    """
    Applique une commande d'invocation au GameState.
    Retourne True si succès.
    """
    from .ddm_p2_board_dice import (
        SHAPES_BY_LEVEL, rotate_pattern, translate_pattern,
        can_place_shape, place_shape, P1_TILE, P2_TILE, P1_QG, P2_QG
    )
    from .ddm_p3_mechanics import spawn_unit_for_player
    from .ddm_p1_core import UNITS

    player_char = "A" if player_id == 1 else "B"
    niveau      = cmd.get("niveau", 1)
    shape_idx   = cmd.get("shape_idx", 0)
    rotation    = cmd.get("rotation", 0)
    ancrage     = cmd.get("ancrage", [0, 0])
    anc_col, anc_row = ancrage

    # Récupère la shape
    shapes = SHAPES_BY_LEVEL.get(niveau, [])
    if not shapes:
        print(f"[CMD_READER] Niveau {niveau} inconnu")
        return False
    if shape_idx >= len(shapes):
        print(f"[CMD_READER] shape_idx {shape_idx} hors limites pour L{niveau}")
        return False

    raw_shape = shapes[shape_idx]

    # translate_pattern place le point (0,0) du pattern normalisé sur (anc_row, anc_col)
    rotated = rotate_pattern(raw_shape, rotation)
    cells = translate_pattern(rotated, anc_row, anc_col)

    # Validation
    player_tiles = {P1_TILE, P1_QG} if player_id == 1 else {P2_TILE, P2_QG}
    if not can_place_shape(state.board, cells, player_tiles):
        print(f"[CMD_READER] Shape invalide pour J{player_char} (niveau {niveau})")
        return False

    # Placement du territoire
    tile_char = P1_TILE if player_id == 1 else P2_TILE
    place_shape(state.board, cells, tile_char)

    # Spawn des unités sur les cases de la shape
    success = spawn_unit_for_player(state, player_char, niveau, cells)

    print(f"[CMD_READER] Invocation L{niveau} appliquée pour J{player_char} "
          f"ancrage=({anc_col},{anc_row}) shape={shape_idx} rot={rotation*90}°")

    # Snapshot immédiat — le renderer voit la shape posée sans attendre la fin du tour
    try:
        from .ddm_snapshot import write_snapshot as _ws
        from .ddm_p1_core import UNITS as _UNITS
        _ws(state, state.board, _UNITS,
            getattr(state, "turn", 1), player_char,
            dice_bag_A=[], dice_bag_B=[])
    except Exception as _e:
        print(f"[CMD_READER] Snapshot post-invoc erreur : {_e}")

    return True
