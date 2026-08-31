# -*- coding: utf-8 -*-
"""Rapid teleport: find addr -> auto teleport test"""
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
with open(os.path.join(script_dir, 'teleport_rapid.js'), 'r') as f:
    js_template = f.read()
JS = js_template % game_fd

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

last_x, last_y = None, None
found_addr = None
found_event = False
tp_active = False

def on_msg(msg, data):
    global last_x, last_y, found_addr, found_event, tp_active
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        if msg.get('type') == 'error':
            print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("[*] 就绪 - 移动两次找到地址，然后自动测试瞬移", flush=True)

    elif ptype == 'scan1':
        print(f"[SCAN1] ({payload['x']},{payload['y']}) -> {payload['count']} matches", flush=True)

    elif ptype == 'scan2':
        print(f"[SCAN2] ({payload['x']},{payload['y']}) -> {payload['count']} matches", flush=True)

    elif ptype == 'found':
        found_addr = payload['addr']
        found_event = True
        print(f"\n[!!!] 找到: {payload['addr']} at ({payload['x']},{payload['y']})", flush=True)

    elif ptype == 'retry':
        print(f"[-] 未找到交叉匹配，继续移动...", flush=True)

    elif ptype == 'pos':
        x, y = payload['x'], payload['y']
        mem = payload.get('mem', '')
        tp = '[TP] ' if payload.get('target') else ''
        if last_x is None or x != last_x or y != last_y:
            print(f"  {tp}pos=({x},{y}){mem}", flush=True)
            last_x, last_y = x, y

    elif ptype == 'tp_start':
        tp_active = True
        print(f"[TP] 持续写入 ({payload['x']},{payload['y']}) @ {payload['addr']} (每30ms)", flush=True)

    elif ptype == 'tp_noaddr':
        print(f"[TP] 无地址，仅改包: ({payload['x']},{payload['y']})", flush=True)

    elif ptype == 'tp_stop':
        tp_active = False
        print(f"[TP] 停止", flush=True)

    elif ptype == 'speed_set':
        print(f"[SPEED] {payload['mult']}x", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

# Phase 1: Wait for address
print("Phase 1: 移动两次找到位置地址...", flush=True)
deadline = time.time() + 60
while not found_event and time.time() < deadline:
    time.sleep(0.3)

if not found_event:
    print("[-] 超时，未找到地址", flush=True)
    session.detach()
    sys.exit(1)

# Phase 2: Wait for stable position, then test teleport
print("\nPhase 2: 等待稳定位置后测试瞬移...", flush=True)
time.sleep(3)

if last_x is None:
    print("[-] 未检测到位置", flush=True)
    session.detach()
    sys.exit(1)

# Test 1: Teleport +50 in X and Y
tx = (last_x + 50) & 0xFF
ty = (last_y + 50) & 0xFF
print(f"\n[TEST1] 瞬移: ({last_x},{last_y}) -> ({tx},{ty}) (持续写入+改包)", flush=True)
old_x, old_y = last_x, last_y
script.post({'type': 'teleport', 'x': tx, 'y': ty})

# Wait 10 seconds, checking if position changes
print("  等待10秒观察位置...", flush=True)
for i in range(10):
    time.sleep(1)
    if last_x == tx and last_y == ty:
        print(f"  [!!!] 瞬移成功! 位置=({last_x},{last_y})", flush=True)
        break
else:
    print(f"  [-] 位置未变为目标: 当前=({last_x},{last_y}) 目标=({tx},{ty})", flush=True)

script.post({'type': 'stop_tp'})
time.sleep(1)

# Test 2: Try smaller teleport (+20)
tx2 = (last_x + 20) & 0xFF
ty2 = (last_y + 20) & 0xFF
print(f"\n[TEST2] 小步瞬移: ({last_x},{last_y}) -> ({tx2},{ty2})", flush=True)
script.post({'type': 'teleport', 'x': tx2, 'y': ty2})
for i in range(8):
    time.sleep(1)
    if last_x == tx2 and last_y == ty2:
        print(f"  [!!!] 瞬移成功! 位置=({last_x},{last_y})", flush=True)
        break
else:
    print(f"  [-] 位置未变为目标: 当前=({last_x},{last_y})", flush=True)

script.post({'type': 'stop_tp'})
time.sleep(1)

# Test 3: Speed hack 3x
print(f"\n[TEST3] 3x速度测试...", flush=True)
script.post({'type': 'speed', 'mult': 3.0})
print("  移动角色观察是否加速... (10秒)", flush=True)
time.sleep(10)
script.post({'type': 'speed', 'mult': 1.0})

print("\n[*] 测试完成", flush=True)
time.sleep(2)
session.detach()
print("Done.", flush=True)
