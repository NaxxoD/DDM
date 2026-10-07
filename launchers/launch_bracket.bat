@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   LAUNCH_BRACKET.BAT  (version simple, s??quentielle)
REM   Args :
REM     %1 = run_name (defaut: run_<datetime>)
REM     %2 = mode  matrix | bracket | both    (defaut: both)
REM     %3 = games-per-pair                   (defaut: 50)
REM ============================================================

set RUN_NAME=%~1
if "%RUN_NAME%"=="" set RUN_NAME=run_quick

set MODE=%~2
if "%MODE%"=="" set MODE=both

set GAMES=%~3
if "%GAMES%"=="" set GAMES=50

set OUT_DIR=reports\bracket\%RUN_NAME%
set LOG_DIR=logs\bracket\%RUN_NAME%

if not exist %OUT_DIR% mkdir %OUT_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

REM Reset stats (anciennes donnees) pour eviter confusion watcher
if exist %OUT_DIR%\matrix.jsonl  del /q %OUT_DIR%\matrix.jsonl
if exist %OUT_DIR%\bracket.jsonl del /q %OUT_DIR%\bracket.jsonl
if exist %OUT_DIR%\report.md     del /q %OUT_DIR%\report.md

echo ============================================================
echo   BRACKET RUN : %RUN_NAME%
echo   Mode  : %MODE%   Games/pair : %GAMES%
echo   Out   : %OUT_DIR%
echo   Logs  : %LOG_DIR%
echo ============================================================
echo.

if /i "%MODE%"=="matrix"  goto :start_run
if /i "%MODE%"=="bracket" goto :start_run
if /i "%MODE%"=="both"    goto :start_run
echo [ERREUR] Mode inconnu : %MODE%
exit /b 1

:start_run
REM Lance le watcher dans une fenetre separee
echo Lancement du watcher dans une fenetre separee...
start "Bracket Watcher %RUN_NAME%" cmd /c "tools\scripts\watch_bracket.bat %RUN_NAME%"
timeout /t 2 /nobreak >nul

if /i "%MODE%"=="matrix"  goto :run_matrix
if /i "%MODE%"=="bracket" goto :run_bracket
if /i "%MODE%"=="both"    goto :run_both


:run_both
call :run_matrix_inner
call :run_bracket_inner
goto :report

:run_matrix
call :run_matrix_inner
goto :report

:run_bracket
call :run_bracket_inner
goto :report


:run_matrix_inner
echo.
echo === MATRIX (6 pairs x 3 seeds x 2 mirrors x %GAMES% games) ===
%PYTHON% -m rl.bracket matrix --games %GAMES% --seeds 42,137,999 --out-dir %OUT_DIR% > %LOG_DIR%\matrix.log 2>&1
if errorlevel 1 (
    echo [ERREUR] matrix a echoue. Voir %LOG_DIR%\matrix.log
    exit /b 1
)
echo Matrix terminee.
exit /b 0


:run_bracket_inner
echo.
echo === BRACKET PLAYOFF + BOSS ===
%PYTHON% -m rl.bracket bracket --seeding jio,jin,cross,jaeha --games %GAMES% --seeds 42,137 --out-dir %OUT_DIR% > %LOG_DIR%\bracket.log 2>&1
if errorlevel 1 (
    echo [ERREUR] bracket a echoue. Voir %LOG_DIR%\bracket.log
    exit /b 1
)
echo Bracket terminee.
exit /b 0


:report
echo.
echo === GENERATION DU REPORT ===
set ARGS=
if exist %OUT_DIR%\matrix.jsonl  set ARGS=%ARGS% %OUT_DIR%\matrix.jsonl
if exist %OUT_DIR%\bracket.jsonl set ARGS=%ARGS% %OUT_DIR%\bracket.jsonl

%PYTHON% tools\scripts\render_bracket.py --jsonl%ARGS% --out %OUT_DIR%\report.md

echo.
echo Run name      : %RUN_NAME%
echo JSONL matrix  : %OUT_DIR%\matrix.jsonl
echo JSONL bracket : %OUT_DIR%\bracket.jsonl
echo Report        : %OUT_DIR%\report.md
echo.
echo Pour suivre en direct quand ca tourne :
echo   tools\scripts\watch_bracket.bat %RUN_NAME%
exit /b 0
