@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up DOT for first use, this may take a minute...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create a virtual environment. Make sure Python 3.11+ is installed and on PATH.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -e ".[dev,optimization,gui]"
    if errorlevel 1 (
        echo Failed to install DOT's dependencies.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m dot.gui.target_synthesis_gui
if errorlevel 1 (
    echo DOT closed with an error. See the message above.
    pause
)
