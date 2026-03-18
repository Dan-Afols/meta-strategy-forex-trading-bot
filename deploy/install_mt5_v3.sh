#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Kill any leftovers
wineserver -k 2>/dev/null
killall Xvfb 2>/dev/null
sleep 2

# Start Xvfb
Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 3

MT5DIR="/home/trader/.wine/drive_c/Program Files/MetaTrader 5"
mkdir -p "$MT5DIR"

echo "Running installer with /auto flag..."
# Run the installer and redirect to a specific install path
wine /tmp/mt5setup.exe /auto 2>/dev/null &
WPID=$!

# Wait and monitor
for i in $(seq 1 60); do
    sleep 5
    # Check if terminal64.exe appeared anywhere
    FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null)
    if [ -n "$FOUND" ]; then
        echo "FOUND terminal64.exe at: $FOUND"
        break
    fi
    
    # Check disk usage to see if files are being downloaded
    DU=$(du -sh /home/trader/.wine/drive_c/ 2>/dev/null | cut -f1)
    PROCS=$(ps aux | grep -c mt5setup)
    echo "Progress check $i: wine_c size=$DU, mt5 procs=$PROCS"
    
    # If installer process died, break
    if ! kill -0 $WPID 2>/dev/null; then
        echo "Installer process ended at check $i"
        break
    fi
done

echo "=== Final file search ==="
find /home/trader/.wine/drive_c -name 'terminal64.exe' -o -name 'terminal.exe' -o -name 'metaeditor64.exe' 2>/dev/null
echo "=== New directories ==="
find /home/trader/.wine/drive_c -maxdepth 3 -type d -newer /tmp/mt5setup.exe 2>/dev/null
echo "=== DONE ==="

kill $WPID 2>/dev/null
killall Xvfb 2>/dev/null
wineserver -k 2>/dev/null
