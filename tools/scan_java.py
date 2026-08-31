# -*- coding: utf-8 -*-
"""Scan Java classes - with error handling"""
import sys, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"

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

JS = """
// Check if Java is available first
send({t: 'info', msg: 'Checking Java availability...'});

try {
    if (typeof Java === 'undefined') {
        send({t: 'err', msg: 'Java bridge not available - game may not use standard JVM'});
    } else {
        Java.perform(function() {
            send({t: 'info', msg: 'Java bridge active, enumerating classes...'});
            var classes = Java.enumerateLoadedClassesSync();
            send({t: 'info', msg: 'Total loaded classes: ' + classes.length});

            var interesting = [];
            classes.forEach(function(cls) {
                var lower = cls.toLowerCase();
                if (lower.indexOf('socket') >= 0 ||
                    lower.indexOf('send') >= 0 ||
                    lower.indexOf('packet') >= 0 ||
                    lower.indexOf('position') >= 0 ||
                    lower.indexOf('move') >= 0 ||
                    lower.indexOf('walk') >= 0 ||
                    lower.indexOf('encrypt') >= 0 ||
                    lower.indexOf('xtea') >= 0 ||
                    lower.indexOf('tcp') >= 0 ||
                    lower.indexOf('conn') >= 0 ||
                    lower.indexOf('proto') >= 0) {
                    interesting.push(cls);
                }
            });
            interesting.sort();
            send({t: 'classes', list: interesting.slice(0, 200)});

            var gameClasses = [];
            classes.forEach(function(cls) {
                if (cls.indexOf('proj') >= 0 || cls.indexOf('xqj') >= 0 ||
                    cls.startsWith('com.') && cls.length < 40) {
                    gameClasses.push(cls);
                }
            });
            send({t: 'game', list: gameClasses.sort().slice(0, 200)});
        });
    }
} catch(e) {
    send({t: 'err', msg: 'Error: ' + e.toString()});
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
        print(f"\n=== Network-related classes ({len(payload['list'])}) ===")
        for c in payload['list']:
            print(f"  {c}")
    elif ptype == 'game':
        print(f"\n=== Game classes ({len(payload['list'])}) ===")
        for c in payload['list']:
            print(f"  {c}")
    else:
        print(f"[{ptype}] {payload}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting for Java enumeration...", flush=True)
time.sleep(8)
session.detach()
print("Done.", flush=True)
