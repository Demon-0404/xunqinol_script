# -*- coding: utf-8 -*-
"""Read-only monitor: capture position packets, show delta analysis"""
import sys, time, subprocess

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

# Find fd
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
    print("Cannot find game fd!", flush=True)
    sys.exit(1)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var count = 0;
var M1 = null, M2 = null;
var lastPos = null;

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();

        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var plain = [];
            for (var i = 0; i < 29; i++) plain.push(buf.add(i + 1).readU8() ^ key);

            if (M1 === null) {{
                M1 = plain[1]; M2 = plain[3];
            }}

            count++;
            var pos = {{
                v1: plain[17], v2: plain[19], v3: plain[21], v4: plain[23],
                sub: plain[6],
                raw: plain.slice(8, 29)
            }};

            var msg = {{t: 'pos', n: count, v1: pos.v1, v2: pos.v2, v3: pos.v3, v4: pos.v4, sub: pos.sub}};

            if (lastPos !== null) {{
                msg.d1 = pos.v1 - lastPos.v1;
                msg.d2 = pos.v2 - lastPos.v2;
                msg.d3 = pos.v3 - lastPos.v3;
                msg.d4 = pos.v4 - lastPos.v4;
            }}

            if (count <= 5 || msg.d1 !== 0 || msg.d2 !== 0 || msg.d3 !== 0 || msg.d4 !== 0) {{
                msg.hex = plain.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
                send(msg);
            }}

            lastPos = pos;
        }}
    }}
}});

send({{t: 'ready'}});
"""

last = None
movement_log = []

def on_msg(msg, data):
    global last, movement_log
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] 监控中... 请点击远处让角色走起来！", flush=True)
    elif ptype == 'pos':
        d1 = payload.get('d1', 0)
        d2 = payload.get('d2', 0)
        d3 = payload.get('d3', 0)
        d4 = payload.get('d4', 0)
        has_move = d1 != 0 or d2 != 0 or d3 != 0 or d4 != 0

        if has_move:
            marker = " <-- MOVEMENT"
            movement_log.append(dict(d1=d1, d2=d2, d3=d3, d4=d4))
        else:
            marker = ""

        print(f"  [#{payload['n']}] v1={payload['v1']:3d} v2={payload['v2']:3d} v3={payload['v3']:3d} v4={payload['v4']:3d}"
              f"  d=({d1:+d},{d2:+d},{d3:+d},{d4:+d}) sub=0x{payload['sub']:02x}{marker}", flush=True)
        if has_move and 'hex' in payload:
            print(f"    hex={payload['hex']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("等待30秒...", flush=True)
try:
    for i in range(30):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()

if movement_log:
    print(f"\n===== 移动分析 ({len(movement_log)} 次变化) =====")
    for i, m in enumerate(movement_log):
        print(f"  [{i+1}] d1={m['d1']:+d} d2={m['d2']:+d} d3={m['d3']:+d} d4={m['d4']:+d}", flush=True)
else:
    print("\n没有检测到移动！", flush=True)

print("Done.", flush=True)
