@echo off
cd /d "%~dp0..\.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

set RUN_NAME=%1
if "%RUN_NAME%"=="" (
    for /f "delims=" %%D in ('dir /b /o-d reports\bracket\ 2^>nul') do (
        set RUN_NAME=%%D
        goto :found
    )
    echo Aucun run trouve dans reports\bracket\
    pause & exit /b 1
)
:found
set EXPECTED=%2
if "%EXPECTED%"=="" set EXPECTED=1100

set OUT_DIR=reports\bracket\%RUN_NAME%
set JSONL=%OUT_DIR%\matrix.jsonl
set LOG_DIR=logs\bracket\%RUN_NAME%

:loop
cls
echo ============================================================
echo   LLM TOURNAMENT LIVE - %RUN_NAME%
echo   %DATE% %TIME%   (Ctrl+C pour quitter)
echo ============================================================
echo.

echo --- Process python ---
tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr python.exe
if errorlevel 1 echo   (aucun)
echo.

%PYTHON% tools\scripts\watch_llm_tournament.py %JSONL% %EXPECTED% 2>&1

echo.
echo --- Tail dernier log ---
powershell -nologo -noprofile -command "Get-ChildItem '%LOG_DIR%\*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Write-Host ('[' + $_.BaseName + ']') -ForegroundColor Cyan; Get-Content $_.FullName -Tail 4 }"

echo.
timeout /t 10 /nobreak >nul
goto loop
