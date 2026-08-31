# -*- coding: utf-8 -*-
"""Analyze movement step deltas to find per-frame step size"""
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
with open(os.path.join(script_dir, 'analyze_step.js'), 'r') as f:
    js_template = f.read()
JS = js_template % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        if msg.get('type') == 'error':
            print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] 步长分析就绪", flush=True)
        print("[*] 请点击远处让角色持续行走...", flush=True)
    elif ptype == 'delta':
        print(f"  [{payload['n']}] ({payload['fromX']},{payload['fromY']})->({payload['toX']},{payload['toY']}) dx={payload['dx']} dy={payload['dy']}", flush=True)
    elif ptype == 'stats':
        print(f"\n[STATS] {payload['count']} steps, avg abs delta={payload['avg']}, max={payload['max']} M1=0x{payload.get('M1',0):02x}", flush=True)
        print(f"  Top patterns:", flush=True)
        for t in payload['top3']:
            print(f"    [{t['key']}] x{t['cnt']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting... (点击远处持续走)", flush=True)
try:
    for i in range(60):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
