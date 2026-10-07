@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   NEOSIA PHASE 1 ??? training contre les 4 RL agents
REM   Curriculum : rl:jin -> rl:jio -> rl:cross -> rl:jaeha
REM   Steps/stage : 200k (4 stages = 800k total)
REM   Balance sides : OUI (2A + 2B workers)
REM   Save : rl/checkpoints/neosia/
REM   Estimation : ~4h sur desktop CPU (56 steps/s en RL-vs-RL)
REM
REM   Note : utilise les checkpoints v1.7 prod (jin/cross/jaeha) +
REM          v2b prod (jio). Mix balanced + non-balanced coh??rent.
REM ============================================================

set SAVE_DIR=rl\checkpoints\neosia
set LOG_DIR=logs\neosia_phase1
set STEPS_PER_STAGE=200000

if not exist %SAVE_DIR% mkdir %SAVE_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%
set LOG=%LOG_DIR%\neosia_phase1_%TS%.log

echo ============================================================
echo   NEOSIA PHASE 1 ??? training vs 4 RL agents
echo   Curriculum : rl:jin -^> rl:jio -^> rl:cross -^> rl:jaeha
echo   Steps total: 800k (4 x 200k)
echo   Save dir   : %SAVE_DIR%
echo   Log        : %LOG%
echo   Estimation : ~4h sur desktop CPU
echo ============================================================
echo.
echo Demarrage dans 5s... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul

REM Lance le monitor dans une fenetre separee
echo Lancement du monitor (autre fenetre)...
start "Neosia Phase1 Monitor" cmd /c "tools\scripts\monitor_finetune.bat --agent neosia --save-dir rl/checkpoints/neosia --target-steps 800000 --n-stages 4 --log-dir logs/neosia_phase1"
timeout /t 2 /nobreak >nul

echo Lancement training (logs dans %LOG%)
echo.
%PYTHON% -m rl.train_ppo ^
    --agent neosia ^
    --curriculum ^
    --balance-sides ^
    --timesteps-per-stage %STEPS_PER_STAGE% ^
    --save-dir %SAVE_DIR% ^
    --seed 7777 > %LOG% 2>&1

if errorlevel 1 (
    echo.
    echo [ERREUR] training a echoue. Voir %LOG%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   NEOSIA PHASE 1 TERMINE
echo   Output  : %SAVE_DIR%\neosia_final.zip
echo   Log     : %LOG%
echo.
echo   Pour evaluer (vs les 4 RL) :
echo     python -m rl.bracket pair --side-a jaeha --side-b neosia ^
       --games 50 --seed 42 ^
       --ckpt-b %SAVE_DIR%\neosia_final.zip ^
       --out reports\bracket\neosia_phase1_eval.jsonl
echo.
echo   Pour phase 2 (vs Claude API) :
echo     1) export ANTHROPIC_API_KEY=sk-ant-xxx
echo     2) pip install anthropic
echo     3) launch_neosia_phase2.bat (a creer)
echo ============================================================
pause
