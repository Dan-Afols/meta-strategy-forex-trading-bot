#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Kill old
killall Xvfb wineserver 2>/dev/null
sleep 2

# Start Xvfb
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

# Set up MT5 directory
MT5DIR="/home/trader/.wine/drive_c/Program Files/MetaTrader 5"
mkdir -p "$MT5DIR"

# Copy the terminal
cp /tmp/mt5terminal64.exe "$MT5DIR/terminal64.exe"
echo "Terminal copied to: $MT5DIR/terminal64.exe"
ls -la "$MT5DIR/terminal64.exe"

# Try running the terminal (it should initialize itself on first run)
echo "=== Starting MT5 terminal ==="
wine "$MT5DIR/terminal64.exe" /portable 2>/dev/null &
WPID=$!
echo "PID=$WPID"

# Wait and check what files get created
for i in $(seq 1 12); do
    sleep 5
    FC=$(find "$MT5DIR" -type f 2>/dev/null | wc -l)
    DU=$(du -sh "$MT5DIR" 2>/dev/null | cut -f1)
    echo "Check $i: files=$FC size=$DU"
done

# Check what was created
echo "=== Files in MT5 directory ==="
find "$MT5DIR" -type f 2>/dev/null | head -30
echo "=== DONE ==="

kill $WPID 2>/dev/null
wineserver -k 2>/dev/null
killall Xvfb 2>/dev/null
