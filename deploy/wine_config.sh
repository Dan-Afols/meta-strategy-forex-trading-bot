#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Start Xvfb
Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 2

# Set Windows 10 mode
wine reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion" /v CurrentVersion /t REG_SZ /d "10.0" /f 2>/dev/null
wine reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion" /v CurrentBuildNumber /t REG_SZ /d "19041" /f 2>/dev/null
wine reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion" /v ProductName /t REG_SZ /d "Windows 10 Pro" /f 2>/dev/null
echo "Windows version set to 10"

wine --version
echo "---"

# Kill Xvfb
killall Xvfb 2>/dev/null
wineserver -k 2>/dev/null
echo "CONFIG_DONE"
