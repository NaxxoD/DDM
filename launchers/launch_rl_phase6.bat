@echo off
cd /d "%~dp0.."
set PYTHON=python
set OUT=reports\bracket\rl_tournament\phase6_matrix.jsonl
set COMBOS=data\rl_phase6_combos.json
echo ============================================================
echo  PHASE 6 - RL TOURNAMENT (Zenom evaluation)
echo  Jin f6+D / Jio f2+D / Cross f1+D / Jaeha f4+C / Neosia f8+C
echo  Zenom : faction random (pas de combo discovery encore)
echo  6 agents x 15 paires x 2 mirrors x 2 seeds x 5 games = 300 games
echo ============================================================
echo.
start "WATCHER_6" cmd /k "tools\scripts\watch_rl_tournament.bat %OUT% 300"
timeout /t 2 /nobreak >nul
%PYTHON% tools\scripts\rl_tournament.py --mode both --pool jin,jio,cross,jaeha,neosia,zenom --games 5 --seeds 42,137 --playoff-games 20 --combos-file %COMBOS% --out %OUT%
echo.
echo PHASE 6 TERMINEE
pause
