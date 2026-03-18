#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# First kill everything
killall Xvfb wineserver x11vnc websockify 2>/dev/null
sleep 2

# Start Xvfb
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 2

# Remove the old terminal64.exe (it's the setup.exe we wrongly copied)
rm -f "/home/trader/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"

echo "=== Starting VNC on :99 display ==="
x11vnc -display :99 -forever -nopw -listen 0.0.0.0 -rfbport 5900 > /dev/null 2>&1 &
sleep 1

echo "=== Starting noVNC on port 6080 ==="
websockify --web=/usr/share/novnc/ 6080 localhost:5900 > /dev/null 2>&1 &
sleep 1

echo "=== Launching MT5 Setup ==="
wine /tmp/mt5setup.exe 2>/dev/null &

echo ""
echo "============================================="
echo "  noVNC is running!"
echo "  Open in browser: http://132.145.153.13:6080/vnc.html"
echo "  Accept the EULA and install MT5!"
echo "============================================="
echo ""
echo "Monitoring for terminal64.exe..."

# Monitor
for i in $(seq 1 120); do
    sleep 5
    FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null | head -1)
    MT5DIR="/home/trader/.wine/drive_c/Program Files/MetaTrader 5"
    FC=$(find "$MT5DIR" -type f 2>/dev/null | wc -l)
    DU=$(du -sh "$MT5DIR" 2>/dev/null | cut -f1)
    
    if [ -n "$FOUND" ] && [ "$FC" -gt 1 ]; then
        echo "MT5 INSTALLED! Files=$FC Size=$DU"
        echo "Terminal at: $FOUND"
        break
    fi
    
    if [ $((i % 6)) -eq 0 ]; then
        echo "Still waiting... ($i checks, files=$FC, size=$DU)"
    fi
done

echo ""
echo "=== Final check ==="
find "/home/trader/.wine/drive_c/Program Files/MetaTrader 5" -type f 2>/dev/null | head -30
du -sh "/home/trader/.wine/drive_c/Program Files/MetaTrader 5" 2>/dev/null

echo ""
echo "Press Ctrl+C when done. VNC still running on port 6080."
