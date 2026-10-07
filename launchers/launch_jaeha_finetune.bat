@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   JAEHA FINETUNE ??? Option 1 du plan investigation Jaeha
REM   But : reprendre depuis 1.55M (curriculum random interrompu)
REM         et continuer sur le NOUVEAU moteur (post-migration)
REM         pour voir si l'exposition aux nouvelles mecaniques
REM         (surcharge ATK, attack redirection, dice_bag fix)
REM         le renforce sur ses configs faibles.
REM   Resultat dans v1.6/ pour ne pas ecraser v1.5/jaeha/ (prod).
REM ============================================================

set LOAD_CKPT=rl\checkpoints\v1.5\jaeha_repeat\jaeha\jaeha_claude_1551760_steps.zip
set SAVE_DIR=rl\checkpoints\v1.6

if not exist %LOAD_CKPT% (
    echo [ERREUR] Checkpoint introuvable : %LOAD_CKPT%
    pause
    exit /b 1
)
if not exist %SAVE_DIR% mkdir %SAVE_DIR%

set LOG_DIR=logs\jaeha_finetune
if not exist %LOG_DIR% mkdir %LOG_DIR%
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%
set LOG=%LOG_DIR%\jaeha_finetune_%TS%.log

echo ============================================================
echo   JAEHA FINETUNE  (Option 1)
echo   Load     : %LOAD_CKPT%
echo   Save dir : %SAVE_DIR%
echo   Log      : %LOG%
echo.
echo   Curriculum random  - 7 LLM stages tires au hasard
echo   500k steps total   - 7x ~71k steps par stage
echo   Bag size 11        - max-rounds 120
echo   Seed 4242          - different des seeds bracket
echo ============================================================
echo.
echo Demarrage dans 5s... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul

echo Lancement (logs en direct dans %LOG% via PowerShell tee)
echo.
%PYTHON% -m rl.train_ppo ^
    --agent jaeha ^
    --load %LOAD_CKPT% ^
    --curriculum-random ^
    --timesteps-per-stage 71428 ^
    --save-dir %SAVE_DIR% ^
    --seed 4242 > %LOG% 2>&1

if errorlevel 1 (
    echo.
    echo [ERREUR] training a echoue. Voir %LOG%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   FINETUNE TERMINE
echo   Output  : %SAVE_DIR%\jaeha\
echo   Log     : %LOG%
echo.
echo   Pour evaluer le resultat :
echo     python -m rl.bracket pair --side-a jaeha --side-b jio --games 50 --seed 42 --out /tmp/jaeha_v16_test.jsonl
echo.
echo   Ou bracket complet :
echo     1) Editer rl\bracket.py ligne ~52 pour pointer jaeha vers v1.6\jaeha\jaeha_final.zip
echo     2) launch_bracket.bat jaeha_v16_test both 50
echo ============================================================
pause
