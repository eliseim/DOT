@echo off
setlocal
cd /d "%~dp0"

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
set "SETUP_MARKER=%CD%\.venv\.dot_setup_v6"

if exist "%VENV_PYTHON%" goto validate_environment

echo Creating DOT's private Python environment...
set "PYTHON_BOOTSTRAP="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import struct,sys; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13)) and struct.calcsize('P')*8==64; raise SystemExit(0 if ok else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_BOOTSTRAP=py -3"
)
if defined PYTHON_BOOTSTRAP goto create_environment
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import struct,sys; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13)) and struct.calcsize('P')*8==64; raise SystemExit(0 if ok else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_BOOTSTRAP=python"
)
if defined PYTHON_BOOTSTRAP goto create_environment

echo.
echo Python was not found, or its version is too old for DOT.
echo Install 64-bit Python 3.11, 3.12, or 3.13 from https://www.python.org/downloads/
echo Keep the standard Tcl/Tk component enabled, then run this file again.
pause
exit /b 1

:create_environment
%PYTHON_BOOTSTRAP% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo.
    echo This Python installation does not include Tkinter/Tcl-Tk, which the DOT GUI requires.
    echo Install 64-bit Python 3.11, 3.12, or 3.13 from python.org with Tcl/Tk enabled.
    pause
    exit /b 1
)
call :approve_packages
if errorlevel 2 goto setup_cancelled
set "DOT_INSTALL_APPROVED=1"
%PYTHON_BOOTSTRAP% -m venv ".venv"
if errorlevel 1 goto setup_failed

:validate_environment
"%VENV_PYTHON%" -c "import struct,sys,tkinter; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13)) and struct.calcsize('P')*8==64; raise SystemExit(0 if ok else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo DOT's existing .venv does not use supported 64-bit Python 3.11, 3.12, or 3.13 with Tcl/Tk.
    echo Rename or remove the .venv folder, install a supported Python, and run this launcher again.
    pause
    exit /b 1
)

:ensure_dependencies
if not exist "%SETUP_MARKER%" goto install_dependencies
"%VENV_PYTHON%" -c "import dot, matplotlib, numpy, pymoo" >nul 2>nul
if errorlevel 1 goto install_dependencies
goto launch

:install_dependencies
if not defined DOT_INSTALL_APPROVED (
    call :approve_packages
    if errorlevel 2 goto setup_cancelled
    set "DOT_INSTALL_APPROVED=1"
)

echo.
echo Installing or updating DOT and its approved Python packages...
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
echo DOT dependency setup v6>"%SETUP_MARKER%"

:launch
"%VENV_PYTHON%" -c "from dot.acceleration import jit_status; print('DOT acceleration: ' + jit_status())"
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
echo that 64-bit Python 3.11, 3.12, or 3.13 is installed, then run this launcher again.
pause
exit /b 1

:setup_cancelled
echo.
echo Package installation was cancelled. DOT was not launched and no listed package was installed.
pause
exit /b 0

:approve_packages
echo.
echo DOT needs permission to install or update these Python packages in its private .venv:
echo.
echo   DOT ^(the local application^)       numpy             matplotlib
echo   pymoo                               numba              llvmlite
echo   scipy                               autograd           cma
echo   alive-progress                      about-time         graphemeu
echo   Deprecated                          wrapt              moocore
echo   cffi                                pycparser          platformdirs
echo   contourpy                           cycler             fonttools
echo   kiwisolver                          packaging          pillow
echo   pyparsing                           python-dateutil     six
echo   pip                                 setuptools
echo.
echo Versions are constrained by pyproject.toml; pip resolves compatible versions.
echo Nothing from this list will be installed unless you approve.
echo.
choice /C YN /N /M "Approve package installation? [Y/N]: "
if errorlevel 2 exit /b 2
exit /b 0
