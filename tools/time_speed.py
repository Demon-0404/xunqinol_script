# -*- coding: utf-8 -*-
"""Time acceleration hack: hook clock_gettime to speed up game"""
import sys, time, subprocess, ctypes

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"

SPEED_MULT = 3.0  # 3x speed - adjust as needed

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
print("Attached!", flush=True)

JS = f"""
var SPEED = {SPEED_MULT};
var baseTime = null;
var baseClock = null;

// Hook clock_gettime - primary time source on Linux
var libc = Process.getModuleByName("libc.so");
var clock_gettime = libc.getExportByName("clock_gettime");

if (clock_gettime) {{
    var clock_gettime_orig = new NativeFunction(clock_gettime, 'int', ['int', 'pointer']);

    Interceptor.replace(clock_gettime, new NativeCallback(function(clk_id, tp) {{
        var ret = clock_gettime_orig(clk_id, tp);
        if (ret === 0 && tp && !isNaN(tp.readU64())) {{
            // CLOCK_MONOTONIC=1, CLOCK_REALTIME=0
            var sec = tp.readU64();
            var nsec = tp.add(8).readU64();

            if (baseTime === null) {{
                baseTime = sec * 1000000000 + nsec;
            }}

            var elapsed = (sec * 1000000000 + nsec) - baseTime;
            var fakeElapsed = elapsed * SPEED;
            var fakeTotal = baseTime + fakeElapsed;

            tp.writeU64(Math.floor(fakeTotal / 1000000000));
            tp.add(8).writeU64(fakeTotal % 1000000000);
        }}
        return ret;
    }}, 'int', ['int', 'pointer']));

    send({{t: 'hooked', func: 'clock_gettime'}});
}} else {{
    send({{t: 'err', msg: 'clock_gettime not found'}});
}}

// Hook gettimeofday as fallback
var gettimeofday = libc.getExportByName("gettimeofday");
if (gettimeofday) {{
    var gettimeofday_orig = new NativeFunction(gettimeofday, 'int', ['pointer', 'pointer']);

    Interceptor.replace(gettimeofday, new NativeCallback(function(tv, tz) {{
        var ret = gettimeofday_orig(tv, tz);
        if (ret === 0 && tv && !isNaN(tv.readU64())) {{
            var sec = tv.readU64();
            var usec = tv.add(8).readU64();

            if (baseTime === null) {{
                baseTime = sec * 1000000 + usec;
            }}

            var elapsed = (sec * 1000000 + usec) - baseTime;
            var fakeElapsed = elapsed * SPEED;
            var fakeTotal = baseTime + fakeElapsed;

            tv.writeU64(Math.floor(fakeTotal / 1000000));
            tv.add(8).writeU64(fakeTotal % 1000000);
        }}
        return ret;
    }}, 'int', ['pointer', 'pointer']));

    send({{t: 'hooked', func: 'gettimeofday'}});
}}

send({{t: 'ready', speed: SPEED}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        # Check for errors
        if msg.get('type') == 'error':
            print(f"[!] Frida error: {msg}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"[*] {payload['speed']}x speed hack active!", flush=True)
        print("[*] 移动角色观察是否加速...", flush=True)
    elif ptype == 'hooked':
        print(f"[+] Hooked {payload['func']}", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['msg']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("\nRunning 30s... (Ctrl+C to stop)", flush=True)
try:
    for i in range(30):
        time.sleep(1)
except KeyboardInterrupt:
    pass

session.detach()
print("\nDone. Game restored to normal speed.", flush=True)
