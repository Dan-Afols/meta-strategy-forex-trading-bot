#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Kill everything first
wineserver -k 2>/dev/null
killall Xvfb mt5setup.exe 2>/dev/null
sleep 3

# Start Xvfb
Xvfb :99 -screen 0 1024x768x16 -ac > /dev/null 2>&1 &
sleep 3

# The MT5 installer is a stub that downloads the real terminal
# The actual terminal comes from MetaQuotes CDN
# Let's try downloading it directly using the installer's internal URLs

# First, let's try the installer with proper settings
# Set winhttp to native mode so the installer can download
wine reg add "HKCU\Software\Wine\DllOverrides" /v winhttp /t REG_SZ /d native,builtin /f 2>/dev/null
wine reg add "HKCU\Software\Wine\DllOverrides" /v wininet /t REG_SZ /d native,builtin /f 2>/dev/null

echo "Trying installer with portable flag..."
# Try portable mode - should install directly into the target directory
wine /tmp/mt5setup.exe /auto /portable /skip_admin_check 2>/dev/null &
WPID=$!

# Monitor with a shorter timeout
for i in $(seq 1 24); do
    sleep 5
    FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null)
    if [ -n "$FOUND" ]; then
        echo "SUCCESS: $FOUND"
        break
    fi
    DU=$(du -sh "/home/trader/.wine/drive_c/Program Files/MetaTrader 5/" 2>/dev/null | cut -f1)
    FC=$(find "/home/trader/.wine/drive_c/Program Files/MetaTrader 5/" -type f 2>/dev/null | wc -l)
    echo "Check $i: MT5 dir size=$DU, files=$FC"
done

# If still no terminal, try manual download approach
FOUND=$(find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null)
if [ -z "$FOUND" ]; then
    echo "Installer failed. Trying direct download approach..."
    kill $WPID 2>/dev/null
    wineserver -k 2>/dev/null
    sleep 2
    
    MT5DIR="/home/trader/.wine/drive_c/Program Files/MetaTrader 5"
    
    # Download the MT5 terminal directly from MetaQuotes servers
    # The setup exe contains a compressed version of the terminal
    # We can extract it or try downloading from the CDN
    
    # Try to get portable terminal from the setup exe itself
    # The exe is a self-extracting archive - let's try 7z to extract it
    which 7z >/dev/null 2>&1 || sudo apt-get install -y -qq p7zip-full 2>/dev/null
    
    mkdir -p /tmp/mt5_extract
    cd /tmp/mt5_extract
    7z x -y /tmp/mt5setup.exe 2>/dev/null
    echo "Extracted files:"
    find /tmp/mt5_extract -type f | head -20
    
    # Check if terminal64.exe was extracted
    EXTRACTED=$(find /tmp/mt5_extract -name 'terminal64.exe' 2>/dev/null)
    if [ -n "$EXTRACTED" ]; then
        echo "Found extracted terminal: $EXTRACTED"
        cp -r /tmp/mt5_extract/* "$MT5DIR/"
    else
        echo "No terminal in extracted files"
        # List what we got
        ls -la /tmp/mt5_extract/
    fi
fi

echo "=== Final check ==="
find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null
ls -la "/home/trader/.wine/drive_c/Program Files/MetaTrader 5/" 2>/dev/null
echo "=== COMPLETE ==="

killall Xvfb 2>/dev/null
wineserver -k 2>/dev/null
