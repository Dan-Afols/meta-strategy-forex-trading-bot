#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export DISPLAY=:99

# Kill old
killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 2

echo "=== Checking DLL loading ==="
WINEDEBUG=+loaddll timeout 10 wine /tmp/mt5setup.exe /auto 2>&1 | grep -iE 'not found|failed|error|cannot|missing' | head -30

echo "=== Full error output ==="
WINEDEBUG=err+all timeout 10 wine /tmp/mt5setup.exe /auto 2>&1 | head -30

killall Xvfb wineserver 2>/dev/null
echo "DIAG_DONE"
