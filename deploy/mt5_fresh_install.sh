#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Kill everything
killall Xvfb wineserver x11vnc websockify mt5setup.exe 2>/dev/null
sleep 3

# Start Xvfb
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

# Before running installer, let's completely reinitialize wine
echo "=== Reinitializing Wine prefix ==="
rm -rf /home/trader/.wine
wineboot --init 2>/dev/null
sleep 10

echo "Wine reinitialized"
echo "=== Setting Windows 10 ==="
wine reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion" /v CurrentVersion /t REG_SZ /d "10.0" /f 2>/dev/null
wine reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion" /v CurrentBuildNumber /t REG_SZ /d "19041" /f 2>/dev/null
wine reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion" /v ProductName /t REG_SZ /d "Windows 10 Pro" /f 2>/dev/null

echo "=== Running MT5 setup with auto clicks ==="
wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!

# Wait for window to appear
sleep 10

# Aggressive clicking - the installer has a EULA page with checkbox + Next
for click_round in $(seq 1 10); do
    # Get any visible window
    WID=$(xdotool search --onlyvisible --name '' 2>/dev/null | tail -1)
    
    if [ -n "$WID" ]; then
        echo "Round $click_round: Found window $WID"
        xdotool windowactivate "$WID" 2>/dev/null
        sleep 0.5
        
        # Click checkbox area (multiple positions to be sure)
        for y in 250 260 270 280 290 300; do
            for x in 15 20 25 30; do
                xdotool mousemove --window "$WID" $x $y 2>/dev/null
                xdotool click 1 2>/dev/null
                sleep 0.1
            done
        done
        
        sleep 0.5
        
        # Click Next/Accept button area
        for y in 310 315 320 325 330; do
            for x in 400 410 420 430 440 450; do
                xdotool mousemove --window "$WID" $x $y 2>/dev/null
                xdotool click 1 2>/dev/null
                sleep 0.1
            done
        done
        
        sleep 1
    else
        echo "Round $click_round: No window found"
    fi
    
    # Check if terminal appeared
    FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null)
    if [ -n "$FOUND" ]; then
        echo "TERMINAL INSTALLED at: $FOUND"
        break
    fi
    
    sleep 3
done

# Wait for download
if [ -z "$FOUND" ]; then
    echo "Waiting for download..."
    for i in $(seq 1 60); do
        sleep 5
        MT5DIR="/home/trader/.wine/drive_c/Program Files/MetaTrader 5"
        FC=$(find "$MT5DIR" -type f 2>/dev/null | wc -l)
        DU=$(du -sh "$MT5DIR" 2>/dev/null | cut -f1)
        FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null)
        
        if [ -n "$FOUND" ]; then
            echo "TERMINAL INSTALLED! files=$FC size=$DU"
            echo "Location: $FOUND"
            break
        fi
        
        if [ $((i % 12)) -eq 0 ]; then
            echo "Still downloading... files=$FC size=$DU (check $i/60)"
        fi
    done
fi

echo ""
echo "=== Final verification ==="
find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null
find "/home/trader/.wine/drive_c/Program Files" -maxdepth 2 -type d 2>/dev/null
echo ""
echo "=== COMPLETE ==="

kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
