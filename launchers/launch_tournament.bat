@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   TOURNAMENT ??? bracket challengers + bosses sequentiels
REM
REM   Format :
REM     Bracket 4 challengers : jin / jio / cross / neosia
REM       semi1 = jio (1) vs neosia (4)
REM       semi2 = jin (2) vs cross (3)
REM       finale -> CHAMPION
REM     Boss 1 : champion vs greedy
REM     Boss 2 : champion vs jaeha (le king ultime)
REM
REM   Args optionnels :
REM     %1 = run_name (defaut: tournament_<timestamp>)
REM     %2 = games   (defaut: 50)
REM ============================================================

REM Generation du timestamp HORS du if block (sinon expansion %DT% foireuse)
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%

set RUN_NAME=%~1
if "%RUN_NAME%"=="" set RUN_NAME=tournament_%TS%

set GAMES=%~2
if "%GAMES%"=="" set GAMES=50

set OUT_DIR=reports\bracket\%RUN_NAME%
set LOG_DIR=logs\bracket\%RUN_NAME%

if not exist %OUT_DIR% mkdir %OUT_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

REM Reset stats
if exist %OUT_DIR%\bracket.jsonl del /q %OUT_DIR%\bracket.jsonl
if exist %OUT_DIR%\report.md     del /q %OUT_DIR%\report.md

echo ============================================================
echo   TOURNAMENT %RUN_NAME%
echo   Bracket : jio (1) vs neosia (4) ^| jin (2) vs cross (3)
echo   Bosses  : champion -^> greedy -^> jaeha
echo   Games/match : %GAMES%
echo   Out dir : %OUT_DIR%
echo ============================================================
echo.

REM Lance le watcher
echo Lancement du watcher...
start "Tournament Watcher %RUN_NAME%" cmd /c "tools\scripts\watch_bracket.bat %RUN_NAME%"
timeout /t 2 /nobreak >nul

echo === BRACKET PLAYOFF + BOSSES ===
%PYTHON% -m rl.bracket bracket ^
    --seeding jio,jin,cross,neosia ^
    --bosses  greedy,jaeha ^
    --games %GAMES% ^
    --seeds 42,137 ^
    --out-dir %OUT_DIR% > %LOG_DIR%\bracket.log 2>&1

if errorlevel 1 (
    echo [ERREUR] tournament a echoue. Voir %LOG_DIR%\bracket.log
    pause
    exit /b 1
)

echo.
echo === GENERATION DU REPORT ===
%PYTHON% tools\scripts\render_bracket.py --jsonl %OUT_DIR%\bracket.jsonl --out %OUT_DIR%\report.md

echo.
echo Run name : %RUN_NAME%
echo JSONL    : %OUT_DIR%\bracket.jsonl
echo Report   : %OUT_DIR%\report.md
echo.
echo Pour ouvrir le report : type %OUT_DIR%\report.md
pause
