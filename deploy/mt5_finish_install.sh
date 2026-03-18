#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Checking if installer is still running ==="
ps aux | grep -i mt5 | grep -v grep

echo ""
echo "=== Running MT5 installer again to let it fully complete ==="
wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 8

# Click through any remaining dialogs
for i in $(seq 1 5); do
    WID=$(xdotool search --name '' 2>/dev/null | head -1)
    if [ -n "$WID" ]; then
        xdotool windowactivate "$WID" 2>/dev/null
        sleep 0.5
        xdotool mousemove --window "$WID" 20 280 2>/dev/null
        xdotool click 1 2>/dev/null
        sleep 0.5
        xdotool mousemove --window "$WID" 430 320 2>/dev/null
        xdotool click 1 2>/dev/null
        sleep 0.5
        xdotool key space Return Tab Return 2>/dev/null
    fi
    sleep 2
done

echo "Waiting for installation to complete (downloading files)..."
# Monitor for progress
for i in $(seq 1 60); do
    sleep 5
    MT5DIR="/home/trader/.wine/drive_c/Program Files/MetaTrader 5"
    FC=$(find "$MT5DIR" -type f 2>/dev/null | wc -l)
    DU=$(du -sh "$MT5DIR" 2>/dev/null | cut -f1)
    echo "Progress $i/60: files=$FC size=$DU"
    
    if [ "$FC" -gt 5 ]; then
        echo "Files appearing! Waiting for completion..."
    fi
    
    # Check if process is still running
    if ! ps aux | grep -q '[m]t5setup'; then
        echo "Installer process completed at check $i"
        break
    fi
done

echo ""
echo "=== Final MT5 directory listing ==="
find "/home/trader/.wine/drive_c/Program Files/MetaTrader 5" -type f 2>/dev/null | head -40
echo ""
echo "=== Directory size ==="
du -sh "/home/trader/.wine/drive_c/Program Files/MetaTrader 5" 2>/dev/null
echo "=== DONE ==="

kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
