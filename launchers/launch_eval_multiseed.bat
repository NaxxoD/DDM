@echo off
cd /d "%~dp0.."
set PYTHON=python
set OUT=rl\checkpoints\eval_multiseed
set LOGDIR=logs\eval_multiseed
set SENTDIR=%LOGDIR%\sentinels
set PYTHONIOENCODING=utf-8

if not exist %LOGDIR%   mkdir %LOGDIR%
if not exist %SENTDIR%  mkdir %SENTDIR%
if not exist %OUT%      mkdir %OUT%

set V1_CROSS=rl\checkpoints\v1\cross\cross_opus_final.zip
set V1_JAEHA=rl\checkpoints\v1\jaeha\jaeha_chatgpt_final.zip
set V1_JIN=rl\checkpoints\v1\jin\jin_claude_final.zip
set V1_JIO=rl\checkpoints\v1\jio\jio_claude_final.zip

set V2_CROSS=rl\checkpoints\v2\v2d\cross\cross_final.zip
set V2_JAEHA=rl\checkpoints\v1.5\jaeha\jaeha_final.zip
set V2_JIN=rl\checkpoints\v2\v2b\jin\jin_final.zip
set V2_JIO=rl\checkpoints\v2\v2b\jio\jio_final.zip

for %%C in ("%V1_CROSS%" "%V1_JAEHA%" "%V1_JIN%" "%V1_JIO%" "%V2_CROSS%" "%V2_JAEHA%" "%V2_JIN%" "%V2_JIO%") do (
    if not exist %%C (
        echo [ERREUR] Checkpoint manquant : %%C
        pause
        exit /b 1
    )
)

del /q %SENTDIR%\*.done 2>nul

echo ============================================================
echo   EVAL MULTISEED v1 vs v2 - 4 agents x 2 versions x 3 seeds
echo   Seeds       : 42, 137, 999
echo   Total       : 24 evals (~12 000 games)
echo   Parallelism : 4 evals simultanes par batch (6 batches)
echo ============================================================
echo.

call :run_batch 1 v1 42  %V1_CROSS% %V1_JAEHA% %V1_JIN% %V1_JIO%
call :run_batch 2 v1 137 %V1_CROSS% %V1_JAEHA% %V1_JIN% %V1_JIO%
call :run_batch 3 v1 999 %V1_CROSS% %V1_JAEHA% %V1_JIN% %V1_JIO%
call :run_batch 4 v2 42  %V2_CROSS% %V2_JAEHA% %V2_JIN% %V2_JIO%
call :run_batch 5 v2 137 %V2_CROSS% %V2_JAEHA% %V2_JIN% %V2_JIO%
call :run_batch 6 v2 999 %V2_CROSS% %V2_JAEHA% %V2_JIN% %V2_JIO%

echo ============================================================
echo   MULTISEED TERMINE - 24 evals OK
echo   Resultats dans %OUT%\
echo.
echo   Pour comparer :
echo     python tools\scripts\compare_eval_multiseed.py
echo ============================================================
pause
exit /b 0


REM ============================================================
REM Subroutine : run_batch <num> <version> <seed> <ckpt_cross> <ckpt_jaeha> <ckpt_jin> <ckpt_jio>
REM ============================================================
:run_batch
set BNUM=%1
set VER=%2
set SEED=%3
set CKPT_CROSS=%4
set CKPT_JAEHA=%5
set CKPT_JIN=%6
set CKPT_JIO=%7
set SAVEDIR=%OUT%\%VER%\seed%SEED%
if not exist %SAVEDIR% mkdir %SAVEDIR%

echo ============================================================
echo   Batch %BNUM%/6 : %VER% seed=%SEED%  (4 agents en parallele)
echo ============================================================

del /q %SENTDIR%\%VER%_seed%SEED%_*.done 2>nul

start "Eval_%VER%_s%SEED%_cross" /B cmd /c "%PYTHON% -m rl.eval_agent --agent cross --checkpoint %CKPT_CROSS% --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --seed %SEED% --save-dir %SAVEDIR% > %LOGDIR%\%VER%_seed%SEED%_cross.log 2>&1 & echo ok > %SENTDIR%\%VER%_seed%SEED%_cross.done"
start "Eval_%VER%_s%SEED%_jaeha" /B cmd /c "%PYTHON% -m rl.eval_agent --agent jaeha --checkpoint %CKPT_JAEHA% --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --seed %SEED% --save-dir %SAVEDIR% > %LOGDIR%\%VER%_seed%SEED%_jaeha.log 2>&1 & echo ok > %SENTDIR%\%VER%_seed%SEED%_jaeha.done"
start "Eval_%VER%_s%SEED%_jin"   /B cmd /c "%PYTHON% -m rl.eval_agent --agent jin   --checkpoint %CKPT_JIN%   --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --seed %SEED% --save-dir %SAVEDIR% > %LOGDIR%\%VER%_seed%SEED%_jin.log 2>&1 & echo ok > %SENTDIR%\%VER%_seed%SEED%_jin.done"
start "Eval_%VER%_s%SEED%_jio"   /B cmd /c "%PYTHON% -m rl.eval_agent --agent jio   --checkpoint %CKPT_JIO%   --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --seed %SEED% --save-dir %SAVEDIR% > %LOGDIR%\%VER%_seed%SEED%_jio.log 2>&1 & echo ok > %SENTDIR%\%VER%_seed%SEED%_jio.done"

echo Attente fin du batch (verif sentinelles toutes les 30s)...
:wait
timeout /t 30 /nobreak >nul
if not exist %SENTDIR%\%VER%_seed%SEED%_cross.done goto wait
if not exist %SENTDIR%\%VER%_seed%SEED%_jaeha.done goto wait
if not exist %SENTDIR%\%VER%_seed%SEED%_jin.done   goto wait
if not exist %SENTDIR%\%VER%_seed%SEED%_jio.done   goto wait
echo Batch %BNUM% termine.
echo.
exit /b 0
