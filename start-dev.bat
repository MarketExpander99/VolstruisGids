@echo off
REM start-dev.bat
REM Easy double-click or "start-dev" for Command Prompt / VS Code cmd
REM This avoids all activation and "python" resolution problems.

setlocal

cd /d "%~dp0"

set VENV_PYTHON=.venv\Scripts\python.exe

echo ========================================
echo   VolstruisGids - Development Server
echo ========================================
echo.

if not exist "%VENV_PYTHON%" (
    echo Virtual environment not found. Creating .venv...
    python -m venv .venv
    if not exist "%VENV_PYTHON%" (
        echo ERROR: Could not create .venv. Is Python installed?
        pause
        exit /b 1
    )
)

echo Using: %VENV_PYTHON%
"%VENV_PYTHON%" --version

echo.
echo Checking for required packages...
"%VENV_PYTHON%" -c "import requests; print('requests already present:', requests.__version__)" 2>nul || (
    echo.
    echo Installing dependencies from requirements.txt...
    "%VENV_PYTHON%" -m pip install -r requirements.txt --disable-pip-version-check --prefer-binary
)

echo.
echo Starting dev server...
echo (Press Ctrl+C to stop)
echo.

echo.
echo Starting dev server...
echo (Press Ctrl+C to stop)
echo.

"%VENV_PYTHON%" run.py

pause
