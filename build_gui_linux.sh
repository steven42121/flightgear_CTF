#!/bin/bash
# MAYDAY CTF Anti-Cheat GUI - Linux Build Script
# Run this on Linux to build a standalone binary

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== MAYDAY CTF Anti-Cheat GUI - Linux Build ==="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

PYTHON=$(which python3)
echo "Using Python: $PYTHON"

# Create virtual environment
echo ""
echo "Setting up virtual environment..."
$PYTHON -m venv .venv
source .venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install pyinstaller tkinter

# Check required files
if [ ! -f "anticheatd/build/bin/Release/anticheatd.exe" ]; then
    echo "WARNING: anticheatd.exe not found. GUI will run in demo mode."
    DEMO_MODE=1
else
    DEMO_MODE=0
    echo "Found anticheatd.exe"
fi

if [ ! -f "server/atc_full.wav" ]; then
    echo "WARNING: atc_full.wav not found."
else
    echo "Found atc_full.wav"
fi

# Build with PyInstaller
echo ""
echo "Building standalone binary..."

if [ "$DEMO_MODE" -eq 1 ]; then
    pyinstaller --onefile \
        --name "AntiCheatDashboard" \
        --windowed \
        --add-data "server/atc_full.wav:server" \
        tools/anticheat_gui.py
else
    pyinstaller --onefile \
        --name "AntiCheatDashboard" \
        --windowed \
        --add-data "anticheatd/build/bin/Release/anticheatd.exe:anticheatd/build/bin/Release" \
        --add-data "server/atc_full.wav:server" \
        tools/anticheat_gui.py
fi

echo ""
echo "Build complete!"
echo "Binary location: dist/AntiCheatDashboard"
echo ""
echo "To run:"
echo "  ./dist/AntiCheatDashboard"
