@echo off
cd /d "%~dp0..\.."
set LOGDIR=logs\eval_multiseed
set SENTDIR=%LOGDIR%\sentinels

:loop
cls
echo ============================================================
echo   Eval multiseed - %DATE% %TIME%   (Ctrl+C pour quitter)
echo ============================================================
echo.
echo --- Process python actifs ---
tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr python.exe
if errorlevel 1 echo   (aucun)
echo.
echo --- Avancement (sentinelles .done) ---
if exist %SENTDIR% (
    for %%V in (v1 v2) do (
        for %%S in (42 137 999) do (
            set /a OK=0
            if exist %SENTDIR%\%%V_seed%%S_cross.done set /a OK+=1
            if exist %SENTDIR%\%%V_seed%%S_jaeha.done set /a OK+=1
            if exist %SENTDIR%\%%V_seed%%S_jin.done   set /a OK+=1
            if exist %SENTDIR%\%%V_seed%%S_jio.done   set /a OK+=1
            powershell -nologo -noprofile -command "$d = Get-ChildItem '%SENTDIR%\%%V_seed%%S_*.done' -ErrorAction SilentlyContinue; Write-Host ('  %%V seed=%%S : ' + $d.Count + '/4 done')"
        )
    )
) else (
    echo   (sentinelles non trouvees - eval pas demarree ?)
)
echo.
echo --- Logs recents (taille en Mo, top 8) ---
if exist %LOGDIR% (
    powershell -nologo -noprofile -command "Get-ChildItem '%LOGDIR%\*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 8 | ForEach-Object { '{0,7:N1} Mo  {1}' -f ($_.Length / 1MB), $_.Name }"
) else (
    echo   (dossier %LOGDIR% inexistant)
)
echo.
echo --- Tail des 4 logs les plus recents (3 dernieres lignes) ---
powershell -nologo -noprofile -command "$logs = Get-ChildItem '%LOGDIR%\*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 4; foreach ($f in $logs) { Write-Host ''; Write-Host ('[' + $f.BaseName + ']') -ForegroundColor Cyan; Get-Content $f.FullName -Tail 3 }"
echo.
timeout /t 15 /nobreak >nul
goto loop
