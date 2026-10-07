@echo off
cd /d "%~dp0..\.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM Args optionnels (passes-through au script python) :
REM   monitor_finetune.bat
REM   monitor_finetune.bat --save-dir rl/checkpoints/v1.7 --target-steps 1000000

:loop
cls
%PYTHON% tools\scripts\monitor_finetune.py %* 2>&1
echo.
echo (refresh dans 30s ??? Ctrl+C pour quitter)
timeout /t 30 /nobreak >nul
goto loop
