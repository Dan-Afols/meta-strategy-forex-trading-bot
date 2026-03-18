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

echo "=== Reinitializing Wine prefix with Staging ==="
rm -rf /home/trader/.wine
wineboot --init 2>/dev/null
sleep 10
wineserver -w 2>/dev/null
sleep 3

echo "=== Installing Wine Mono and Gecko ==="
# Install Mono
if [ -f /tmp/wine-mono-9.4.0-x86.msi ]; then
    wine msiexec /i /tmp/wine-mono-9.4.0-x86.msi /q 2>/dev/null
    sleep 5
    wineserver -w 2>/dev/null
    echo "Mono installed"
fi

# Install Gecko
if [ -f /tmp/wine-gecko-2.47.4-x86_64.msi ]; then
    wine msiexec /i /tmp/wine-gecko-2.47.4-x86_64.msi /q 2>/dev/null
    sleep 5
    wineserver -w 2>/dev/null
    echo "Gecko installed"
fi

echo ""
echo "=== Setting Wine Staging anti-detection options ==="
# Wine Staging has HKCU\Software\Wine\AppDefaults and staging patches
# Key staging options:
wine reg add "HKCU\\Software\\Wine" /v HideWineExports /t REG_DWORD /d 1 /f 2>/dev/null
wine reg add "HKCU\\Software\\Wine\\Direct3D" /v UseGLSL /t REG_SZ /d enabled /f 2>/dev/null

# Disable winedbg completely
wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v winedbg.exe /t REG_SZ /d "" /f 2>/dev/null
wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v dbghelp /t REG_SZ /d "" /f 2>/dev/null
wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v dbgeng /t REG_SZ /d "" /f 2>/dev/null

# Clear AeDebug
wine reg add "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AeDebug" /v Debugger /t REG_SZ /d "" /f 2>/dev/null
wine reg add "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AeDebug" /v Auto /t REG_SZ /d "0" /f 2>/dev/null

# Set Windows version to Windows 10 (some apps check OS version too)
wine reg add "HKCU\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f 2>/dev/null

wineserver -w 2>/dev/null
sleep 2

echo ""
echo "=== Running MT5 setup with Wine Staging ==="
# Use STAGING_SHARED_MEMORY and other staging env vars
export STAGING_SHARED_MEMORY=1
export WINEDLLOVERRIDES="dbghelp=;dbgeng=;winedbg.exe="

wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 15

# Take screenshot and OCR
import -window root /tmp/staging_screen.png 2>/dev/null
convert /tmp/staging_screen.png -trim /tmp/staging_dialog.png 2>/dev/null
TRIM=$(convert /tmp/staging_screen.png -trim -format '%wx%h+%X+%Y' info: 2>/dev/null)
echo "Dialog dimensions: $TRIM"
echo "OCR result:"
tesseract /tmp/staging_dialog.png - 2>/dev/null

# Also check if any MT5 directories were created
echo ""
echo "Checking for MT5 files..."
find /home/trader/.wine/drive_c -name "MetaTrader*" -type d 2>/dev/null
find /home/trader/.wine/drive_c -name "terminal64.exe" 2>/dev/null

echo ""
echo "=== DONE ==="
kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
