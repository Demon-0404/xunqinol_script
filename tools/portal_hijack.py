# -*- coding: utf-8 -*-
"""Hijack portal: freeze at A, click B"""
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

if game_fd < 0:
    print("Game not connected!", flush=True)
    sys.exit(1)

print(f"PID={pid} fd={game_fd}", flush=True)
subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, 'portal_hijack.js'), 'r', encoding='utf-8') as f:
    JS = f.read() % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

pos_a_captured = False

def on_msg(msg, data):
    global pos_a_captured
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg}", flush=True)
        return
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] Hook ready", flush=True)
    elif ptype == 'auto_capture':
        if not pos_a_captured:
            pos_a_captured = True
            print(f">>> CAPTURED pos_A: {payload['hex']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

# Phase 1: stand at portal A
print("=" * 50, flush=True)
print("PHASE 1: Stand at PORTAL A, walk a bit", flush=True)
print("Waiting 15s for capture...", flush=True)
time.sleep(15)

if pos_a_captured:
    print(">>> POSITION FROZEN to portal A!", flush=True)
    script.exports_sync.freeze()
else:
    print("[!] Not captured yet, waiting 5s more...", flush=True)
    time.sleep(5)
    script.exports_sync.freeze()

# Phase 2: walk to portal B
print("=" * 50, flush=True)
print("PHASE 2: Walk to PORTAL B now! (15 seconds)", flush=True)
print("DO NOT click the portal yet!", flush=True)
time.sleep(15)

# Phase 3: click portal B
print("=" * 50, flush=True)
print("PHASE 3: CLICK PORTAL B NOW! (10 seconds)", flush=True)
print("Watch where you end up!", flush=True)
time.sleep(10)

script.exports_sync.unfreeze()
print("=" * 50, flush=True)
print("UNFROZEN. Did you go to A's destination or B's destination?", flush=True)
time.sleep(3)
session.detach()
print("Done.", flush=True)
