# -*- coding: utf-8 -*-
"""Spawn game with Frida to get Java bridge access"""
import sys, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")

print("Spawning proj.xqj...", flush=True)
pid = dev.spawn(["proj.xqj"])
print(f"Spawned PID={pid}", flush=True)

session = dev.attach(pid)
print("Attached!", flush=True)

JS = """
send({t: 'info', msg: 'Checking Java...'});
send({t: 'info', msg: 'typeof Java = ' + typeof Java});

if (typeof Java !== 'undefined') {
    Java.perform(function() {
        send({t: 'info', msg: 'Java bridge OK! Enumerating...'});
        var classes = Java.enumerateLoadedClassesSync();
        send({t: 'info', msg: 'Classes loaded: ' + classes.length});

        // Find position/player classes
        var found = [];
        classes.forEach(function(c) {
            if (c.toLowerCase().indexOf('position') >= 0 ||
                c.toLowerCase().indexOf('player') >= 0 ||
                c.toLowerCase().indexOf('move') >= 0) {
                found.push(c);
            }
        });
        send({t: 'classes', list: found.sort()});

        // Show first 50 classes
        send({t: 'classes', list: classes.slice(0, 50)});
    });
} else {
    send({t: 'err', msg: 'Java NOT available even with spawn!'});
}
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        print(f"RAW: {msg}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'info':
        print(f"[*] {payload['msg']}", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['msg']}", flush=True)
    elif ptype == 'classes':
        print(f"  Classes ({len(payload['list'])}):", flush=True)
        for c in payload['list'][:80]:
            print(f"    {c}", flush=True)
    else:
        print(f"[{ptype}] {payload}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

# Resume the app
dev.resume(pid)
print("App resumed, waiting...", flush=True)
time.sleep(8)
session.detach()
print("Done.", flush=True)
