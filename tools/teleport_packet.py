# -*- coding: utf-8 -*-
"""Teleport via packet modification - change position in send() buffer"""
import sys, time, subprocess, os, threading

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
with open(os.path.join(script_dir, 'teleport_packet.js'), 'r') as f:
    js_template = f.read()
JS = js_template % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

last_seen_x = None
last_seen_y = None
teleport_sent = False
move_count = 0

def on_msg(msg, data):
    global last_seen_x, last_seen_y, teleport_sent, move_count
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        if msg.get('type') == 'error':
            print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("[*] 包修改模式就绪", flush=True)
        print("[*] 等待移动... 几秒后自动发送瞬移测试", flush=True)

    elif ptype == 'pos':
        x, y = payload['x'], payload['y']
        if last_seen_x is None or x != last_seen_x or y != last_seen_y:
            print(f"  pos=({x},{y})", flush=True)
            last_seen_x, last_seen_y = x, y
            move_count += 1

    elif ptype == 'cmd':
        print(f"[CMD] {payload['cmd']}: {payload}", flush=True)

    elif ptype == 'teleport':
        print(f"\n[TP] 包已修改: ({payload['fromX']},{payload['fromY']}) -> ({payload['toX']},{payload['toY']})", flush=True)
        print(f"    观察下次位置是否变化...", flush=True)

    elif ptype == 'status':
        print(f"[STATUS] mode={payload['mode']} speed={payload['speedMult']} last=({payload.get('lastX')},{payload.get('lastY')})", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

# Auto-test: after seeing some movements, send teleport
def auto_test():
    global teleport_sent, move_count, last_seen_x, last_seen_y
    time.sleep(8)  # Wait for user to move around
    if last_seen_x is not None and not teleport_sent:
        # Read current position from game
        script.post({'type': 'status'})
        time.sleep(0.5)
        if last_seen_x is not None:
            target_x = (last_seen_x + 30) & 0xFF
            target_y = (last_seen_y + 30) & 0xFF
            print(f"\n[*] 自动测试: 瞬移到 ({target_x},{target_y}) (原 ({last_seen_x},{last_seen_y}) + 30)", flush=True)
            script.post({'type': 'teleport', 'x': target_x, 'y': target_y})
            teleport_sent = True
            # Wait and check if position changed
            time.sleep(5)
            script.post({'type': 'status'})
            if last_seen_x == target_x and last_seen_y == target_y:
                print(f"[!!!] 瞬移成功! 位置已变为目标值!", flush=True)
            else:
                print(f"[-] 位置未变为目标值 (当前: {last_seen_x},{last_seen_y})", flush=True)

t = threading.Thread(target=auto_test, daemon=True)
t.start()

print("Waiting... (移动角色)", flush=True)
try:
    for i in range(60):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
