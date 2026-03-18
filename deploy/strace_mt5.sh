#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export DISPLAY=:99

killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 2

MT5="/home/trader/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"

echo "=== Using strace to find missing files ==="
timeout 10 strace -f -e trace=openat wine "$MT5" /portable 2>&1 | grep -i 'ENOENT\|No such file' | grep -viE 'fontconfig|font|nls|share|locale|pkcs|themes|gtk|pixbuf|pango|gio|glib|icons|mime|dri|gallium|mesa|vulkan' | tail -30

echo "=== DONE ==="
killall Xvfb wineserver 2>/dev/null
