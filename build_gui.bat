@echo off
REM MAYDAY CTF Anti-Cheat GUI - Windows Build Script
REM Run this to create a standalone .exe with PyInstaller

setlocal enabledelayedexpansion

echo === MAYDAY CTF Anti-Cheat GUI - Windows Build ===
echo.

cd /d "%~dp0"

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found
    pause
    exit /b 1
)

echo Using Python:
python --version
echo.

REM Create virtual environment if not exists
if not exist ".venv" (
    echo Setting up virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install pyinstaller

REM Check required files
set DEMO_MODE=0
if not exist "anticheatd\build\bin\Release\anticheatd.exe" (
    echo WARNING: anticheatd.exe not found. GUI will run in demo mode.
    set DEMO_MODE=1
) else (
    echo Found anticheatd.exe
)

if not exist "server\atc_full.wav" (
    echo WARNING: atc_full.wav not found.
) else (
    echo Found atc_full.wav
)

REM Build with PyInstaller
echo.
echo Building standalone .exe...
echo.

if !DEMO_MODE! equ 1 (
    pyinstaller --one^file ^
        --name "AntiCheatDashboard" ^
        --windowed ^
        --add-data "server/atc_full.wav;server" ^
        tools\anticheat_gui.py
) else (
    pyinstaller --one^file ^
        --name "AntiCheatDashboard" ^
        --windowed ^
        --add-data "anticheatd\build\bin\Release\anticheatd.exe;anticheatd\build\bin\Release" ^
        --add-data "server\atc_full.wav;server" ^
        tools\anticheat_gui.py
)

echo.
echo Build complete!
echo Binary location: dist\AntiCheatDashboard.exe
echo.
echo To run:
echo   dist\AntiCheatDashboard.exe
echo.

if exist "%TEMP%\PyInstaller\*.log" (
    echo Build logs available in %TEMP%\PyInstaller\
)

pause
