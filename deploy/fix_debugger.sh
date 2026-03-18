#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Start display
killall Xvfb wineserver 2>/dev/null
sleep 2
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Disabling debugger detection ==="

# Method 1: Set explorer.exe as the shell (avoids winedbg)
wine reg add "HKCU\Software\Wine\WineDbg" /v ShowCrashDialog /t REG_DWORD /d 0 /f 2>/dev/null

# Method 2: Override winedbg
wine reg add "HKCU\Software\Wine\DllOverrides" /v "winedbg.exe" /t REG_SZ /d "" /f 2>/dev/null
wine reg add "HKCU\Software\Wine\DllOverrides" /v "dbghelp" /t REG_SZ /d "" /f 2>/dev/null
wine reg add "HKCU\Software\Wine\DllOverrides" /v "dbgeng" /t REG_SZ /d "" /f 2>/dev/null

# Method 3: Set NtCurrentProcess check override
wine reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion\AeDebug" /v "Debugger" /t REG_SZ /d "" /f 2>/dev/null
wine reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion\AeDebug" /v "Auto" /t REG_SZ /d "0" /f 2>/dev/null

# Method 4: Hide Wine from being detected as debugger
wine reg add "HKCU\Software\Wine" /v "HideWineExports" /t REG_DWORD /d 1 /f 2>/dev/null

echo "Registry updated"

echo "=== Running MT5 setup ==="
wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 10

# Take screenshot
import -window root /tmp/no_debug_screen.png 2>/dev/null
convert /tmp/no_debug_screen.png -trim /tmp/no_debug_dialog.png 2>/dev/null
TRIM=$(convert /tmp/no_debug_screen.png -trim -format '%wx%h+%X+%Y' info: 2>/dev/null)
echo "Dialog: $TRIM"
tesseract /tmp/no_debug_dialog.png - 2>/dev/null

echo "=== DONE ==="
kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
