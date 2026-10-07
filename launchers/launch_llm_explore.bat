@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   LLM TOURNOI — Phase 3 : 15%% EXPLORATION
REM
REM   Chaque profil joue son combo prefere a 85%%, mais explore une
REM   autre faction random a 15%%. Utile pour tester si les profils
REM   dominants gardent leur WR avec d'autres combos, ou si leur
REM   force vient strictement du combo de predilection.
REM
REM   PRECAUTIONS :
REM   - Lancer apres Phase 1 et Phase 2 si possible
REM   - Verifier que swap_prefs --check rend des values d'interview
REM     avant de lancer (la pref de base est lue 85%% du temps)
REM
REM   Args :
REM     %1 = run_name        (defaut: llm_explore)
REM     %2 = group games/mirror (defaut: 5)
REM ============================================================

set RUN_NAME=%~1
if "%RUN_NAME%"=="" set RUN_NAME=llm_explore

set GAMES=%~2
if "%GAMES%"=="" set GAMES=5

set OUT_DIR=reports\bracket\%RUN_NAME%
set LOG_DIR=logs\bracket\%RUN_NAME%
set OUT_JSONL=%OUT_DIR%\matrix.jsonl
set LOG_FILE=%LOG_DIR%\llm_explore.log

if not exist %OUT_DIR% mkdir %OUT_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

set /a EXPECTED=%GAMES%*220

echo ============================================================
echo   LLM EXPLORATION : %RUN_NAME%
echo   85%% pref interview + 15%% random faction
echo   Group : %EXPECTED% games
echo   Out   : %OUT_JSONL%
echo ============================================================
echo.
echo Demarrage dans 5s... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul

start "LLM Explore Watcher %RUN_NAME%" cmd /c "tools\scripts\watch_llm_tournament.bat %RUN_NAME% %EXPECTED%"
timeout /t 2 /nobreak >nul

%PYTHON% tools\scripts\llm_matrix.py ^
    --mode both ^
    --pool greedy,haiku,gemini,chatgpt,mistral,grok,sonnet,opus,deepseek,qwen3,glm ^
    --games %GAMES% ^
    --playoff-games 9 ^
    --seeds 42,137 ^
    --exploration 0.15 ^
    --out %OUT_JSONL% > %LOG_FILE% 2>&1

if errorlevel 1 (
    echo [ERREUR] explore tournoi a echoue. Voir %LOG_FILE%
    pause & exit /b 1
)

echo.
echo ============================================================
echo   LLM EXPLORATION TERMINE
echo   JSONL : %OUT_JSONL%
echo ============================================================
pause
