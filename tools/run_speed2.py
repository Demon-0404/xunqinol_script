# -*- coding: utf-8 -*-
"""Test speed hack using direct memory addresses (bypass libhoudini hiding)."""
import sys, time, os, subprocess, re

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
print(f"[*] PID: {pid}")

# Get current base address from /proc/pid/maps
r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/maps | grep libtestcpp.so | head -1"], capture_output=True, text=True, timeout=10)
line = r2.stdout.strip()
m = re.match(r'^([0-9a-f]+)-[0-9a-f]+', line)
if not m: raise Exception("Cannot find libtestcpp.so base")
base = int(m.group(1), 16)
print(f"[*] libtestcpp.so base: 0x{base:08x}")

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

# Read JS template and inject base address
with open(os.path.join(SCRIPT_DIR, 'speed_direct.js'), 'r', encoding='utf-8') as f:
    JS = f.read()
JS = JS.replace('var base = ptr(0x0c074000);', f'var base = ptr(0x{base:08x});')

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg}", flush=True)
        return
    if not isinstance(payload, dict):
        print(f"[*] {payload}", flush=True)
        return
    ptype = payload.get('t', '?')
    msg_text = payload.get('msg', str(payload))
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
print("[*] Check if game speed changed. Ctrl+C to exit.", flush=True)

try:
    time.sleep(300)
except KeyboardInterrupt:
    pass

session.detach()
print("[*] Done.", flush=True)
