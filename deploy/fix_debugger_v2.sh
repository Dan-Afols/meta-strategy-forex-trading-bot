#!/bin/bash
export WINEPREFIX=/home/trader/.wine
export WINEDEBUG=-all
export DISPLAY=:99

killall Xvfb wineserver 2>/dev/null
sleep 2
Xvfb :99 -screen 0 1280x1024x24 -ac > /dev/null 2>&1 &
sleep 3

echo "=== Creating anti-debug patch DLL ==="

# Create a tiny C source for a DLL that hooks IsDebuggerPresent
cat > /tmp/antidebug.c << 'CEOF'
#include <windows.h>

// Override IsDebuggerPresent to always return FALSE
BOOL WINAPI IsDebuggerPresent_hook(void) {
    return FALSE;
}

// Override NtQueryInformationProcess for ProcessDebugPort
NTSTATUS WINAPI NtQueryInformationProcess_hook(
    HANDLE ProcessHandle,
    int ProcessInformationClass,
    PVOID ProcessInformation,
    ULONG ProcessInformationLength,
    PULONG ReturnLength
) {
    // ProcessDebugPort = 7, ProcessDebugObjectHandle = 30, ProcessDebugFlags = 31
    if (ProcessInformationClass == 7 || ProcessInformationClass == 30 || ProcessInformationClass == 31) {
        if (ProcessInformation && ProcessInformationLength >= sizeof(ULONG_PTR)) {
            *(ULONG_PTR*)ProcessInformation = 0;
        }
        if (ReturnLength) {
            *ReturnLength = sizeof(ULONG_PTR);
        }
        return 0; // STATUS_SUCCESS
    }
    return 1; // Let other queries pass through normally
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    return TRUE;
}
CEOF

echo "Source created"

# Try using native Linux compiler for Windows target
which x86_64-w64-mingw32-gcc >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Installing mingw cross-compiler..."
    sudo apt-get install -y -qq gcc-mingw-w64-x86-64 2>/dev/null
fi

echo "=== Compiling anti-debug DLL ==="
x86_64-w64-mingw32-gcc -shared -o /tmp/antidebug.dll /tmp/antidebug.c -Wl,--export-all-symbols -lntdll 2>&1
ls -la /tmp/antidebug.dll

echo "=== Copying DLL and setting up preload ==="
cp /tmp/antidebug.dll "/home/trader/.wine/drive_c/windows/system32/antidebug.dll"

# Alternative: Use WINE_PRELOADRESERVE and LD_PRELOAD technique won't work for Windows DLLs
# Instead, try setting environment variable to disable ptrace 
echo "=== Trying with WINEESYNC and WINEFSYNC ==="
export WINEESYNC=0
export WINEFSYNC=0  

# Also try setting sysctl to disable ptrace_scope
echo "Current ptrace_scope:"
cat /proc/sys/kernel/yama/ptrace_scope
sudo sysctl -w kernel.yama.ptrace_scope=0 2>/dev/null

echo "=== Running MT5 setup with ptrace disabled ==="
wine /tmp/mt5setup.exe 2>/dev/null &
WPID=$!
sleep 10

import -window root /tmp/ptrace_screen.png 2>/dev/null
convert /tmp/ptrace_screen.png -trim /tmp/ptrace_dialog.png 2>/dev/null
TRIM=$(convert /tmp/ptrace_screen.png -trim -format '%wx%h+%X+%Y' info: 2>/dev/null)
echo "Dialog: $TRIM"
tesseract /tmp/ptrace_dialog.png - 2>/dev/null

echo "=== DONE ==="
kill $WPID 2>/dev/null
killall Xvfb wineserver 2>/dev/null
