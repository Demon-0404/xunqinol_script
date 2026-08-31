# -*- coding: utf-8 -*-
"""Capture portal packet, then replay it later from a different position"""
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

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, 'replay_portal2.js'), 'r', encoding='utf-8') as f:
    js_template = f.read()
JS = js_template % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

captured = False
script = None

def on_msg(msg, data):
    global captured
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"[*] {payload['msg']}", flush=True)
    elif ptype == 'captured':
        captured = True
        print(f"\n[CAPTURE] {payload['hex']}", flush=True)
    elif ptype == 'replay':
        print(f"[REPLAY] key=0x{payload['key']:02x} ret={payload['ret']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("[*] 第1步: 走传送门 → 捕获数据包", flush=True)
for i in range(60):
    time.sleep(1)
    if captured:
        break

if not captured:
    print("[!] 未捕获到传送包", flush=True)
    session.detach()
    sys.exit(1)

print("\n[*] 第2步: 走到地图上另一个位置（不要走传送门！）", flush=True)
print("[*] 到位后等10秒自动重放...", flush=True)
time.sleep(10)

print("[*] 正在重放传送包...", flush=True)
result = script.exports_sync.replay()
print(f"[*] 重放结果: {result}", flush=True)
print("[*] 观察游戏：传送成功？掉线？无事发生？", flush=True)

time.sleep(15)
session.detach()
print("Done.", flush=True)
