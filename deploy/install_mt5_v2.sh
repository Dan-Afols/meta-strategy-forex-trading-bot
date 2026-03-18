#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Kill any existing
wineserver -k 2>/dev/null
sleep 1

# Start Xvfb
Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
XPID=$!
sleep 3

# Launch installer
wine /tmp/mt5setup.exe &
WPID=$!
echo "Installer launched PID=$WPID"

# Wait for window
sleep 10

# Take screenshot
import -window root -display :99 /tmp/mt5_screen1.png 2>/dev/null
echo "Screenshot 1 taken"

# List all windows
xdotool search --onlyvisible --name '' 2>/dev/null
echo "---visible windows above---"

# Try clicking in the middle-bottom area (where Next button usually is)
# MT5 installer window is typically around 500x350
# Next/Accept button is around x=380, y=320
xdotool mousemove 400 300
sleep 1
xdotool click 1
sleep 2

import -window root -display :99 /tmp/mt5_screen2.png 2>/dev/null
echo "Screenshot 2 taken"

sleep 5
xdotool mousemove 400 300
xdotool click 1
sleep 2

import -window root -display :99 /tmp/mt5_screen3.png 2>/dev/null
echo "Screenshot 3 taken"

echo "Waiting 120s for download..."
sleep 120

import -window root -display :99 /tmp/mt5_screen4.png 2>/dev/null
echo "Screenshot 4 taken"

# Check
find /home/trader/.wine/drive_c -name 'terminal64.exe' -o -name 'terminal.exe' 2>/dev/null
find /home/trader/.wine/drive_c -name '*.exe' -newer /tmp/mt5setup.exe 2>/dev/null | head -20
echo "=== CHECK DONE ==="

kill $WPID $XPID 2>/dev/null
wineserver -k 2>/dev/null
