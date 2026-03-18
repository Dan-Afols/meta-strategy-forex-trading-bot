#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export DISPLAY=:99

# Kill everything
killall Xvfb wineserver 2>/dev/null
sleep 2

# Start Xvfb
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "Wine: $(wine --version 2>/dev/null)"
echo ""

echo "=== Test 1: Run MT5 setup with debug output ==="
export WINEDEBUG=warn+ntdll,err+ntdll
export WINEESYNC=0
export WINEFSYNC=0

timeout 20 wine /tmp/mt5setup.exe 2>&1 | head -50
echo ""
echo "Exit code: $?"

echo ""
echo "=== Test 2: Run MT5 terminal64.exe ==="
timeout 20 wine /tmp/mt5terminal64.exe 2>&1 | head -50
echo ""
echo "Exit code: $?"

echo ""
echo "=== Test 3: Run setup with full logging ==="
export WINEDEBUG=+relay,+seh
timeout 15 wine /tmp/mt5setup.exe 2>&1 | grep -i "debug\|NtQuery\|IsDebug\|STATUS" | head -30
echo ""

echo ""
echo "=== Test 4: Check processes ==="
wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 8
ps aux | grep -i wine | grep -v grep
echo ""

# Capture any windows
xdotool search --name '' 2>/dev/null | head -20
echo ""

import -window root /tmp/debug_screen.png 2>/dev/null
identify /tmp/debug_screen.png 2>&1
convert /tmp/debug_screen.png -trim -format '%wx%h' info: 2>/dev/null
echo ""
# Try full OCR on untrimmed image
tesseract /tmp/debug_screen.png - 2>/dev/null

kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
echo "=== DONE ==="
