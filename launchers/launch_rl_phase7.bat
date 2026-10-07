@echo off
cd /d "%~dp0.."
set PYTHON=python
set OUT=reports\bracket\rl_tournament\phase7_matrix.jsonl
set COMBOS=data\rl_phase7_combos.json
echo ============================================================
echo  PHASE 7 - RL TOURNAMENT (Zenom combo optimise)
echo  Cross f1+D / Jio f2+D / Zenom f3+B / Jaeha f4+C
echo  Jin f6+D / Neosia f8+C  ? 6 factions distinctes
echo  300 games group + BO20 playoffs
echo ============================================================
echo.
start "WATCHER_7" cmd /k "tools\scripts\watch_rl_tournament.bat %OUT% 300"
timeout /t 2 /nobreak >nul
%PYTHON% tools\scripts\rl_tournament.py --mode both --pool jin,jio,cross,jaeha,neosia,zenom --games 5 --seeds 42,137 --playoff-games 20 --combos-file %COMBOS% --out %OUT%
echo.
echo PHASE 7 TERMINEE
pause
