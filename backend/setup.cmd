@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 or newer was not found in PATH.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m ensurepip --upgrade
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements-dev.lock
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --no-deps -e .
if errorlevel 1 exit /b 1

echo GoGlobe backend environment is ready.
