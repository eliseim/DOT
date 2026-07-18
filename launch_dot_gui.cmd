@echo off
setlocal
cd /d "%~dp0"

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
set "SETUP_MARKER=%CD%\.venv\.dot_setup_v3"

if exist "%VENV_PYTHON%" goto ensure_dependencies

echo Creating DOT's private Python environment...
set "PYTHON_BOOTSTRAP="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_BOOTSTRAP=py -3"
)
if defined PYTHON_BOOTSTRAP goto create_environment
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_BOOTSTRAP=python"
)
if defined PYTHON_BOOTSTRAP goto create_environment

echo.
echo Python 3.11 or newer was not found.
echo Install a 64-bit Python from https://www.python.org/downloads/ and run this file again.
pause
exit /b 1

:create_environment
%PYTHON_BOOTSTRAP% -m venv ".venv"
if errorlevel 1 goto setup_failed

:ensure_dependencies
if not exist "%SETUP_MARKER%" goto install_dependencies
"%VENV_PYTHON%" -c "import dot, matplotlib, numpy, pymoo" >nul 2>nul
if errorlevel 1 goto install_dependencies
goto launch

:install_dependencies
echo Installing or updating DOT and all Python packages needed to run it...
"%VENV_PYTHON%" -m ensurepip --upgrade >nul 2>nul
"%VENV_PYTHON%" -m pip install --disable-pip-version-check --upgrade pip setuptools
if errorlevel 1 goto setup_failed

rem Numba is optional at package level for unusual platforms, but the normal
rem launcher installs it so DOT's geometry kernels receive the full speedup.
"%VENV_PYTHON%" -m pip install --disable-pip-version-check -e ".[acceleration]"
if not errorlevel 1 goto mark_setup

echo.
echo Numba acceleration is not available on this Python/hardware combination.
echo Installing portable DOT instead; campaigns will still work, but more slowly.
"%VENV_PYTHON%" -m pip install --disable-pip-version-check -e "."
if errorlevel 1 goto setup_failed

:mark_setup
echo DOT dependency setup v3>"%SETUP_MARKER%"

:launch
"%VENV_PYTHON%" -m dot.gui.target_synthesis_gui
if errorlevel 1 (
    echo.
    echo DOT closed with an error. Review the message above, then run this launcher again.
    pause
)
exit /b %errorlevel%

:setup_failed
echo.
echo DOT could not install its Python packages. Check the internet connection and
echo that Python 3.11 or newer is installed, then run this launcher again.
pause
exit /b 1
