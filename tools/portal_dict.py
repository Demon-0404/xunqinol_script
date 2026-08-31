# -*- coding: utf-8 -*-
"""Record portal IDs to build a dictionary"""
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
with open(os.path.join(script_dir, 'portal_dict.js'), 'r', encoding='utf-8') as f:
    js_template = f.read()
JS = js_template % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

portals = []

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"[*] {payload['msg']}", flush=True)
    elif ptype == 'portal':
        n = payload['n']
        pid_hex = payload['id']
        var_hex = payload['vars']
        print(f"\n=== 传送门 #{n} ===", flush=True)
        print(f"  ID (18B): {pid_hex}", flush=True)
        print(f"  VAR (9B): {var_hex}", flush=True)
        print(f"  RAW: {payload['raw']}", flush=True)
        portals.append({'n': n, 'id': pid_hex, 'vars': var_hex, 'raw': payload['raw']})

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("[*] 现在可以去走各种传送门了。每次走过都会记录。", flush=True)
print("[*] 按 Ctrl+C 退出并保存...", flush=True)
try:
    for i in range(300):  # 5 minutes
        time.sleep(1)
except KeyboardInterrupt:
    pass

session.detach()

# Save dictionary
log_path = os.path.join(script_dir, '..', 'logs', 'portal_dict.txt')
os.makedirs(os.path.dirname(log_path), exist_ok=True)
with open(log_path, 'w') as f:
    for p in portals:
        f.write(f"Portal#{p['n']}: ID={p['id']} VARS={p['vars']} RAW={p['raw']}\n")
print(f"\n[*] {len(portals)} 个传送门记录已保存到 {log_path}", flush=True)
print("Done.", flush=True)
