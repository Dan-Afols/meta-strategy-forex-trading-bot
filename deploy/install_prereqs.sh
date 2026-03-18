#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

# Start display
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Downloading Wine Mono ==="
MONO_VER="9.4.0"
MONO_URL="https://dl.winehq.org/wine/wine-mono/${MONO_VER}/wine-mono-${MONO_VER}-x86.msi"
cd /tmp
if [ ! -f wine-mono-${MONO_VER}-x86.msi ]; then
    wget -q "$MONO_URL" -O wine-mono-${MONO_VER}-x86.msi
fi
ls -la wine-mono-${MONO_VER}-x86.msi

echo "=== Installing Wine Mono ==="
wine msiexec /i /tmp/wine-mono-${MONO_VER}-x86.msi /quiet 2>/dev/null
sleep 10
echo "Mono installed"

echo "=== Downloading Wine Gecko ==="
GECKO_VER="2.47.4"
GECKO_URL_AMD64="https://dl.winehq.org/wine/wine-gecko/${GECKO_VER}/wine-gecko-${GECKO_VER}-x86_64.msi"
GECKO_URL_X86="https://dl.winehq.org/wine/wine-gecko/${GECKO_VER}/wine-gecko-${GECKO_VER}-x86.msi"

if [ ! -f wine-gecko-${GECKO_VER}-x86_64.msi ]; then
    wget -q "$GECKO_URL_AMD64" -O wine-gecko-${GECKO_VER}-x86_64.msi
fi
if [ ! -f wine-gecko-${GECKO_VER}-x86.msi ]; then
    wget -q "$GECKO_URL_X86" -O wine-gecko-${GECKO_VER}-x86.msi
fi

echo "=== Installing Wine Gecko (amd64) ==="
wine msiexec /i /tmp/wine-gecko-${GECKO_VER}-x86_64.msi /quiet 2>/dev/null
sleep 10,

echo "=== Installing Wine Gecko (x86) ==="
wine msiexec /i /tmp/wine-gecko-${GECKO_VER}-x86.msi /quiet 2>/dev/null
sleep 10

echo "=== Reinitializing Wine prefix ==="
rm -rf /home/trader/.wine
wineboot --init 2>/dev/null
sleep 15
echo "Wine reinitialized with Mono and Gecko"

echo "=== Now running MT5 setup ==="
wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 10

# Take screenshot to see what dialog appears now
import -window root /tmp/after_mono_screen.png 2>/dev/null
convert /tmp/after_mono_screen.png -trim info: 2>/dev/null

# Try OCR
CROP_INFO=$(convert /tmp/after_mono_screen.png -trim -format '%wx%h+%X+%Y' info: 2>/dev/null)
echo "Cropping: $CROP_INFO"
convert /tmp/after_mono_screen.png -trim /tmp/dialog_new.png 2>/dev/null
tesseract /tmp/dialog_new.png - 2>/dev/null

echo "=== PREREQS_DONE ==="
kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
