@echo off
cd /d "%~dp0.."
set PYTHON=python
set CKPT=rl\checkpoints\v2
set EVAL=rl\checkpoints\eval
set LOGDIR=logs\eval_v2
REM Force UTF-8 sur stdout/stderr (sinon crash sur les fl??ches Unicode dans engine/ddm_p4_opus.py)
set PYTHONIOENCODING=utf-8

if not exist %LOGDIR% mkdir %LOGDIR%

REM Timestamp pour suffixer les logs
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%

echo ============================================================
echo   EVAL v2 ??? 4 agents vs opus  (logs redirected)
echo   Logs: %LOGDIR%\{agent}_%TS%.log
echo ============================================================

start "Eval_Jin"   /B cmd /c %PYTHON% -m rl.eval_agent --agent jin   --checkpoint %CKPT%\v2b\jin\jin_final.zip   --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --save-dir %EVAL% ^> %LOGDIR%\jin_%TS%.log 2^>^&1
start "Eval_Jio"   /B cmd /c %PYTHON% -m rl.eval_agent --agent jio   --checkpoint %CKPT%\v2b\jio\jio_final.zip   --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --save-dir %EVAL% ^> %LOGDIR%\jio_%TS%.log 2^>^&1
start "Eval_Cross" /B cmd /c %PYTHON% -m rl.eval_agent --agent cross --checkpoint %CKPT%\v2d\cross\cross_final.zip --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --save-dir %EVAL% ^> %LOGDIR%\cross_%TS%.log 2^>^&1
start "Eval_Jaeha" /B cmd /c %PYTHON% -m rl.eval_agent --agent jaeha --checkpoint rl\checkpoints\v1.5\jaeha\jaeha_final.zip --opponent opus --games-per-combo 10 --confirm-games 50 --top-k 2 --save-dir %EVAL% ^> %LOGDIR%\jaeha_%TS%.log 2^>^&1

echo.
echo 4 evals lancees en parallele (background, logs dans %LOGDIR%).
echo.
echo Pour suivre en direct depuis PowerShell:
echo   Get-Content -Wait %LOGDIR%\jin_%TS%.log
echo.
echo Ou pour voir l'etat des 4 logs:
echo   tools\scripts\watch_eval.bat
echo.
pause
