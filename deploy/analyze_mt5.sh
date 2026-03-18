#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 2

MT5="/home/trader/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"

echo "=== Checking if mt5terminal64.exe is actually the installer ==="
strings "$MT5" 2>/dev/null | grep -i 'setup\|install\|unpack\|extract\|next\|accept' | head -10

echo ""
echo "=== Checking binary magic/header ==="
xxd "$MT5" | head -3

echo ""
echo "=== Checking file size ==="
ls -la "$MT5"

echo ""
echo "=== Checking if it's a self-extracting archive ==="
# Try 7z to extract
7z l "$MT5" 2>/dev/null | grep -E 'terminal|Terminal|\.dll|\.exe' | head -20

echo ""
echo "=== Check the [0] resource from setup ==="
# The [0] file from the mt5setup.exe extraction might actually be the terminal
ls -la /tmp/mt5_extract/\[0\] 2>/dev/null
file /tmp/mt5_extract/\[0\] 2>/dev/null

echo ""
echo "=== Try 7z on [0] ==="
mkdir -p /tmp/mt5_res0
cd /tmp/mt5_res0
7z x -y /tmp/mt5_extract/\[0\] 2>/dev/null | head -10
echo "---"
find /tmp/mt5_res0 -type f -name '*.exe' -o -name '*.dll' 2>/dev/null | head -20
echo "---files found---"
find /tmp/mt5_res0 -type f 2>/dev/null | head -20

echo "=== DONE ==="
killall Xvfb wineserver 2>/dev/null
