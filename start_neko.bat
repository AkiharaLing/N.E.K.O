@echo off

REM N.E.K.O One-click Startup Script
REM Startup sequence: launcher.py (will automatically start all necessary servers)

echo ====================================
echo N.E.K.O One-click Startup Script
echo ====================================

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python not detected. Please install Python 3.8 or higher first.
    pause
    exit /b 1
)

REM Check if virtual environment exists
if exist ".venv" (
    echo Virtual environment detected, activating...
    call ".venv\Scripts\activate"
    
    REM Check dependencies in virtual environment
    if exist "requirements.txt" (
        echo Checking dependencies...
        python -c "import pkg_resources; pkg_resources.require(open('requirements.txt').read())" >nul 2>&1
        if %errorlevel% neq 0 (
            echo Dependencies not installed, installing...
            pip install -r requirements.txt
            if %errorlevel% neq 0 (
                echo Failed to install dependencies. Please check network connection or Python environment.
                pause
                exit /b 1
            )
        ) else (
            echo Dependencies already installed.
        )
    )
) else (
    echo No virtual environment detected.
    echo ====================================
    echo It is recommended to use a virtual environment to isolate dependencies and avoid conflicts with system Python.
    set /p create_venv="Create virtual environment? (Y/N): "
    
    if /i "%create_venv%"=="Y" (
        echo Creating virtual environment...
        python -m venv .venv
        if %errorlevel% neq 0 (
            echo Failed to create virtual environment.
            pause
            exit /b 1
        )
        echo Virtual environment created successfully, activating...
        call ".venv\Scripts\activate"
        
        REM Install dependencies
        if exist "requirements.txt" (
            echo Installing dependencies...
            pip install -r requirements.txt
            if %errorlevel% neq 0 (
                echo Failed to install dependencies. Please check network connection or Python environment.
                pause
                exit /b 1
            )
            echo Dependencies installed successfully.
        )
    ) else (
        echo Continuing with system Python...
        echo Warning: Using system Python may cause dependency conflicts.
        echo ====================================
    )
)

REM Start N.E.K.O
echo Starting N.E.K.O...
echo Command: python launcher.py
echo ====================================

python launcher.py

REM Capture exit code
if %errorlevel% neq 0 (
    echo N.E.K.O startup failed, error code: %errorlevel%
    pause
    exit /b %errorlevel%
)

pause