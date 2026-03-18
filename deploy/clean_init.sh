#!/bin/bash
set -e

export WINEPREFIX=/home/trader/.wine
export DISPLAY=:99
export WINEDEBUG=-all

echo "=== Step 1: Start Xvfb ==="
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3
echo "Xvfb running"

echo "=== Step 2: Clean prefix ==="
rm -rf /home/trader/.wine
echo "Old prefix removed"

echo "=== Step 3: Init prefix ==="
DISPLAY=:99 wineboot --init 2>/dev/null
echo "Waiting for wineboot..."
sleep 20
DISPLAY=:99 wineserver -w 2>/dev/null || true
sleep 3
echo "Prefix contents: $(ls /home/trader/.wine/drive_c/ 2>/dev/null)"

echo "=== Step 4: Install Mono ==="
DISPLAY=:99 wine msiexec /i /tmp/wine-mono-9.4.0-x86.msi /q 2>/dev/null || true
sleep 5
DISPLAY=:99 wineserver -w 2>/dev/null || true
echo "Mono installed"

echo "=== Step 5: Install Gecko ==="
DISPLAY=:99 wine msiexec /i /tmp/wine-gecko-2.47.4-x86_64.msi /q 2>/dev/null || true
sleep 5
DISPLAY=:99 wineserver -w 2>/dev/null || true
echo "Gecko installed"

echo "=== Step 6: Test Wine ==="
DISPLAY=:99 wine cmd /c "echo Wine OK" 2>/dev/null
sleep 2

echo "=== Step 7: Set HideWineExports ==="
DISPLAY=:99 wine reg add "HKCU\\Software\\Wine" /v HideWineExports /t REG_DWORD /d 1 /f 2>/dev/null || true
DISPLAY=:99 wineserver -w 2>/dev/null || true
echo "Registry set"

echo "=== Step 8: Run MT5 setup ==="
DISPLAY=:99 wine /tmp/mt5setup.exe 2>/dev/null &
MT5PID=$!
echo "MT5 PID: $MT5PID"
sleep 15

echo "=== Step 9: Screenshot ==="
import -window root /tmp/final_screen.png 2>/dev/null || true
identify /tmp/final_screen.png 2>&1
convert /tmp/final_screen.png -trim /tmp/final_dialog.png 2>/dev/null || true
DIMS=$(convert /tmp/final_screen.png -trim -format '%wx%h' info: 2>/dev/null)
echo "Dialog: $DIMS"
echo "OCR:"
tesseract /tmp/final_dialog.png - 2>/dev/null || echo "(no text)"

echo ""
echo "=== Step 10: Check MT5 files ==="
find /home/trader/.wine/drive_c -maxdepth 3 -name "MetaTrader*" -o -name "terminal*" 2>/dev/null | head -10

kill $MT5PID 2>/dev/null
DISPLAY=:99 wineserver -k 2>/dev/null || true
killall Xvfb 2>/dev/null
echo "=== ALL DONE ==="
