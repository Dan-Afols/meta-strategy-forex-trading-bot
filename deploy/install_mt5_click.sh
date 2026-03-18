#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Presetting EULA acceptance in registry ==="
# Try to set EULA accepted in registry
wine reg add "HKCU\Software\MetaQuotes Software Corp.\MetaTrader 5" /v EulaAccepted /t REG_DWORD /d 1 /f 2>/dev/null
wine reg add "HKCU\Software\MetaQuotes\MetaTrader 5" /v EulaAccepted /t REG_DWORD /d 1 /f 2>/dev/null
wine reg add "HKCU\Software\MetaQuotes Software Corp.\MetaTrader 5" /v EULA /t REG_DWORD /d 1 /f 2>/dev/null
wine reg add "HKCU\Software\MetaQuotes\MetaTrader 5" /v EULA /t REG_DWORD /d 1 /f 2>/dev/null

echo "=== Running installer with xdotool clicker ==="
# Launch installer
wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!

# Click every button we can find
sleep 8

# Give the window time to appear and try clicking in key locations
for i in $(seq 1 20); do
    WID=$(xdotool search --name '' 2>/dev/null | head -1)
    if [ -n "$WID" ]; then
        # The installer dialog: checkbox at bottom left, Next button at bottom right
        # Try activating the window and tabbing/entering through it
        xdotool windowactivate "$WID" 2>/dev/null
        sleep 0.5
        
        # Click on the EULA checkbox (usually lower-left area)
        # For a 500px wide dialog: checkbox ~20px from left, ~280px from top
        xdotool mousemove --window "$WID" 20 280 2>/dev/null
        xdotool click 1 2>/dev/null
        sleep 0.5
        
        # Click "Next" button (usually lower-right, ~430, 320)
        xdotool mousemove --window "$WID" 430 320 2>/dev/null
        xdotool click 1 2>/dev/null
        sleep 0.5
        
        # Also try keyboard approach
        xdotool key space 2>/dev/null   # Toggle checkbox
        sleep 0.3
        xdotool key Return 2>/dev/null  # Press Next/OK
        sleep 0.3
        xdotool key Tab 2>/dev/null     # Next control
        sleep 0.3
        xdotool key Return 2>/dev/null  # Press it
        sleep 0.3
        
        # Take screenshot
        if [ "$i" -eq 1 ] || [ "$i" -eq 5 ] || [ "$i" -eq 10 ]; then
            import -window root -display :99 "/tmp/mt5_click_${i}.png" 2>/dev/null
            echo "Screenshot $i taken"
        fi
    fi
    
    # Check if terminal appeared
    FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null | grep -v 'mt5terminal64\|mt5setup')
    if [ -n "$FOUND" ]; then
        echo "TERMINAL FOUND: $FOUND"
        break
    fi
    
    DU=$(du -sh "/home/trader/.wine/drive_c" 2>/dev/null | cut -f1)
    echo "Click pass $i: disk=$DU"
    sleep 2
done

echo "=== Final check ==="
find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null
find /home/trader/.wine/drive_c -name '*.exe' -newer /tmp/mt5setup.exe -not -name mt5terminal64.exe 2>/dev/null | head -10
echo "=== COMPLETE ==="

kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
