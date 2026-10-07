@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8
set CHECKPOINT=rl\checkpoints\zenom\zenom\zenom_final.zip
set SAVE_DIR=rl\checkpoints\zenom
set LOG_DIR=logs\zenom_phase1c
set STEPS_PER_STAGE=80000
set ADVANCE_WR=0.65
if not exist %CHECKPOINT% ( echo [ERREUR] zenom_final.zip introuvable. & pause & exit /b 1 )
if not exist %LOG_DIR% mkdir %LOG_DIR%
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%
set LOG=%LOG_DIR%\zenom_phase1c_%TS%.log
echo ZENOM PHASE 1c - Neosia f4-f8 (25 stages manquants)
echo Resume : %CHECKPOINT%
echo Log    : %LOG%
echo.
echo Demarrage dans 5s...
timeout /t 5 /nobreak >nul
start "Zenom Phase1c Monitor" cmd /c "tools\scripts\monitor_finetune.bat --agent zenom --save-dir rl/checkpoints/zenom --target-steps 4000000 --n-stages 25 --log-dir logs/zenom_phase1c"
timeout /t 2 /nobreak >nul
set CMD=%PYTHON% -m rl.train_ppo --agent zenom --curriculum-custom rl:neosia:4:A,rl:neosia:4:B,rl:neosia:4:C,rl:neosia:4:D,rl:neosia:4:E,rl:neosia:5:A,rl:neosia:5:B,rl:neosia:5:C,rl:neosia:5:D,rl:neosia:5:E,rl:neosia:6:A,rl:neosia:6:B,rl:neosia:6:C,rl:neosia:6:D,rl:neosia:6:E,rl:neosia:7:A,rl:neosia:7:B,rl:neosia:7:C,rl:neosia:7:D,rl:neosia:7:E,rl:neosia:8:A,rl:neosia:8:B,rl:neosia:8:C,rl:neosia:8:D,rl:neosia:8:E --balance-sides --advance-mode conditional --advance-wr %ADVANCE_WR% --anchor-steps %STEPS_PER_STAGE% --middle-steps %STEPS_PER_STAGE% --load %CHECKPOINT% --save-dir %SAVE_DIR% --seed 9999
echo Lancement training...
%CMD% > %LOG% 2>&1
if errorlevel 1 ( echo [ERREUR] Voir %LOG% & pause & exit /b 1 )
echo.
echo ZENOM PHASE 1c TERMINEE - Lance launch_zenom_phase2.bat
pause
