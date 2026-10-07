@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   ALL BALANCE ??? finetune jin/jio/cross avec --balance-sides
REM   But : valider l'hypothese que la balance est generique
REM         (pas specifique a jaeha).
REM   Sequentiel : 3 x ~2h = ~6h total
REM   Save : v1.7/{jin,jio,cross}/
REM ============================================================

set SAVE_DIR=rl\checkpoints\v1.7
set LOG_DIR=logs\all_balance
set STEPS_PER_STAGE=71428

if not exist %SAVE_DIR% mkdir %SAVE_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%

echo ============================================================
echo   ALL BALANCE ??? jin + jio + cross
echo   Save dir : %SAVE_DIR%
echo   Logs     : %LOG_DIR%\
echo ============================================================
echo.

REM Lance le watcher dans une fenetre separee (suivra le run en cours)
echo Lancement watcher (autre fenetre)...
start "All Balance Monitor" cmd /c "tools\scripts\watch_all_balance.bat"
timeout /t 2 /nobreak >nul

call :balance_one jin   rl\checkpoints\v1\jin\jin_claude_final.zip          5101
call :balance_one jio   rl\checkpoints\v2\v2b\jio\jio_final.zip             5202
call :balance_one cross rl\checkpoints\v2\v2d\cross\cross_final.zip         5303

echo.
echo ============================================================
echo   ALL BALANCE TERMINE
echo   3 agents fine-tunes : %SAVE_DIR%\jin\ %SAVE_DIR%\jio\ %SAVE_DIR%\cross\
echo.
echo   Pour evaluer (bracket complet) :
echo     1) Edit rl\bracket.py AGENT_CKPT pour pointer jin/jio/cross vers v1.7
echo     2) launch_bracket.bat post_v17_all both 50
echo ============================================================
pause
exit /b 0


:balance_one
REM args : %1=agent  %2=load_ckpt  %3=seed
set AGENT=%1
set LOAD=%2
set SEED=%3

if not exist %LOAD% (
    echo [ERREUR] Checkpoint introuvable : %LOAD%
    exit /b 1
)

set LOG=%LOG_DIR%\%AGENT%_balance_%TS%.log

echo.
echo --- BALANCE %AGENT% ---
echo   Load     : %LOAD%
echo   Seed     : %SEED%
echo   Log      : %LOG%
echo.

%PYTHON% -m rl.train_ppo ^
    --agent %AGENT% ^
    --load %LOAD% ^
    --curriculum-random ^
    --balance-sides ^
    --timesteps-per-stage %STEPS_PER_STAGE% ^
    --save-dir %SAVE_DIR% ^
    --seed %SEED% > %LOG% 2>&1

if errorlevel 1 (
    echo [ERREUR] balance %AGENT% a echoue. Voir %LOG%
    exit /b 1
)
echo Balance %AGENT% terminee.
exit /b 0
