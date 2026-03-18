#!/bin/bash
for i in $(seq 1 24); do
    sleep 10
    SIZE=$(du -sh /home/trader/.wine/drive_c/ 2>/dev/null | cut -f1)
    FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null | head -1)
    MT5F=$(find "/home/trader/.wine/drive_c/Program Files/MetaTrader 5/" -type f 2>/dev/null | wc -l)
    echo "Check $i: size=$SIZE mt5_files=$MT5F found=$FOUND"
    if [ -n "$FOUND" ]; then
        echo "TERMINAL FOUND!"
        break
    fi
done
echo "MONITOR_DONE"
