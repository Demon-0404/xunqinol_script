# -*- coding: utf-8 -*-
"""Sniff RECV packets during portal transition"""
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
with open(os.path.join(script_dir, 'sniff_recv.js'), 'r', encoding='utf-8') as f:
    js_template = f.read()
JS = js_template % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

portal_sent = False
recv_buf = []

def on_msg(msg, data):
    global portal_sent, recv_buf
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"[*] {payload['msg']}", flush=True)
    elif ptype == 'PORTAL_SENT':
        portal_sent = True
        recv_buf = []
        print(f"\n>>> 检测到传送包发送！等待服务端回复...", flush=True)
    elif ptype == 'recv':
        if portal_sent:
            recv_buf.append(payload)
        else:
            # 只打印长度异常的大包
            if payload['len'] > 50:
                print(f"  [bg recv#{payload['n']}] len={payload['len']} {payload['hex'][:80]}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("[*] 请在同一个地图上走传送门... 60秒后自动退出", flush=True)
try:
    for i in range(60):
        time.sleep(1)
        # 走传送门后2秒，打印收到的回复包
        if portal_sent and len(recv_buf) >= 3:
            time.sleep(1)
            break
except KeyboardInterrupt:
    pass

if portal_sent and recv_buf:
    print(f"\n===== 传送门后服务端回复 (共{len(recv_buf)}包) =====", flush=True)
    for p in recv_buf:
        print(f"  RECV len={p['len']:3d} | {p['hex']}", flush=True)
else:
    print("\n[*] 未检测到传送门事件（或未收到后续包）", flush=True)

# Keep running a bit longer
try:
    for i in range(10):
        time.sleep(1)
except KeyboardInterrupt:
    pass

session.detach()
print("Done.", flush=True)
