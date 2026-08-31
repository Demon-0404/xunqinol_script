# -*- coding: utf-8 -*-
"""Speed hack v2: hook Android system clock in libutils.so"""
import sys, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
SPEED = 5.0  # 5x speed

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

var utils = Process.getModuleByName("libutils.so");

// Hook elapsedRealtimeNano() -> nsecs_t (int64)
// This is the underlying implementation of System.nanoTime()
var elapsedNano = utils.getExportByName("_ZN7android19elapsedRealtimeNanoEv");
if (elapsedNano) {{
    send({{t: 'found', func: 'elapsedRealtimeNano', addr: elapsedNano.toString()}});

    Interceptor.attach(elapsedNano, {{
        onLeave: function(ret) {{
            var original = ret.toInt64();
            if (startTime === null) {{
                startTime = original;
                return;
            }}
            var elapsed = original.sub(startTime);
            var fakeElapsed = elapsed.mul(SPEED);
            var fakeTime = startTime.add(fakeElapsed);
            ret.replace(ptr(fakeTime));
        }}
    }});
}} else {{
    send({{t: 'err', msg: 'elapsedRealtimeNano not found'}});
}}

// Hook uptimeMillis() -> int64
var uptimeMs = utils.getExportByName("_ZN7android12uptimeMillisEv");
if (uptimeMs) {{
    send({{t: 'found', func: 'uptimeMillis', addr: uptimeMs.toString()}});

    Interceptor.attach(uptimeMs, {{
        onLeave: function(ret) {{
            var original = ret.toInt64();
            if (startTime === null) {{
                startTime = original;
                return;
            }}
            var elapsed = original.sub(startTime);
            var fakeElapsed = elapsed.mul(SPEED);
            var fakeTime = startTime.add(fakeElapsed);
            ret.replace(ptr(fakeTime));
        }}
    }});
}}

// Hook uptimeNanos() -> nsecs_t
var uptimeNs = utils.getExportByName("_ZN7android11uptimeNanosEv");
if (uptimeNs) {{
    send({{t: 'found', func: 'uptimeNanos', addr: uptimeNs.toString()}});

    Interceptor.attach(uptimeNs, {{
        onLeave: function(ret) {{
            var original = ret.toInt64();
            if (startTime === null) {{
                startTime = original;
                return;
            }}
            var elapsed = original.sub(startTime);
            var fakeElapsed = elapsed.mul(SPEED);
            var fakeTime = startTime.add(fakeElapsed);
            ret.replace(ptr(fakeTime));
        }}
    }});
}}

send({{t: 'ready', speed: SPEED}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        if msg.get('type') == 'error':
            print(f"[!] {msg}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"[*] {payload['speed']}x speed active!", flush=True)
        print("[*] 点击远处让角色移动，观察是否加速...", flush=True)
    elif ptype == 'found':
        print(f"[+] {payload['func']} @ {payload['addr']}", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['msg']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Running 25s...", flush=True)
try:
    for i in range(25):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
