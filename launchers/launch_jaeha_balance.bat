@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   JAEHA BALANCE ??? corrige l'asymetrie A/B detectee post-v1.6
REM   Charge depuis v1.6 (dernier finetune) et continue 500k steps
REM   avec --balance-sides : 2 workers cote A + 2 workers cote B
REM   Resultat dans v1.7/jaeha/
REM ============================================================

set LOAD_CKPT=rl\checkpoints\v1.6\jaeha\jaeha_final.zip
set SAVE_DIR=rl\checkpoints\v1.7

if not exist %LOAD_CKPT% (
    echo [ERREUR] Checkpoint introuvable : %LOAD_CKPT%
    pause
    exit /b 1
)
if not exist %SAVE_DIR% mkdir %SAVE_DIR%

set LOG_DIR=logs\jaeha_balance
if not exist %LOG_DIR% mkdir %LOG_DIR%
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%
set LOG=%LOG_DIR%\jaeha_balance_%TS%.log

echo ============================================================
echo   JAEHA BALANCE  (correctif asymetrie A/B)
echo   Load     : %LOAD_CKPT%   (v1.6 final, asym +20pts cote A)
echo   Save dir : %SAVE_DIR%
echo   Log      : %LOG%
echo.
echo   Curriculum random  - 7 LLM stages tires au hasard
echo   500k steps total   - ~71k steps par stage
echo   Balance sides      - 2 workers A + 2 workers B
echo   Seed 5252          - different des seeds precedents
echo ============================================================
echo.
echo Demarrage dans 5s... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul

REM Lance le monitor dans une fenetre separee
echo Lancement du monitor (autre fenetre)...
start "Jaeha Balance Monitor" cmd /c "tools\scripts\monitor_finetune.bat --save-dir rl/checkpoints/v1.7 --target-steps 500000"

echo Lancement training (logs dans %LOG%)
echo.
%PYTHON% -m rl.train_ppo ^
    --agent jaeha ^
    --load %LOAD_CKPT% ^
    --curriculum-random ^
    --balance-sides ^
    --timesteps-per-stage 71428 ^
    --save-dir %SAVE_DIR% ^
    --seed 5252 > %LOG% 2>&1

if errorlevel 1 (
    echo.
    echo [ERREUR] training a echoue. Voir %LOG%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BALANCE TERMINE
echo   Output  : %SAVE_DIR%\jaeha\
echo.
echo   Pour evaluer (mirror a + mirror b vs jio) :
echo     python -m rl.bracket pair --side-a jaeha --side-b jio --games 50 --seed 42 --mirror a --ckpt-a %SAVE_DIR%\jaeha\jaeha_final.zip --out reports\bracket\jaeha_v17_quick.jsonl
echo     python -m rl.bracket pair --side-a jio --side-b jaeha --games 50 --seed 42 --mirror b --ckpt-b %SAVE_DIR%\jaeha\jaeha_final.zip --out reports\bracket\jaeha_v17_quick.jsonl
echo.
echo   Pour suivre :
echo     tools\scripts\monitor_finetune.bat --save-dir rl/checkpoints/v1.7 --target-steps 500000
echo ============================================================
pause
