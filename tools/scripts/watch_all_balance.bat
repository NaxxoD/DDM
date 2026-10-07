@echo off
cd /d "%~dp0..\.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

:loop
cls
echo ============================================================
echo   ALL BALANCE WATCHER  (refresh 30s, Ctrl+C pour quitter)
echo   %DATE% %TIME%
echo ============================================================
echo.
echo --- Process python actifs ---
tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr python.exe
if errorlevel 1 echo   (aucun)
echo.

REM Pour chaque agent, on regarde s'il a un training.csv en cours
for %%A in (jin jio cross) do (
    if exist rl\checkpoints\v1.7\%%A (
        echo --- %%A ---
        %PYTHON% tools\scripts\monitor_finetune.py --save-dir rl/checkpoints/v1.7 --agent %%A --target-steps 500000 --log-dir logs\all_balance 2>&1
        echo.
    )
)

timeout /t 30 /nobreak >nul
goto loop
