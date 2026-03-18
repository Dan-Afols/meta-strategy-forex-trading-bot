#!/bin/bash
cd /tmp

echo "=== Trying direct MT5 terminal download URLs ==="

# Try various known CDN patterns
URLS=(
    "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5terminal64.exe"
    "https://download.mql5.com/cdn/web/metaquotes.ltd/mt5/mt5terminal64.exe"
    "https://download.mql5.com/cdn/web/13014/mt5/mt5terminal64.exe"
    "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/metatrader5.exe"
)

for url in "${URLS[@]}"; do
    echo "Trying: $url"
    HTTP_CODE=$(curl -sI -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
    echo "  Response: $HTTP_CODE"
    if [ "$HTTP_CODE" = "200" ]; then
        echo "FOUND: $url"
        wget -q "$url" -O /tmp/mt5terminal64.exe
        ls -la /tmp/mt5terminal64.exe
        break
    fi
done

# Also try to find what the installer downloads by checking its network calls
# The installer embeds the broker server ID and downloads from CDN
# MetaQuotes Demo server ID is typically 10010
echo ""
echo "=== Trying MetaQuotes Demo ID patterns ==="
MORE_URLS=(
    "https://download.mql5.com/cdn/web/10010/mt5/mt5terminal64.exe"
    "https://download.mql5.com/cdn/web/16929/mt5/mt5terminal64.exe"
    "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/MetaTrader5.exe"
)

for url in "${MORE_URLS[@]}"; do
    echo "Trying: $url"
    HTTP_CODE=$(curl -sI -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
    echo "  Response: $HTTP_CODE"
done

echo "=== SCAN DONE ==="
