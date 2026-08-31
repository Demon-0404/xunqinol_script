# -*- coding: utf-8 -*-
"""Capture full RECV data during portal for later injection"""
import sys, time, subprocess, os, json

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"

r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"], capture_output=True, text=True, timeout=15)
pid = None
for line in r.stdout.split("\n"):
    if "proj.xqj" in line:
        parts = line.split()
        if len(parts) >= 2: pid = int(parts[1]); break

game_fd = -1
for tcp_file in ["net/tcp", "net/tcp6"]:
    r = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/{tcp_file}"], capture_output=True, text=True, timeout=10)
    for line in r.stdout.split("\n"):
        line = line.strip()
        if not line or line.startswith("sl"): continue
        parts = line.split()
        if len(parts) >= 10 and parts[3] == "01":
            inode = parts[9]
            if inode != "0":
                r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/ | grep {inode}"], capture_output=True, text=True, timeout=10)
                for fl in r2.stdout.split("\n"):
                    fp = fl.strip().split()
                    if len(fp) >= 8:
                        try:
                            fd = int(fp[7])
                            if fd > 2: game_fd = fd; break
                        except: pass
        if game_fd > 0: break
    if game_fd > 0: break

if game_fd < 0: print("Game not connected!"); sys.exit(1)
print(f"PID={pid} fd={game_fd}", flush=True)
subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, 'capture_full_recv.js'), 'r', encoding='utf-8') as f:
    JS = f.read() % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

captured = []

def on_msg(msg, data):
    global captured
    payload = msg.get('payload', {})
    if msg.get('type') == 'error': print(f"[!] {msg}", flush=True); return
    if not isinstance(payload, dict): return
    ptype = payload.get('t', '?')
    if ptype == 'ready': print("[*] Ready", flush=True)
    elif ptype == 'portal': print("\n>>> PORTAL! Capturing RECV...", flush=True)
    elif ptype == 'recv': print(f"  RECV#{payload['n']} len={payload['len']}", flush=True)
    elif ptype == 'capture_done':
        print(f"\n=== Capture done: {payload['total']} packets ===", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("[*] Walk through portal! 30s", flush=True)
time.sleep(30)

# Get captured data
packets = script.exports_sync.get_packets()
if packets:
    print(f"\n=== Captured {len(packets)} RECV packets ===", flush=True)
    log_path = os.path.join(script_dir, '..', 'logs', 'recv_map_data.json')
    with open(log_path, 'w') as f:
        json.dump(packets, f, indent=2)
    print(f"Saved to {log_path}", flush=True)
    for i, p in enumerate(packets):
        print(f"  [{i}] len={p['len']} {p['hex'][:60]}...", flush=True)
else:
    print("[!] No packets captured", flush=True)

session.detach()
print("Done.", flush=True)
