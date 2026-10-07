@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   LLM TOURNOI — Phase 2 : SECOND CHOICE
REM
REM   Bascule prefs vers 2nd choix interview puis lance le tournoi.
REM   En fin de tournoi, restore les prefs vers 1st choice.
REM
REM   Args :
REM     %1 = run_name        (defaut: llm_2nd)
REM     %2 = group games/mirror (defaut: 5)
REM ============================================================

set RUN_NAME=%~1
if "%RUN_NAME%"=="" set RUN_NAME=llm_2nd

set GAMES=%~2
if "%GAMES%"=="" set GAMES=5

set OUT_DIR=reports\bracket\%RUN_NAME%
set LOG_DIR=logs\bracket\%RUN_NAME%
set OUT_JSONL=%OUT_DIR%\matrix.jsonl
set LOG_FILE=%LOG_DIR%\llm_2nd.log

if not exist %OUT_DIR% mkdir %OUT_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

set /a EXPECTED=%GAMES%*220

echo ============================================================
echo   LLM 2ND CHOICE : %RUN_NAME%
echo   Bascule prefs vers 2nd choice interview...
echo ============================================================
%PYTHON% tools\scripts\swap_prefs.py --to second
echo.
echo Demarrage dans 5s... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul

start "LLM 2nd Watcher %RUN_NAME%" cmd /c "tools\scripts\watch_llm_tournament.bat %RUN_NAME% %EXPECTED%"
timeout /t 2 /nobreak >nul

%PYTHON% tools\scripts\llm_matrix.py ^
    --mode both ^
    --pool greedy,haiku,gemini,chatgpt,mistral,grok,sonnet,opus,deepseek,qwen3,glm ^
    --games %GAMES% ^
    --playoff-games 9 ^
    --seeds 42,137 ^
    --out %OUT_JSONL% > %LOG_FILE% 2>&1

set RC=%errorlevel%

REM Toujours restore vers 1st choice (etat de reference)
echo.
echo Restore prefs vers 1st choice...
%PYTHON% tools\scripts\swap_prefs.py --to first

if not "%RC%"=="0" (
    echo [ERREUR] 2nd choice tournoi a echoue (rc=%RC%). Voir %LOG_FILE%
    pause & exit /b 1
)

echo.
echo ============================================================
echo   LLM 2ND CHOICE TERMINE
echo   JSONL : %OUT_JSONL%
echo   Prefs : restored to 1st choice
echo ============================================================
pause
