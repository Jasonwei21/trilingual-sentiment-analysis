@echo off
REM ============================================================
REM  Trilingual Sentiment Analysis - Launcher (Windows)
REM  With Python 3    : install deps + start web UI (auto browser)
REM  Without Python   : open the portable HTML (no install, offline)
REM ============================================================
cd /d "%~dp0"

set "PY="
python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
    py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
)

if not defined PY goto :portable

echo [1/2] Checking dependencies...
%PY% -m pip install -r requirements.txt --quiet
if errorlevel 1 goto :portable

echo [2/2] Starting server... the browser will open automatically.
echo       Press Ctrl+C in this window to stop.
%PY% webapp\app.py --open
pause
exit /b 0

:portable
echo [INFO] Python 3 unavailable. Opening the portable version instead.
echo        The portable HTML runs offline with no installation.
for %%f in ("%~dp0*.html") do start "" "%%f"
pause
exit /b 0
