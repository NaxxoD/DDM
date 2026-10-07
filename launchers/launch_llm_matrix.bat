@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   LLM TOURNAMENT (Group Stage + Playoff Bracket)
REM
REM   Phase 1 — GROUP STAGE :
REM     11 profils, 55 paires x 2 mirrors x 2 seeds x N games
REM   Phase 2 — PLAYOFF :
REM     Top 8 du classement → seedés NBA (1v8, 2v7, 3v6, 4v5)
REM     QF → SF → Finale, Best-of-N par match
REM
REM   Args :
REM     %1 = run_name        (defaut: llm_tournament)
REM     %2 = group games/mirror (defaut: 5 → 1100 games total group)
REM     %3 = playoff BO       (defaut: 9 → first à 5 par match)
REM     %4 = mode             (defaut: both | matrix | bracket)
REM ============================================================

set RUN_NAME=%~1
if "%RUN_NAME%"=="" set RUN_NAME=llm_tournament

set GAMES=%~2
if "%GAMES%"=="" set GAMES=5

set PLAYOFF_GAMES=%~3
if "%PLAYOFF_GAMES%"=="" set PLAYOFF_GAMES=9

set MODE=%~4
if "%MODE%"=="" set MODE=both

set OUT_DIR=reports\bracket\%RUN_NAME%
set LOG_DIR=logs\bracket\%RUN_NAME%
set OUT_JSONL=%OUT_DIR%\matrix.jsonl
set LOG_FILE=%LOG_DIR%\llm_tournament.log

if not exist %OUT_DIR% mkdir %OUT_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

REM Calcul games attendus (utilisé par le watcher pour la barre)
REM Group : 55 paires x 2 mirrors x 2 seeds x GAMES = GAMES * 220
set /a EXPECTED=%GAMES%*220

echo ============================================================
echo   LLM TOURNAMENT : %RUN_NAME%
echo   Mode      : %MODE%
echo   Pool      : 11 profils LLM (greedy + 10 LLM scriptes)
echo   Group     : 55 paires x 2 mirrors x 2 seeds x %GAMES% games = %EXPECTED% games
echo   Playoff   : Top 8 NBA-seeded, BO%PLAYOFF_GAMES% par match (QF+SF+F = 7 matchs)
echo   Out       : %OUT_JSONL%
echo   Log       : %LOG_FILE%
echo ============================================================
echo.
echo Demarrage dans 5s... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul

REM Lance le watcher dans une fenetre separee
echo Lancement du watcher (autre fenetre)...
start "LLM Tournament Watcher %RUN_NAME%" cmd /c "tools\scripts\watch_llm_tournament.bat %RUN_NAME% %EXPECTED%"
timeout /t 2 /nobreak >nul

echo Lancement training (logs dans %LOG_FILE%)
echo.
%PYTHON% tools\scripts\llm_matrix.py ^
    --mode %MODE% ^
    --pool greedy,haiku,gemini,chatgpt,mistral,grok,sonnet,opus,deepseek,qwen3,glm ^
    --games %GAMES% ^
    --playoff-games %PLAYOFF_GAMES% ^
    --seeds 42,137 ^
    --out %OUT_JSONL% > %LOG_FILE% 2>&1

if errorlevel 1 (
    echo [ERREUR] llm_tournament a echoue. Voir %LOG_FILE%
    pause
    exit /b 1
)

echo.
echo === GENERATION REPORTS ===
%PYTHON% tools\scripts\render_bracket.py --jsonl %OUT_JSONL% --out %OUT_DIR%\report.md
%PYTHON% tools\scripts\best_combos.py --top 5 --min-games 4 --out %OUT_DIR%\best_combos.md

echo.
echo ============================================================
echo   LLM TOURNAMENT TERMINE
echo   JSONL    : %OUT_JSONL%
echo   Report   : %OUT_DIR%\report.md
echo   Combos   : %OUT_DIR%\best_combos.md
echo   Log full : %LOG_FILE%
echo ============================================================
pause
