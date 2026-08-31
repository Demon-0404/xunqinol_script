# -*- coding: utf-8 -*-
"""Calibrate screen-to-game coordinate mapping"""
import sys, time, subprocess
from datetime import datetime

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

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var p = [];
            for (var i = 0; i < 29; i++) p.push(buf.add(i + 1).readU8() ^ key);
            var x = p[17], y = p[21];
            if (x !== lastX || y !== lastY) {{
                send({{t: 'pos', x: x, y: y, ts: Date.now()}});
                lastX = x; lastY = y;
            }}
        }}
    }}
}});
send({{t: 'ready'}});
"""

print("=" * 50)
print("校准开始！请按顺序点击：")
print("  1. 屏幕正中心 → 等 3 秒")
print("  2. 屏幕上方   → 等 3 秒")
print("  3. 屏幕下方   → 等 3 秒")
print("  4. 屏幕左方   → 等 3 秒")
print("  5. 屏幕右方   → 等 3 秒")
print("=" * 50)

results = []
last_ts = None

def on_msg(msg, data):
    global last_ts
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    if payload.get('t') == 'pos':
        x, y, ts = payload['x'], payload['y'], payload['ts']
        now = datetime.now().strftime("%H:%M:%S")
        gap = f"+{ts - last_ts:4d}ms" if last_ts else "start"
        last_ts = ts
        print(f"[{now}]  X={x:3d}  Y={y:3d}  ({gap})", flush=True)
        results.append((x, y, ts))

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    for i in range(60):
        time.sleep(1)
except KeyboardInterrupt:
    pass

session.detach()

# Analyze
if len(results) >= 5:
    print("\n===== 分析 =====")
    # Take the last position of each movement phase (when character stopped)
    # Simple approach: show every position with large time gap (>2s) as a "stop point"
    stops = [results[0]]
    for i in range(1, len(results)):
        gap = results[i][2] - results[i-1][2]
        if gap > 1500:  # >1.5s gap = new click
            stops.append(results[i])
    stops.append(results[-1])  # last position

    print(f"检测到 {len(stops)} 个停留点:")
    for i, (x, y, ts) in enumerate(stops):
        print(f"  [{i}] X={x:3d} Y={y:3d}", flush=True)

    if len(stops) >= 5:
        center = stops[0]
        up_pos = stops[1]
        down_pos = stops[2]
        left_pos = stops[3]
        right_pos = stops[4]

        print(f"\n中心: ({center[0]}, {center[1]})")
        print(f"上:   ({up_pos[0]}, {up_pos[1]})  delta=({up_pos[0]-center[0]}, {up_pos[1]-center[1]})")
        print(f"下:   ({down_pos[0]}, {down_pos[1]})  delta=({down_pos[0]-center[0]}, {down_pos[1]-center[1]})")
        print(f"左:   ({left_pos[0]}, {left_pos[1]})  delta=({left_pos[0]-center[0]}, {left_pos[1]-center[1]})")
        print(f"右:   ({right_pos[0]}, {right_pos[1]})  delta=({right_pos[0]-center[0]}, {right_pos[1]-center[1]})")

print("Done.", flush=True)
