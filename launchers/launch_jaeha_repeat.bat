@echo off
cd /d "%~dp0.."
set PYTHON=python
set CKPT=rl\checkpoints\jaeha_repeat

echo ============================================================
echo   JAEHA REPEAT — Accumulation matrice empirique
echo   Phase 1 greedy (500k) -> Phase 2 curriculum random (7x150k)
echo   Chaque run utilise un seed different (timestamp-based)
echo   Matrice empirique mise a jour apres chaque phase 2
echo   Ctrl+C pour arreter
echo ============================================================

set /a RUN=0

:loop
set /a RUN+=1
echo.
echo ============================================================
echo   RUN #%RUN% — $(date /t) $(time /t)
echo ============================================================

REM Seed base = RUN * 1000 pour eviter collisions
set /a SEED_P1=%RUN% * 1000
set /a SEED_P2=%RUN% * 1000 + 1

del /q %CKPT%\jaeha\jaeha.done           2>nul
del /q %CKPT%\jaeha\jaeha_greedy_final.zip 2>nul

echo   Phase 1 — greedy 500k (seed=%SEED_P1%)
start /wait "Jaeha_repeat_P1" %PYTHON% -m rl.train_ppo ^
    --agent jaeha ^
    --opponent greedy ^
    --timesteps 500000 ^
    --seed %SEED_P1% ^
    --save-dir %CKPT%

if not exist %CKPT%\jaeha\jaeha_greedy_final.zip (
    echo [ERREUR] Phase 1 n'a pas produit jaeha_greedy_final.zip — abandon run #%RUN%
    goto loop
)

echo   Phase 2 — curriculum random 7x150k (seed=%SEED_P2%)
start /wait "Jaeha_repeat_P2" %PYTHON% -m rl.train_ppo ^
    --agent jaeha ^
    --load %CKPT%\jaeha\jaeha_greedy_final.zip ^
    --curriculum-random ^
    --timesteps-per-stage 150000 ^
    --seed %SEED_P2% ^
    --save-dir %CKPT%

echo   Run #%RUN% termine — matrice mise a jour.
echo   (Ctrl+C pour arreter, sinon run suivant dans 5s)
timeout /t 5 /nobreak >nul

goto loop
