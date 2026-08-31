# -*- coding: utf-8 -*-
"""Explore libhoudini.so internals."""
import sys, time, os, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

subprocess.run([ADB, "-s", SERIAL, "root"], capture_output=True, timeout=10)
r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"], capture_output=True, text=True, timeout=15)
pid = None
for line in r.stdout.split("\n"):
    if "proj.xqj" in line:
        parts = line.split()
        if len(parts) >= 2: pid = int(parts[1]); break
if not pid: raise Exception("Game not found")
print(f"[*] PID: {pid}", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

# Read JS
with open(os.path.join(SCRIPT_DIR, 'houdini_explore.js'), 'r', encoding='utf-8') as f:
    JS = f.read()

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if msg.get('type') == 'error': print(f"[!] {msg}", flush=True); return
    if not isinstance(payload, dict): return
    ptype = payload.get('t', '?')
    msg_text = payload.get('msg', str(payload))
    if ptype == 'ready': print(f"[*] {msg_text}", flush=True)
    elif ptype == 'log': print(f"[*] {msg_text}", flush=True)
    elif ptype == 'err': print(f"[!] {msg_text}", flush=True)
    else: print(f"[{ptype}] {msg_text}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
time.sleep(5)
session.detach()
print("[*] Done.", flush=True)
