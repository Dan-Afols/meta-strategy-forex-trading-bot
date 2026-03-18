#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99
export WINEESYNC=0
export WINEFSYNC=0

killall Xvfb wineserver 2>/dev/null
sleep 2
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Attempt 1: Create anti-debug DLL with mingw ==="
cat > /tmp/antidebug.c << 'CEOF'
#include <windows.h>
#include <winternl.h>

BOOL WINAPI IsDebuggerPresent(void) {
    return FALSE;
}

BOOL WINAPI CheckRemoteDebuggerPresent(HANDLE hProcess, PBOOL pbDebuggerPresent) {
    if (pbDebuggerPresent) *pbDebuggerPresent = FALSE;
    return TRUE;
}

void WINAPI OutputDebugStringA(LPCSTR lpOutputString) {
    return;
}

void WINAPI OutputDebugStringW(LPCWSTR lpOutputString) {
    return;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    if (fdwReason == DLL_PROCESS_ATTACH) {
        // Patch PEB->BeingDebugged to 0
        #ifdef _WIN64
        PPEB pPeb = (PPEB)__readgsqword(0x60);
        #else
        PPEB pPeb = (PPEB)__readfsdword(0x30);
        #endif
        if (pPeb) {
            pPeb->BeingDebugged = 0;
            // NtGlobalFlag at offset 0xBC (x64) or 0x68 (x86) - clear debug flags
            #ifdef _WIN64
            *(DWORD*)((PBYTE)pPeb + 0xBC) &= ~0x70;
            #else
            *(DWORD*)((PBYTE)pPeb + 0x68) &= ~0x70;
            #endif
        }
    }
    return TRUE;
}
CEOF

x86_64-w64-mingw32-gcc -shared -o /tmp/kernel32_override.dll /tmp/antidebug.c \
    -Wl,--export-all-symbols 2>&1
ls -la /tmp/kernel32_override.dll 2>&1

if [ -f /tmp/kernel32_override.dll ]; then
    cp /tmp/kernel32_override.dll "$WINEPREFIX/drive_c/windows/system32/"
    echo "DLL copied to system32"
fi

echo ""
echo "=== Attempt 2: Run MT5 with DLL override ==="
# Try running MT5 with various overrides
WINEDLLOVERRIDES="kernel32_override=n,b" wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 12

import -window root /tmp/test_screen2.png 2>/dev/null
convert /tmp/test_screen2.png -trim /tmp/test_dialog2.png 2>/dev/null
echo "OCR result:"
tesseract /tmp/test_dialog2.png - 2>/dev/null
kill $WPID 2>/dev/null
wineserver -k 2>/dev/null
sleep 3

echo ""
echo "=== Attempt 3: Run with wine-staging style env vars ==="
# These env vars are used by some Wine patches to hide Wine identity
export STAGING_WRITECOPY=1
export WINE_HEAP_TAIL_CHECK_SIZE=0
export __GL_THREADED_OPTIMIZATIONS=0

Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 2

# Try running with ntdll override to use builtin which might not report debug
WINEDLLOVERRIDES="dbghelp=;dbgeng=;winedbg.exe=" wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 12

import -window root /tmp/test_screen3.png 2>/dev/null
convert /tmp/test_screen3.png -trim /tmp/test_dialog3.png 2>/dev/null
echo "OCR result attempt 3:"
tesseract /tmp/test_dialog3.png - 2>/dev/null
kill $WPID 2>/dev/null
wineserver -k 2>/dev/null
sleep 3

echo ""
echo "=== Attempt 4: Try running MT5 terminal directly (not setup) ==="
# Check if there's a terminal anywhere from previous attempts
find /home/trader/.wine -name "terminal64.exe" -o -name "terminal.exe" 2>/dev/null
find /home/trader/.wine -name "metatrader*" -type d 2>/dev/null

echo ""
echo "=== Attempt 5: Check Wine version and try wine-staging ==="
wine --version 2>/dev/null

echo "=== DONE ==="
killall Xvfb wineserver 2>/dev/null
