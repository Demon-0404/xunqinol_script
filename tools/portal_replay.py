# -*- coding: utf-8 -*-
"""Capture portal packet, replay with NEW key to avoid anti-cheat"""
import sys, time, subprocess, os, random

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

game_fd = -1
for tcp_file in ["net/tcp", "net/tcp6"]:
    r = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/{tcp_file}"],
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.split("\n"):
        line = line.strip()
        if not line or line.startswith("sl"):
            continue
        parts = line.split()
        if len(parts) >= 10 and parts[3] == "01":
            inode = parts[9]
            if inode != "0":
                r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/ | grep {inode}"],
                                   capture_output=True, text=True, timeout=10)
                for fl in r2.stdout.split("\n"):
                    fp = fl.strip().split()
                    if len(fp) >= 8:
                        try:
                            fd = int(fp[7])
                            if fd > 2:
                                game_fd = fd
                                break
                        except:
                            pass
        if game_fd > 0:
            break
    if game_fd > 0:
        break
print(f"Game fd={game_fd}", flush=True)
if game_fd < 0:
    sys.exit(1)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, 'portal_replay.js'), 'r') as f:
    js_template = f.read()
JS = js_template % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

captured = False
orig_key = 0

def on_msg(msg, data):
    global captured, orig_key
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg.get('description', msg)}", flush=True)
        if 'stack' in msg:
            print(f"[!] {msg['stack']}", flush=True)
        return
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"[*] {payload.get('msg')}", flush=True)
        print("[*] 请: 走过传送门 → 走回来", flush=True)
    elif ptype == 'unusual':
        print(f"  [包] len={payload['len']} | {payload['hex']}", flush=True)
    elif ptype == 'captured':
        orig_key = payload.get('key', 0)
        print(f"[*] 截获传送门包 len={payload['len']} orig_key=0x{orig_key:02x}", flush=True)
        captured = True
    elif ptype == 'replayed':
        print(f"[*] 已重放! new_key=0x{payload['newKey']:02x} ret={payload['ret']}", flush=True)
    elif ptype == 'error':
        print(f"[!] {payload.get('msg', '?')}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("[*] 等待截获传送门包...", flush=True)
for i in range(90):
    if captured:
        break
    time.sleep(1)

if not captured:
    print("[!] 未截获到传送门包", flush=True)
    session.detach()
    sys.exit(1)

print("[*] 请走到别处... 等5秒", flush=True)
time.sleep(5)

# Replay with FRESH random key (different from original)
new_key = (orig_key + random.randint(17, 239)) & 0xFF
if new_key == orig_key:
    new_key = (orig_key + 37) & 0xFF
print(f"[*] 重放! orig_key=0x{orig_key:02x} → new_key=0x{new_key:02x}", flush=True)
result = script.exports.replay(new_key)
print(f"[*] 结果: {result}", flush=True)

print("[*] 观察... 15秒", flush=True)
time.sleep(15)
session.detach()
print("Done.", flush=True)
