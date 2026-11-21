@echo off
rem ======================================================================
rem  Thuis dashboard - dubbelklik om te installeren en te starten.
rem  De eerste keer installeert dit alles (een paar minuten),
rem  daarna start het dashboard binnen een paar seconden.
rem ======================================================================
setlocal
chcp 65001 >nul
title Thuis dashboard
cd /d "%~dp0"

rem De Python-werkmap staat op een kort pad: Windows staat standaard maar 260
rem tekens per bestandspad toe en Streamlit bevat diep geneste mappen.
set "VENV=%LOCALAPPDATA%\ThuisDashboard\venv"
set "VPY=%VENV%\Scripts\python.exe"

echo.
echo   === Thuis dashboard ===
echo.

if not exist "streamlit_app.py" (
    echo   Ik kan streamlit_app.py niet vinden.
    echo   Pak de zip eerst helemaal uit en start dit bestand vanuit die map.
    goto :fail
)

rem ---- 1. Al geinstalleerd? Dan meteen door. ---------------------------
if exist "%VPY%" goto :packages

rem ---- 2. Python zoeken -------------------------------------------------
call :findpython
if defined PY goto :makevenv

echo   Python is niet gevonden. Ik installeer het nu via winget...
echo.
where winget >nul 2>&1
if errorlevel 1 goto :nopython
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :findpython
if not defined PY goto :nopython

:makevenv
echo.
echo   Eenmalige installatie: werkmap voor Python maken...
if not exist "%LOCALAPPDATA%\ThuisDashboard" mkdir "%LOCALAPPDATA%\ThuisDashboard"
%PY% -m venv "%VENV%"
if errorlevel 1 goto :fail

rem ---- 3. Pakketten installeren als dat nog niet (opnieuw) gebeurd is --
:packages
fc /b requirements.txt "%VENV%\requirements.installed" >nul 2>&1
if not errorlevel 1 goto :run
echo.
echo   Pakketten installeren. De eerste keer duurt dit een paar minuten...
"%VPY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :fail
copy /y requirements.txt "%VENV%\requirements.installed" >nul

rem ---- 4. Starten -------------------------------------------------------
:run
echo.
echo   Het dashboard start. Je browser opent zo op http://localhost:8501
echo   Laat dit venster open; sluit het om het dashboard te stoppen.
echo.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 5; Start-Process 'http://localhost:8501'"
"%VPY%" -m streamlit run streamlit_app.py --server.headless true --server.address localhost --server.port 8501 --browser.gatherUsageStats false
if errorlevel 1 goto :fail
goto :eof

rem ---- Hulpfuncties -----------------------------------------------------
:findpython
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (set "PY=py -3" & goto :eof)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (set "PY=python" & goto :eof)
for %%P in ("%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" "%SystemRoot%\py.exe") do (
    if exist %%P (set PY=%%P -3& goto :eof)
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set PY="%%D\python.exe"
)
goto :eof

:nopython
echo.
echo   Python kon niet automatisch worden geinstalleerd.
echo   Download het via https://www.python.org/downloads/
echo   en vink tijdens de installatie "Add Python to PATH" aan.
echo   Dubbelklik daarna opnieuw op start.bat.
start "" https://www.python.org/downloads/

:fail
echo.
echo   Er ging iets mis. Lees de melding hierboven of stuur hem naar Claude.
echo.
pause
exit /b 1
