#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Start Xvfb
Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
XPID=$!
sleep 3

# Launch installer in background
wine /tmp/mt5setup.exe &
WPID=$!
echo "Installer launched (PID=$WPID), waiting for window..."

# Wait for installer window to appear
WID=""
for i in $(seq 1 30); do
    WID=$(xdotool search --name 'MetaTrader' 2>/dev/null | head -1)
    if [ -n "$WID" ]; then
        echo "Found MetaTrader window: $WID at attempt $i"
        break
    fi
    WID=$(xdotool search --name 'Setup' 2>/dev/null | head -1)
    if [ -n "$WID" ]; then
        echo "Found Setup window: $WID at attempt $i"
        break
    fi
    WID=$(xdotool search --name 'Install' 2>/dev/null | head -1)
    if [ -n "$WID" ]; then
        echo "Found Install window: $WID at attempt $i"
        break
    fi
    # Also check for any Wine window
    ANYWIN=$(xdotool search --class '' 2>/dev/null | head -1)
    if [ -n "$ANYWIN" ]; then
        echo "Found window (class search): $ANYWIN at attempt $i"
        WID=$ANYWIN
        break
    fi
    echo "Waiting for window... attempt $i"
    sleep 2
done

if [ -z "$WID" ]; then
    echo "No window found after 60s, trying blind approach"
    sleep 5
    xdotool key Return
    sleep 3
    xdotool key Return
    sleep 3
    xdotool key Return
else
    echo "Window found, sending keystrokes to accept and install..."
    xdotool windowactivate "$WID" 2>/dev/null
    sleep 1
    # Tab to Next/Accept and press Enter
    xdotool key Tab Tab Return
    sleep 3
    xdotool key Return
    sleep 3
    xdotool key Return
    sleep 3
    xdotool key Return
fi

echo "Waiting 120 seconds for download and install..."
sleep 120

# Check results
echo "=== Checking for terminal executable ==="
find /home/trader/.wine/drive_c -name 'terminal64.exe' -o -name 'terminal.exe' 2>/dev/null
echo "=== Checking for MetaTrader directories ==="
find /home/trader/.wine/drive_c -type d -iname '*metatrader*' -o -type d -iname '*mt5*' 2>/dev/null
echo "=== New exe files ==="
find /home/trader/.wine/drive_c -name '*.exe' -newer /tmp/mt5setup.exe 2>/dev/null | head -20
echo "=== Done ==="

# Cleanup
kill $WPID 2>/dev/null
kill $XPID 2>/dev/null
wineserver -k 2>/dev/null
