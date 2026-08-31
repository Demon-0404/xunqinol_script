# -*- coding: utf-8 -*-
"""Auto teleport test: scan -> find address -> write test value -> verify"""
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
with open(os.path.join(script_dir, 'mem_test_teleport.js'), 'r') as f:
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
        print("[*] 自动瞬移测试", flush=True)
        print("[*] 第1步: 点击远处移动角色 (触发第1次扫描)", flush=True)
        print("[*] 第2步: 再点击移动 (交叉比对+自动测试写入)", flush=True)
    elif ptype == 'scanning':
        print(f"[SCAN] Phase {payload['phase']} X={payload['x']}...", flush=True)
    elif ptype == 'scanned':
        print(f"       {payload['count']} addresses matched", flush=True)
    elif ptype == 'found':
        print(f"\n[!!!] 找到位置: {payload['addr']}", flush=True)
        print(f"      X=0x{payload['u0']:08x} Y=0x{payload['u8']:08x} (pkt X={payload['x']} Y={payload['y']})", flush=True)
    elif ptype == 'test_write':
        print(f"\n[TEST] 写入 X={payload['newX']} (原值={payload['oldX']}) @ {payload['addr']}", flush=True)
        print(f"      等待下次移动看位置是否变化...", flush=True)
    elif ptype == 'write_fail':
        print(f"[FAIL] 写入失败: {payload['err']}", flush=True)
    elif ptype == 'test_result':
        if payload['match']:
            print(f"\n[!!!] 瞬移成功! 位置从 ({payload['beforeX']},{payload['beforeY']}) 变为 ({payload['afterX']},{payload['afterY']})", flush=True)
            print(f"      预期 X={payload['expectedX']} 实际 X={payload['afterX']} ✓", flush=True)
        else:
            print(f"\n[-] 瞬移无效: ({payload['beforeX']},{payload['beforeY']}) -> ({payload['afterX']},{payload['afterY']})", flush=True)
            print(f"      预期 X={payload['expectedX']} 实际 X={payload['afterX']} — 内存修改不生效", flush=True)
    elif ptype == 'restored':
        print(f"[*] 已恢复原值 X={payload['x']}", flush=True)
    elif ptype == 'retry':
        print(f"[RETRY] {payload['msg']}", flush=True)
    elif ptype == 'desync':
        print(f"[DESYNC] pkt=({payload['pktX']},{payload['pktY']}) mem=({payload['memX']},{payload['memY']}) — 不同步!", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting... (移动两次以触发扫描和测试)", flush=True)
try:
    for i in range(180):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
