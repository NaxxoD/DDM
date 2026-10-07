@echo off
cd /d "%~dp0.."
set PYTHON=python
set OUT=reports\rl_combo_eval\zenom_eval.jsonl
echo ZENOM ? Combo Discovery (40 combos x 11 LLMs x 3g = 1320 games)
echo Out : %OUT%
echo.
%PYTHON% tools\scripts\rl_combo_eval.py --agents zenom --games 3 --seed 42 --out %OUT%
echo.
echo Rapport :
%PYTHON% tools\scripts\rl_combo_report.py %OUT%
pause
