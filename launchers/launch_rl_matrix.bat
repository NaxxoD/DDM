@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   RL TOURNAMENT (Group Stage + Playoff Bracket top-4)
REM
REM   Phase 1 — GROUP STAGE :
REM     5 agents (jin/jio/cross/jaeha/neosia) round-robin
REM     10 paires x 2 mirrors x 2 seeds x N games
REM   Phase 2 — PLAYOFF top-4 :
REM     Top 4 du classement → SF (1v4, 2v3) + Finale
REM     5e place eliminé après group stage
REM
REM   Args :
REM     %1 = run_name        (defaut: rl_tournament)
REM     %2 = group games/mirror (defaut: 25 → 1000 games group)
REM     %3 = playoff BO       (defaut: 20 par match → 60 games playoff)
REM     %4 = mode             (defaut: both | matrix | bracket)
REM ============================================================

set RUN_NAME=%~1
if "%RUN_NAME%"=="" set RUN_NAME=rl_tournament

set GAMES=%~2
if "%GAMES%"=="" set GAMES=25

set PLAYOFF_GAMES=%~3
if "%PLAYOFF_GAMES%"=="" set PLAYOFF_GAMES=20

set MODE=%~4
if "%MODE%"=="" set MODE=both

set OUT_DIR=reports\bracket\%RUN_NAME%
set LOG_DIR=logs\bracket\%RUN_NAME%
set OUT_JSONL=%OUT_DIR%\matrix.jsonl
set LOG_FILE=%LOG_DIR%\rl_tournament.log

if not exist %OUT_DIR% mkdir %OUT_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

REM 10 paires x 2 mirrors x 2 seeds x GAMES = GAMES * 40
set /a EXPECTED=%GAMES%*40

if not exist rl\checkpoints\neosia\neosia\neosia_final.zip (
    echo [ERREUR] neosia_final.zip introuvable
    pause
    exit /b 1
)

echo ============================================================
echo   RL TOURNAMENT : %RUN_NAME%
echo   Mode      : %MODE%
echo   Pool      : jin, jio, cross, jaeha, neosia (5 agents)
echo   Group     : 10 paires x 2 mirrors x 2 seeds x %GAMES% games = %EXPECTED% games
echo   Playoff   : Top 4, BO%PLAYOFF_GAMES% par match (SF+F = 3 matchs)
echo   Out       : %OUT_JSONL%
echo   Log       : %LOG_FILE%
echo ============================================================
echo.
echo Demarrage dans 5s... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul

echo Lancement watcher (autre fenetre)...
start "RL Tournament Watcher %RUN_NAME%" cmd /c "tools\scripts\watch_llm_tournament.bat %RUN_NAME% %EXPECTED%"
timeout /t 2 /nobreak >nul

%PYTHON% tools\scripts\rl_tournament.py ^
    --mode %MODE% ^
    --pool jin,jio,cross,jaeha,neosia ^
    --games %GAMES% ^
    --playoff-games %PLAYOFF_GAMES% ^
    --seeds 42,137 ^
    --out %OUT_JSONL% > %LOG_FILE% 2>&1

if errorlevel 1 (
    echo [ERREUR] rl_tournament a echoue. Voir %LOG_FILE%
    pause
    exit /b 1
)

echo.
echo === GENERATION REPORTS ===
%PYTHON% tools\scripts\render_bracket.py --jsonl %OUT_JSONL% --out %OUT_DIR%\report.md

echo.
echo ============================================================
echo   RL TOURNAMENT TERMINE
echo   JSONL    : %OUT_JSONL%
echo   Report   : %OUT_DIR%\report.md
echo ============================================================
pause
