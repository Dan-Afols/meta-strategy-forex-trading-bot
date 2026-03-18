#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export DISPLAY=:99

# Kill old
killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 2

MT5="/home/trader/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"
echo "Running MT5 terminal with full debug..."
timeout 15 wine "$MT5" /portable 2>&1 | head -20

echo "=== ERRORS SHOWN ABOVE ==="
killall Xvfb wineserver 2>/dev/null
