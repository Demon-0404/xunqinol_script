# -*- coding: utf-8 -*-
"""Load speed hack JS and test game acceleration."""
import sys, time, os, json, subprocess

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

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

with open(os.path.join(SCRIPT_DIR, 'speed_test.js'), 'r', encoding='utf-8') as f:
    JS = f.read()

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg}", flush=True)
        return
    if not isinstance(payload, dict):
        # Plain text message
        print(f"[*] {payload}", flush=True)
        return
    ptype = payload.get('t', '?')
    msg_text = payload.get('msg', '')
    if ptype == 'ready':
        print(f"[*] {msg_text}", flush=True)
    elif ptype == 'log':
        print(f"[*] {msg_text}", flush=True)
    elif ptype == 'err':
        print(f"[!] {msg_text}", flush=True)
    else:
        print(f"[{ptype}] {msg_text}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
time.sleep(2)

try:
    result = script.exports_sync.speed(3.0)
    print(f"[*] speed() -> {result}", flush=True)
except Exception as e:
    print(f"[!] {e}", flush=True)

print("[*] Check if game is faster now. Press Ctrl+C to exit.", flush=True)
try:
    time.sleep(300)
except KeyboardInterrupt:
    pass

session.detach()
print("[*] Done.", flush=True)
