# -*- coding: utf-8 -*-
"""Step 1: capture map data. Step 2: inject it on a different map."""
import sys, time, subprocess, os

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
with open(os.path.join(script_dir, 'snatch_and_inject.js'), 'r', encoding='utf-8') as f:
    JS = f.read() % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

captured_data = ''
capture_done_flag = False

def on_msg(msg, data):
    global capture_done_flag
    payload = msg.get('payload', {})
    if msg.get('type') == 'error': print(f"[!] {msg}", flush=True); return
    if not isinstance(payload, dict): return
    ptype = payload.get('t', '?')
    if ptype == 'ready': print("[*] Ready", flush=True)
    elif ptype == 'capture_start': print("\n>>> Portal sent! Capturing RECV data...", flush=True)
    elif ptype == 'capture_done':
        capture_done_flag = True
        print(f">>> Captured {payload['totalLen']} bytes!", flush=True)
    elif ptype == 'injected': print(f">>> INJECTED {payload['len']} bytes!", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

# ===== Phase 1: Walk through portal to capture =====
print("=" * 50, flush=True)
print("PHASE 1: Walk through portal NOW!", flush=True)
print("(This captures the RECV data for the destination map)", flush=True)
time.sleep(30)

if capture_done_flag:
    captured_data = script.exports_sync.get_capture()
    print(f">>> Saved {len(captured_data)//2} bytes of map data", flush=True)
else:
    # Manual capture after timeout
    captured_data = script.exports_sync.get_capture()
    if captured_data:
        print(f">>> Got {len(captured_data)//2} bytes", flush=True)
    else:
        print("[!] No data captured. Walk through portal and re-run.", flush=True)
        session.detach()
        sys.exit(1)

# ===== Phase 2: Walk back then inject =====
print("=" * 50, flush=True)
print("PHASE 2: Walk BACK to the previous map (15 seconds)", flush=True)
print("Then stand still and wait for injection...", flush=True)
time.sleep(15)

print(">>> Injecting captured map data NOW!", flush=True)
result = script.exports_sync.inject(captured_data)
print(f"Result: {result}", flush=True)

print(">>> Observe: Did the map change? Any crash/disconnect?", flush=True)
time.sleep(15)

session.detach()
print("Done.", flush=True)
