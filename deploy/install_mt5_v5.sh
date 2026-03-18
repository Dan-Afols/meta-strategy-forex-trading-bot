#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Clean slate
wineserver -k 2>/dev/null
killall Xvfb 2>/dev/null
sleep 3

# Start Xvfb
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Trying Wine virtual desktop mode ==="
# Wine virtual desktop forces proper rendering
wine explorer /desktop=MT5,1024x768 /tmp/mt5setup.exe /auto 2>/dev/null &
WPID=$!

# Monitor installation
for i in $(seq 1 40); do
    sleep 5
    FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null)
    if [ -n "$FOUND" ]; then
        echo "SUCCESS! Found: $FOUND"
        break
    fi
    
    MT5DIR="/home/trader/.wine/drive_c/Program Files/MetaTrader 5"
    DU=$(du -sh "$MT5DIR" 2>/dev/null | cut -f1)
    FC=$(find "$MT5DIR" -type f 2>/dev/null | wc -l)
    
    # Also check AppData (non-portable installs go here)
    APPDATA_MT5=$(find /home/trader/.wine/drive_c/users -type d -iname '*metatrader*' 2>/dev/null | head -1)
    APPDATA_DU=""
    if [ -n "$APPDATA_MT5" ]; then
        APPDATA_DU=$(du -sh "$APPDATA_MT5" 2>/dev/null | cut -f1)
    fi
    
    echo "Check $i/40: PF_size=$DU PF_files=$FC AppData=$APPDATA_DU"

    # If wine process died, try xdotool to click through
    if ! ps aux | grep -q '[m]t5setup'; then
        echo "MT5 process died, restarting..."
        wine explorer /desktop=MT5,1024x768 /tmp/mt5setup.exe /auto 2>/dev/null &
        WPID=$!
        sleep 5
    fi
done

echo "=== Final Results ==="
echo "--- terminal64.exe search ---"
find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null
echo "--- All new files in Program Files ---"
find "/home/trader/.wine/drive_c/Program Files/MetaTrader 5/" -type f 2>/dev/null | head -30
echo "--- AppData MetaTrader files ---"
find /home/trader/.wine/drive_c/users -ipath '*metatrader*' -type f 2>/dev/null | head -30
echo "=== DONE ==="

kill $WPID 2>/dev/null
killall Xvfb 2>/dev/null
wineserver -k 2>/dev/null
