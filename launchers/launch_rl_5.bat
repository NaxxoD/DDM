@echo off
cd /d "%~dp0.."
set PYTHON=python
set OUT=reports\bracket\rl_tournament\5_matrix.jsonl
set COMBOS=data\rl_5_combos.json

echo ============================================================
echo  PHASE 5 - RL TOURNAMENT (2nd choices, greedy variety)
echo  Jin    f6+D  Lycans
echo  Jio    f8+D  Abominations
echo  Cross  f5+A  Orcs
echo  Jaeha  f3+B  Reptiliens
echo  Neosia f1+D  Humains
echo  200 games -- ETA ~20-30 min
echo ============================================================
echo.

start "WATCHER_5" cmd /k "tools\scripts\watch_rl_tournament.bat %OUT% 200"

timeout /t 2 /nobreak >nul

%PYTHON% tools\scripts\rl_tournament.py --mode both --games 5 --seeds 42,137 --playoff-games 20 --combos-file %COMBOS% --out %OUT%

echo.
echo ============================================================
echo  PHASE 5 TERMINEE
echo ============================================================
pause
