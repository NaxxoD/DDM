@echo off
cd /d "%~dp0.."
set PYTHON=python
set OUT=rl\checkpoints\eval_multiseed
set LOGDIR=logs\eval_multiseed
set SENTDIR=%LOGDIR%\sentinels
set PYTHONIOENCODING=utf-8

if not exist %LOGDIR%   mkdir %LOGDIR%
if not exist %SENTDIR%  mkdir %SENTDIR%

set CKPT_V2C=rl\checkpoints\v2\v2c\jin\jin_final.zip
set CKPT_V2D=rl\checkpoints\v2\v2d\jin\jin_final.zip

if not exist %CKPT_V2C% (echo [ERREUR] %CKPT_V2C% manquant & pause & exit /b 1)
if not exist %CKPT_V2D% (echo [ERREUR] %CKPT_V2D% manquant & pause & exit /b 1)

del /q %SENTDIR%\jin_v2c_*.done %SENTDIR%\jin_v2d_*.done 2>nul

echo ============================================================
echo   EVAL JIN - variantes v2c (anchor opus, claude/mistral...)
echo                       v2d (anchor opus, grok/gemini...)
echo   3 seeds (42,137,999) chacun = 6 evals
echo   Parallelisme : 4 evals simultanes par batch (2 batches)
echo ============================================================
echo.

REM --- Batch 1 : v2c x 3 seeds + v2d seed 42 ---
echo Batch 1/2 : v2c (3 seeds) + v2d (seed 42)
call :spawn v2c 42  %CKPT_V2C%
call :spawn v2c 137 %CKPT_V2C%
call :spawn v2c 999 %CKPT_V2C%
call :spawn v2d 42  %CKPT_V2D%
call :wait_4 v2c 42 v2c 137 v2c 999 v2d 42

REM --- Batch 2 : v2d seed 137 + 999 (seul) ---
echo Batch 2/2 : v2d (seed 137 + 999)
call :spawn v2d 137 %CKPT_V2D%
call :spawn v2d 999 %CKPT_V2D%
call :wait_2 v2d 137 v2d 999

echo ============================================================
echo   EVAL JIN v2c/v2d TERMINE
echo   Resultats dans %OUT%\v2c\ et %OUT%\v2d\
echo.
echo   Comparaison :
echo     python tools\scripts\compare_jin_variants.py
echo ============================================================
pause
exit /b 0


:spawn
REM args: <variante> <seed> <ckpt>
set V=%1
set S=%2
set C=%3
set SAVEDIR=%OUT%\%V%\seed%S%
if not exist %SAVEDIR% mkdir %SAVEDIR%
del /q %SENTDIR%\jin_%V%_seed%S%.done 2>nul
start "Eval_jin_%V%_s%S%" /B cmd /c "%PYTHON% -m rl.eval_agent --agent jin --checkpoint %C% --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --seed %S% --save-dir %SAVEDIR% > %LOGDIR%\jin_%V%_seed%S%.log 2>&1 & echo ok > %SENTDIR%\jin_%V%_seed%S%.done"
exit /b 0


:wait_4
REM args: V1 S1 V2 S2 V3 S3 V4 S4
:wait4loop
timeout /t 30 /nobreak >nul
if not exist %SENTDIR%\jin_%1_seed%2.done goto wait4loop
if not exist %SENTDIR%\jin_%3_seed%4.done goto wait4loop
if not exist %SENTDIR%\jin_%5_seed%6.done goto wait4loop
if not exist %SENTDIR%\jin_%7_seed%8.done goto wait4loop
echo Batch 1 termine.
echo.
exit /b 0


:wait_2
REM args: V1 S1 V2 S2
:wait2loop
timeout /t 30 /nobreak >nul
if not exist %SENTDIR%\jin_%1_seed%2.done goto wait2loop
if not exist %SENTDIR%\jin_%3_seed%4.done goto wait2loop
echo Batch 2 termine.
echo.
exit /b 0
