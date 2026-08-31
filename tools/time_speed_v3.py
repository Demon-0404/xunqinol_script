# -*- coding: utf-8 -*-
"""Speed hack v3: hook ALL time sources aggressively"""
import sys, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
SPEED = 20.0

r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"],
                   capture_output=True, text=True, timeout=15)
pid = None
for line in r.stdout.split("\n"):
    if "proj.xqj" in line:
        parts = line.split()
        if len(parts) >= 2:
            pid = int(parts[1])
            break
print(f"PID={pid}", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var SPEED = {SPEED};
var startTime = null;
var hookedCount = 0;

function makeTimeHook(name, moduleName, exportName) {{
    try {{
        var mod = Process.getModuleByName(moduleName);
        var addr = mod.getExportByName(exportName);
        if (!addr) return false;

        Interceptor.attach(addr, {{
            onLeave: function(ret) {{
                var t = ret.toInt64();
                if (startTime === null) {{
                    startTime = t;
                    return;
                }}
                var elapsed = t.sub(startTime);
                var fake = startTime.add(elapsed.mul(SPEED));
                ret.replace(ptr(fake));
            }}
        }});
        hookedCount++;
        send({{t: 'ok', name: name}});
        return true;
    }} catch(e) {{
        send({{t: 'miss', name: name, err: e.toString()}});
        return false;
    }}
}}

// Android system clocks (libutils.so)
makeTimeHook('elapsedRealtimeNano', 'libutils.so', '_ZN7android19elapsedRealtimeNanoEv');
makeTimeHook('uptimeMillis', 'libutils.so', '_ZN7android12uptimeMillisEv');
makeTimeHook('uptimeNanos', 'libutils.so', '_ZN7android11uptimeNanosEv');
makeTimeHook('elapsedRealtime', 'libutils.so', '_ZN7android15elapsedRealtimeEv');

// C++ chrono clocks (libc++.so)
makeTimeHook('steady_clock::now', 'libc++.so', '_ZNSt3__16chrono12steady_clock3nowEv');
makeTimeHook('system_clock::now', 'libc++.so', '_ZNSt3__16chrono12system_clock3nowEv');

// libc time
makeTimeHook('clock_gettime', 'libc.so', 'clock_gettime');
makeTimeHook('gettimeofday', 'libc.so', 'gettimeofday');

// libbase boot clock
makeTimeHook('boot_clock::now', 'libbase.so', '_ZN7android4base10boot_clock3nowEv');

send({{t: 'done', count: hookedCount, speed: SPEED}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        if msg.get('type') == 'error':
            print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'done':
        print(f"[*] {payload['count']} time functions hooked at {payload['speed']}x", flush=True)
        print("[*] 移动试试...", flush=True)
    elif ptype == 'ok':
        print(f"[+] {payload['name']}", flush=True)
    elif ptype == 'miss':
        print(f"[-] {payload['name']}: {payload.get('err','?')}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Running 30s...", flush=True)
try:
    for i in range(30):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
