@echo off
REM MAYDAY CTF Anti-Cheat Launcher
REM This launches the standalone GUI executable (PyInstaller built)
setlocal

set "SCRIPT_DIR=%~dp0"
set "GUI_EXE=%SCRIPT_DIR%dist\AntiCheatDashboard.exe"
set "ANTICHEAT_EXE=%SCRIPT_DIR%anticheatd\build\bin\Release\anticheatd.exe"

REM Check if PyInstaller executable exists
if exist "%GUI_EXE%" (
    echo Starting MAYDAY CTF Anti-Cheat Dashboard (standalone)...
    start "" "%GUI_EXE%"
    exit /b 0
)

REM Fallback: Launch Python script directly
if exist "%SCRIPT_DIR%tools\anticheat_gui.py" (
    echo Starting MAYDAY CTF Anti-Cheat Dashboard (Python)...
    python "%SCRIPT_DIR%tools\anticheat_gui.py"
    exit /b %errorlevel%
)

echo ERROR: Neither GUI executable nor Python script found
echo Please run: pyinstaller --onefile tools/anticheat_gui.py
pause
