@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0..\.." || exit /b 1
echo Preparing the Media Downloader environment in this folder...
if not exist "data\tmp\" mkdir "data\tmp"
if not exist "data\tmp\" exit /b 1
set "TEMP=%CD%\data\tmp"
set "TMP=%TEMP%"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -I -B -m pip --version >nul 2>&1
    if not errorlevel 1 goto install
)

python.exe -I -B -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    python.exe -I -B -m venv --system-site-packages .venv
    if errorlevel 1 exit /b 1
    goto install
)
py.exe -3 -I -B -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 (
    echo Python 3.11 or newer is required. Make python.exe or py.exe available on PATH.
    exit /b 1
)
py.exe -3 -I -B -m venv --system-site-packages .venv
if errorlevel 1 exit /b 1

:install
echo Checking the download and GUI packages...
".venv\Scripts\python.exe" -I -B -m pip --disable-pip-version-check --no-cache-dir --no-input install -r "ui\requirements.txt"
exit /b %ERRORLEVEL%
