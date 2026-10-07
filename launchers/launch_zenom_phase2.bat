@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8
set FIN=rl\checkpoints\zenom\zenom\zenom_final.zip
set FRZ=rl\checkpoints\zenom\zenom\zenom_frozen.zip
set SAVE_DIR=rl\checkpoints\zenom
set LOG_DIR=logs\zenom_phase2
set STEPS=80000
set WR=0.65
if not exist %FIN% ( echo [ERREUR] %FIN% introuvable. & pause & exit /b 1 )
if not exist %LOG_DIR% mkdir %LOG_DIR%
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%
set LOG=%LOG_DIR%\zenom_phase2_%TS%.log
echo Copie frozen...
copy /Y %FIN% %FRZ% >nul
echo Frozen OK : %FRZ%
echo ZENOM PHASE 2 - Self-play 40 stages
echo Log : %LOG%
echo.
echo Demarrage dans 5s...
timeout /t 5 /nobreak >nul
start "Zenom Phase2 Monitor" cmd /c "tools\scripts\monitor_finetune.bat --agent zenom --save-dir rl/checkpoints/zenom --target-steps 6400000 --n-stages 40 --log-dir logs/zenom_phase2"
timeout /t 2 /nobreak >nul
set CMD=%PYTHON% -m rl.train_ppo --agent zenom --curriculum-custom rl:zenom_frozen:1:A,rl:zenom_frozen:1:B,rl:zenom_frozen:1:C,rl:zenom_frozen:1:D,rl:zenom_frozen:1:E,rl:zenom_frozen:2:A,rl:zenom_frozen:2:B,rl:zenom_frozen:2:C,rl:zenom_frozen:2:D,rl:zenom_frozen:2:E,rl:zenom_frozen:3:A,rl:zenom_frozen:3:B,rl:zenom_frozen:3:C,rl:zenom_frozen:3:D,rl:zenom_frozen:3:E,rl:zenom_frozen:4:A,rl:zenom_frozen:4:B,rl:zenom_frozen:4:C,rl:zenom_frozen:4:D,rl:zenom_frozen:4:E,rl:zenom_frozen:5:A,rl:zenom_frozen:5:B,rl:zenom_frozen:5:C,rl:zenom_frozen:5:D,rl:zenom_frozen:5:E,rl:zenom_frozen:6:A,rl:zenom_frozen:6:B,rl:zenom_frozen:6:C,rl:zenom_frozen:6:D,rl:zenom_frozen:6:E,rl:zenom_frozen:7:A,rl:zenom_frozen:7:B,rl:zenom_frozen:7:C,rl:zenom_frozen:7:D,rl:zenom_frozen:7:E,rl:zenom_frozen:8:A,rl:zenom_frozen:8:B,rl:zenom_frozen:8:C,rl:zenom_frozen:8:D,rl:zenom_frozen:8:E --balance-sides --advance-mode conditional --advance-wr %WR% --anchor-steps %STEPS% --middle-steps %STEPS% --load %FIN% --save-dir %SAVE_DIR% --seed 1234
echo Lancement...
%CMD% > %LOG% 2>&1
if errorlevel 1 ( echo [ERREUR] Voir %LOG% & pause & exit /b 1 )
echo ZENOM PHASE 2 TERMINEE
pause
