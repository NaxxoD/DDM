"""Proto_DDM CLI launcher.

Run from project root:
python -m engine.cli_main

Or from inside engine/:
python cli_main.py

This file only forwards execution to engine.ddm_p4_loop.main().
"""

from __future__ import annotations


def _get_main():
    # When executed with `-m engine.cli_main`, relative import is required.
    try:
        from .ddm_p4_loop import main
        return main
    except Exception:
        # Fallback for `python cli_main.py` when cwd == engine/
        from ddm_p4_loop import main
        return main


def run():
    main = _get_main()
    return main()


if __name__ == "__main__":
    raise SystemExit(run() or 0)
