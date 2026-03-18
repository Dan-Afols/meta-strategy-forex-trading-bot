#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export DISPLAY=:99
export WINEDEBUG=-all

# Kill everything
killall -u trader Xvfb wineserver wine wineboot rundll32 winedevice 2>/dev/null
sleep 3
killall -9 -u trader wineserver wine wineboot rundll32 winedevice 2>/dev/null
sleep 2

# Start fresh Xvfb
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Removing old Wine prefix ==="
rm -rf /home/trader/.wine

echo "=== Creating clean Wine prefix ==="
# NO DLL overrides during init
wineboot --init 2>/dev/null
sleep 15
wineserver -w 2>/dev/null
sleep 3

echo "Prefix created: $(ls /home/trader/.wine/drive_c/ 2>&1)"

# Install Mono if available
if [ -f /tmp/wine-mono-9.4.0-x86.msi ]; then
    echo "Installing Mono..."
    wine msiexec /i /tmp/wine-mono-9.4.0-x86.msi /q 2>/dev/null
    sleep 5
    wineserver -w 2>/dev/null
    echo "Mono done"
fi

# Install Gecko if available
if [ -f /tmp/wine-gecko-2.47.4-x86_64.msi ]; then
    echo "Installing Gecko..."
    wine msiexec /i /tmp/wine-gecko-2.47.4-x86_64.msi /q 2>/dev/null
    sleep 5
    wineserver -w 2>/dev/null
    echo "Gecko done"
fi

# ONLY set HideWineExports (do NOT mess with DLL overrides)
wine reg add "HKCU\\Software\\Wine" /v HideWineExports /t REG_DWORD /d 1 /f 2>/dev/null
wineserver -w 2>/dev/null
sleep 2

echo ""
echo "=== Testing basic Wine works ==="
wine cmd /c "echo Wine works" 2>/dev/null
echo ""

echo "=== Running MT5 setup (clean, no overrides) ==="
# Run without ANY DLL overrides
wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 15

# Take screenshot
import -window root /tmp/clean_screen.png 2>/dev/null
identify /tmp/clean_screen.png 2>&1
convert /tmp/clean_screen.png -trim /tmp/clean_dialog.png 2>/dev/null
DIMS=$(convert /tmp/clean_screen.png -trim -format '%wx%h' info: 2>/dev/null)
echo "Dialog: $DIMS"
echo "OCR:"
tesseract /tmp/clean_dialog.png - 2>/dev/null

# Check if any MT5 files were created
echo ""
echo "MT5 files:"
find /home/trader/.wine/drive_c -name "MetaTrader*" -o -name "terminal*" -o -name "mt5*" 2>/dev/null | head -10

kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
echo "=== DONE ==="
