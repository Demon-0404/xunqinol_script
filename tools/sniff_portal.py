# -*- coding: utf-8 -*-
"""Sniff send+recv to capture full portal transition"""
import sys, time, subprocess, os

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
with open(os.path.join(script_dir, 'sniff_portal.js'), 'r') as f:
    js_template = f.read()
JS = js_template % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

packets = []

def on_msg(msg, data):
    # Handle errors FIRST
    if msg.get('type') == 'error':
        print(f"[!] {msg.get('description', msg)}", flush=True)
        if 'stack' in msg:
            print(f"[!] Stack: {msg['stack']}", flush=True)
        return
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"[*] {payload.get('msg', 'ready')}", flush=True)
    elif ptype in ('SEND', 'RECV'):
        direction = '>>>' if ptype == 'SEND' else '<<<'
        print(f"[#{payload['n']}] {direction} dt={payload['dt']}ms len={payload['len']} | {payload['hex']}", flush=True)
        packets.append(payload)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("[*] 走过传送门后等待10秒...", flush=True)
try:
    for i in range(90):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()

log_path = os.path.join(script_dir, '..', 'logs', 'sniff_portal.txt')
os.makedirs(os.path.dirname(log_path), exist_ok=True)
with open(log_path, 'w') as f:
    for p in packets:
        direction = '>>>' if p['t'] == 'SEND' else '<<<'
        f.write(f"[#{p['n']}] {direction} dt={p['dt']}ms len={p['len']} | {p['hex']}\n")
print(f"\n[*] Saved {len(packets)} packets to {log_path}", flush=True)
print("Done.", flush=True)
