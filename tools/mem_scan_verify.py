# -*- coding: utf-8 -*-
"""12-byte wildcard scan: [X,0,0,0,?,?,?,?,Y,0,0,0] — very few false positives"""
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
with open(os.path.join(script_dir, 'scan_verify.js'), 'r') as f:
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
        print("[*] 12字节通配符扫描就绪", flush=True)
        print("[*] 模式: [X,0,0,0,?,?,?,?,Y,0,0,0]", flush=True)
        print("[*] 移动两次: 第1次扫描, 第2次交叉比对+写入测试", flush=True)

    elif ptype == 'move':
        print(f"  pos=({payload['x']},{payload['y']})", flush=True)

    elif ptype == 'scanning':
        print(f"\n[SCAN{payload['phase']}] X={payload['x']} Y={payload['y']}...", flush=True)

    elif ptype == 'scanned':
        print(f"  -> {payload['count']} matches", flush=True)

    elif ptype == 'candidate':
        print(f"  [CAND] {payload['addr']} u0={payload['u0'] & 0xFF} u4=0x{payload['u4']:08x} u8={payload['u8'] & 0xFF} u12=0x{payload['u12']:08x} pkt=({payload['pktX']},{payload['pktY']})", flush=True)

    elif ptype == 'tested':
        print(f"\n[WRITE] {payload['addr']}", flush=True)
        print(f"  ({payload['oldX']},{payload['oldY']}) -> ({payload['newX']},{payload['newY']})", flush=True)
        print(f"  写入成功: {payload['writeOk']}", flush=True)
        print(f"  等待下次移动看位置是否变化...", flush=True)

    elif ptype == 'test_err':
        print(f"  [ERR] {payload['addr']}: {payload['err']}", flush=True)

    elif ptype == 'write_result':
        print(f"\n[RESULT] {payload['addr']}", flush=True)
        print(f"  写入目标: ({payload['wroteX']},{payload['wroteY']})", flush=True)
        print(f"  当前内存: ({payload['memX']},{payload['memY']})", flush=True)
        print(f"  当前包位置: ({payload['pktX']},{payload['pktY']})", flush=True)
        if payload['pktX'] == payload['wroteX'] and payload['pktY'] == payload['wroteY']:
            print(f"  [!!!] 瞬移成功! 位置已变为写入值!", flush=True)
        elif payload['memX'] == payload['wroteX']:
            print(f"  [-] 内存值保留但位置未变 (不是权威位置源)", flush=True)
        elif payload['memX'] == payload['pktX']:
            print(f"  [-] 内存值被游戏覆盖回正版 (游戏覆盖了写入)", flush=True)
        else:
            print(f"  [-] 内存值已变化但不同于写入值或包值", flush=True)

    elif ptype == 'no_cross':
        print(f"\n[-] 无交叉匹配: prev={payload['prevCount']} new={payload['newCount']}", flush=True)
        print(f"  继续移动以缩小范围...", flush=True)

    elif ptype == 'desync':
        print(f"[DESYNC] mem=({payload['memX']},{payload['memY']}) pkt=({payload['pktX']},{payload['pktY']})", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting... (移动两次)", flush=True)
try:
    for i in range(180):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
