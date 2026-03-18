#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

killall Xvfb wineserver 2>/dev/null
sleep 2

Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Trying MetaTrader5 Python package auto-install ==="
cd /home/trader/python311

# The MetaTrader5 Python package has a built-in install mechanism
# When mt5.initialize() finds no terminal, it can auto-download one
cat > /tmp/init_mt5.py << 'PYEOF'
import MetaTrader5 as mt5
import os, time

# First try: let it auto-find/install
print("Attempting mt5.initialize()...")
result = mt5.initialize()
if result:
    info = mt5.account_info()
    print(f"SUCCESS! Connected. Account: {info}")
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"Init failed: {err}")
    
    # Try with explicit path
    mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    print(f"Trying with path: {mt5_path}")
    result = mt5.initialize(path=mt5_path)
    if result:
        print("SUCCESS with explicit path!")
        mt5.shutdown()
    else:
        err = mt5.last_error()
        print(f"Failed again: {err}")

    # Check what the package installed
    print("\nChecking installed terminal locations:")
    locations = [
        r"C:\Program Files\MetaTrader 5",
        os.path.expanduser("~") + r"\AppData\Roaming\MetaQuotes\Terminal",
        os.path.expanduser("~") + r"\AppData\Local\MetaQuotes\Terminal",
    ]
    for loc in locations:
        if os.path.exists(loc):
            print(f"  FOUND: {loc}")
            for root, dirs, files in os.walk(loc):
                for f in files:
                    if f.lower().endswith('.exe'):
                        print(f"    {os.path.join(root, f)}")
        else:
            print(f"  NOT FOUND: {loc}")
PYEOF

wine python.exe /tmp/init_mt5.py 2>/dev/null

echo ""
echo "=== Checking for new terminal files ==="
find /home/trader/.wine/drive_c -name 'terminal64.exe' 2>/dev/null
find /home/trader/.wine/drive_c -path '*MetaQuotes*' -name '*.exe' 2>/dev/null | head -10

echo "=== DONE ==="
killall Xvfb wineserver 2>/dev/null
