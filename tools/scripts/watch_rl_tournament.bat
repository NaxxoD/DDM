@echo off
cd /d "%~dp0..\.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

if "%~1"=="" ( echo Usage: watch_rl_tournament.bat ^<jsonl_path^> [expected] & pause & exit /b 1 )
if exist "%~1" (
    set JSONL=%~f1
) else (
    set JSONL=%CD%\%~1
)
set EXPECTED=%2
if "%EXPECTED%"=="" set EXPECTED=200

:loop
cls
echo ============================================================
echo   RL TOURNAMENT LIVE
echo   %DATE% %TIME%   (Ctrl+C pour quitter)
echo   %JSONL%
echo ============================================================
echo.
%PYTHON% tools\scripts\watch_llm_tournament.py %JSONL% %EXPECTED% 2>&1
echo.
timeout /t 10 /nobreak >nul
goto loop
