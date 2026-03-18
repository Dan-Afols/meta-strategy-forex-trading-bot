#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export DISPLAY=:99

killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 2

MT5="/home/trader/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"

# Use Wine's own DLL trace
echo "=== DLL Load trace ==="
WINEDEBUG=+loaddll timeout 10 wine "$MT5" /portable 2>&1 | grep -iE 'Failed|could not|not found' | head -20

echo ""
echo "=== All loaded DLLs ==="
WINEDEBUG=+loaddll timeout 10 wine "$MT5" /portable 2>&1 | grep -i 'Loaded' | tail -20

echo ""
echo "=== Relay for ntdll NtRaiseHardError ==="
WINEDEBUG=+relay timeout 10 wine "$MT5" /portable 2>&1 | grep -i 'NtRaiseHardError' | head -5

echo "=== DONE ==="
killall Xvfb wineserver 2>/dev/null
