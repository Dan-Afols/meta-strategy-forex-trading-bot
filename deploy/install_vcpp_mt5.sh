#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Kill old
killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 2

echo "=== Attempting to set up VC++ runtime manually ==="

# Download VC++ 2015-2022 redistributable
cd /tmp
if [ ! -f vc_redist.x64.exe ]; then
    wget -q "https://aka.ms/vs/17/release/vc_redist.x64.exe" -O vc_redist.x64.exe
    echo "Downloaded VC++ redist"
fi

# Install it
wine /tmp/vc_redist.x64.exe /install /quiet /norestart 2>/dev/null
sleep 30
echo "VC++ install attempted"

# Check for needed DLLs
echo "=== Checking system32 for VC++ DLLs ==="
ls /home/trader/.wine/drive_c/windows/system32/msvcp*.dll 2>/dev/null
ls /home/trader/.wine/drive_c/windows/system32/vcruntime*.dll 2>/dev/null
ls /home/trader/.wine/drive_c/windows/system32/api-ms-win*.dll 2>/dev/null | head -5

# Now try MT5 installer again
echo "=== Trying MT5 installer again ==="
timeout 30 wine /tmp/mt5setup.exe /auto 2>&1 | grep -v 'vulkan'

echo "=== Checking for terminal ==="
find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null
echo "DONE"

killall Xvfb wineserver 2>/dev/null
