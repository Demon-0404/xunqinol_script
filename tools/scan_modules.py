# -*- coding: utf-8 -*-
"""Scan ALL game modules, especially ARM .so through houdini"""
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

JS = """
var modules = Process.enumerateModules();
var gameMods = [];

modules.forEach(function(m) {
    var path = m.path;
    // Game-related modules
    if (path.indexOf('proj.xqj') >= 0 ||
        path.indexOf('xqj') >= 0 ||
        path.indexOf('testcpp') >= 0 ||
        path.indexOf('il2cpp') >= 0 ||
        path.indexOf('unity') >= 0 ||
        path.indexOf('houdini') >= 0 ||
        path.indexOf('armeabi') >= 0 ||
        path.indexOf('arm64') >= 0) {
        gameMods.push(m);
    }
});

// Also find largest modules that aren't system libs
var allMods = modules.slice().sort(function(a, b) { return b.size - a.size; });

send({t: 'matched', list: gameMods.map(function(m) {
    return m.name + " | " + m.base + " | " + (m.size/1024).toFixed(0) + "KB | " + m.path;
})});

send({t: 'top20', list: allMods.slice(0, 25).map(function(m) {
    return m.name + " | " + m.base + " | " + (m.size/1024).toFixed(0) + "KB | " + m.path;
})});

// Also list modules from the app's install directory
var appPath = '/data/app/';
modules.forEach(function(m) {
    if (m.path.indexOf(appPath) >= 0) {
        send({t: 'appmod', name: m.name, base: m.base, size: m.size, path: m.path});
    }
});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'matched':
        print(f"\n=== Game-matched modules ({len(payload['list'])}) ===")
        for l in payload['list']:
            print(f"  {l}")
    elif ptype == 'top20':
        print(f"\n=== Largest 25 modules ===")
        for l in payload['list']:
            print(f"  {l}")
    elif ptype == 'appmod':
        print(f"  APP: {payload['name']} | {payload['base']} | {payload['size']/1024:.0f}KB")
        print(f"       {payload['path']}")

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
time.sleep(3)
session.detach()
