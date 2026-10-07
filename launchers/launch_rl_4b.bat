@echo off
cd /d "%~dp0.."
set PYTHON=python
set OUT=reports\bracket\rl_tournament\4b_matrix.jsonl
set COMBOS=data\rl_4b_combos.json

echo ============================================================
echo  PHASE 4b - RL TOURNAMENT
echo  Cross f1+D  /  Jaeha f4+C  /  Jin f6+D
echo  Jio   f2+D  /  Neosia f8+C
echo  200 games -- ETA ~20-30 min
echo ============================================================
echo.

start "WATCHER_4b" cmd /k "tools\scripts\watch_rl_tournament.bat %OUT% 200"

timeout /t 2 /nobreak >nul

%PYTHON% tools\scripts\rl_tournament.py --mode both --games 5 --seeds 42,137 --playoff-games 20 --combos-file %COMBOS% --out %OUT%

echo.
echo ============================================================
echo  PHASE 4b TERMINEE
echo ============================================================
pause
