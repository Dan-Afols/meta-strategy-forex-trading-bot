#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Kill everything
killall Xvfb wineserver 2>/dev/null
sleep 2

# Start Xvfb
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

# Check if wine prefix exists, if not init it
if [ ! -d "/home/trader/.wine/drive_c" ]; then
    echo "Initializing Wine prefix..."
    wineboot --init 2>/dev/null
    sleep 10
    wineserver -w 2>/dev/null
    sleep 2
    
    # Install Mono
    if [ -f /tmp/wine-mono-9.4.0-x86.msi ]; then
        echo "Installing Mono..."
        wine msiexec /i /tmp/wine-mono-9.4.0-x86.msi /q 2>/dev/null
        sleep 5
        wineserver -w 2>/dev/null
    fi
    
    # Install Gecko
    if [ -f /tmp/wine-gecko-2.47.4-x86_64.msi ]; then
        echo "Installing Gecko..."
        wine msiexec /i /tmp/wine-gecko-2.47.4-x86_64.msi /q 2>/dev/null
        sleep 5
        wineserver -w 2>/dev/null
    fi
    
    # Set registry
    wine reg add "HKCU\\Software\\Wine" /v HideWineExports /t REG_DWORD /d 1 /f 2>/dev/null
    wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v winedbg.exe /t REG_SZ /d "" /f 2>/dev/null
    wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v dbghelp /t REG_SZ /d "" /f 2>/dev/null
    wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v dbgeng /t REG_SZ /d "" /f 2>/dev/null
    wine reg add "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AeDebug" /v Debugger /t REG_SZ /d "" /f 2>/dev/null
    wine reg add "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AeDebug" /v Auto /t REG_SZ /d "0" /f 2>/dev/null
    wineserver -w 2>/dev/null
    echo "Wine prefix initialized with Staging"
else
    echo "Wine prefix already exists"
fi

echo ""
echo "Wine version: $(wine --version 2>/dev/null)"

echo ""
echo "=== Running MT5 setup ==="
export STAGING_SHARED_MEMORY=1
export WINEESYNC=0
export WINEFSYNC=0
export WINEDLLOVERRIDES="dbghelp=;dbgeng=;winedbg.exe="

wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 15

# Screenshot and OCR
import -window root /tmp/stage_screen.png 2>/dev/null
convert /tmp/stage_screen.png -trim /tmp/stage_dialog.png 2>/dev/null
echo "OCR:"
tesseract /tmp/stage_dialog.png - 2>/dev/null

kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
echo "=== DONE ==="
