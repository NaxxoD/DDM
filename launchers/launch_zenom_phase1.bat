@echo off
cd /d "%~dp0.."
set PYTHON=python
set PYTHONIOENCODING=utf-8

REM ============================================================
REM   ZENOM PHASE 1 - meta-agent training vs full roster
REM   Curriculum : 211 stages
REM     LLM  (11)  : greedy + haiku + gemini + chatgpt + mistral + grok +
REM                  sonnet + opus + deepseek + qwen3 + glm
REM     RL (5x40)  : jin / jio / cross / jaeha / neosia
REM                  chacun sur les 40 combos (8 factions x 5 champions)
REM   Steps/stage : 80k min, 2x safety cap (160k max)
REM   Budget : 80k*211=16.88M (ideal) -> 160k*211=33.76M (pire cas)
REM   Balance sides : OUI
REM   Estimation : ~2 a 4 jours CPU
REM
REM   Prereq : rl\checkpoints\neosia\neosia\neosia_final.zip
REM ============================================================

set SAVE_DIR=rl\checkpoints\zenom
set LOG_DIR=logs\zenom_phase1
set STEPS_PER_STAGE=80000
set ADVANCE_WR=0.65
set TOTAL_STAGES=211
set TOTAL_STEPS=25320000

if not exist %SAVE_DIR% mkdir %SAVE_DIR%
if not exist %LOG_DIR% mkdir %LOG_DIR%

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,8%_%DT:~8,6%
set LOG=%LOG_DIR%\zenom_phase1_%TS%.log

if not exist rl\checkpoints\neosia\neosia\neosia_final.zip (
    echo [WARNING] rl\checkpoints\neosia\neosia\neosia_final.zip introuvable.
    echo           Zenom va planter sur les stages rl:neosia:*:*.
    echo           Lance launch_neosia_phase1.bat avant de continuer.
    echo.
    pause
)

echo ============================================================
echo   ZENOM PHASE 1 - %TOTAL_STAGES% stages (11 LLM + 5 agents x 40 combos)
echo   Mode       : conditional (advance_wr=%ADVANCE_WR%)
echo   Per stage  : %STEPS_PER_STAGE% min, 2x safety cap
echo   Budget     : ~16.88M (ideal) -> ~33.76M (pire cas)
echo   Log        : %LOG%
echo   Estimation : ~2 a 4 jours sur desktop CPU
echo ============================================================
echo.
echo Demarrage dans 5s... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul

start "Zenom Phase1 Monitor" cmd /c "tools\scripts\monitor_finetune.bat --agent zenom --save-dir rl/checkpoints/zenom --target-steps %TOTAL_STEPS% --n-stages %TOTAL_STAGES% --log-dir logs/zenom_phase1"
timeout /t 2 /nobreak >nul

echo Lancement training (logs dans %LOG%)
echo.
%PYTHON% -m rl.train_ppo ^
    --agent zenom ^
    --curriculum ^
    --balance-sides ^
    --advance-mode conditional ^
    --advance-wr %ADVANCE_WR% ^
    --timesteps-per-stage %STEPS_PER_STAGE% ^
    --save-dir %SAVE_DIR% ^
    --seed 9999 > %LOG% 2>&1

if errorlevel 1 (
    echo.
    echo [ERREUR] training a echoue. Voir %LOG%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ZENOM PHASE 1 TERMINE
echo   Output  : %SAVE_DIR%\zenom_final.zip
echo   Log     : %LOG%
echo   Prochaines etapes :
echo     1) Cabler dans engine\ddm_p4_turn.py (_AI_REGISTRY)
echo     2) Ajouter dans rl\ddm_env.py RL_AGENT_CKPT
echo     3) Eval vs full roster via rl\bracket.py
echo ============================================================
pause