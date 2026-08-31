# -*- coding: utf-8 -*-
"""Cross-scan: find addresses whose values change from pos1 to pos2"""
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

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;
var scanPhase = 0;
var prevMatches = [];
var prevX = 0, prevY = 0;

function bytesToHex(arr) {{
    return arr.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
}}

function scanAll(patBytes, patName) {{
    var patStr = bytesToHex(patBytes);
    var ranges = Process.enumerateRanges({{protection: 'rw-', coalesce: true}});
    var all = [];
    ranges.forEach(function(range) {{
        var size = range.size.toInt32 ? range.size.toInt32() : Number(range.size);
        if (size < 65536 || size > 67108864) return;
        try {{
            var matches = Memory.scanSync(range.base, size, patStr);
            for (var i = 0; i < matches.length; i++) {{
                all.push(matches[i].address.toString());
            }}
        }} catch(e) {{}}
    }});
    return all;
}}

// Monitor position and do cross-scan
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

            if (lastX !== null && (x !== lastX || y !== lastY)) {{
                send({{t: 'move', x: x, y: y, oldX: lastX, oldY: lastY, phase: scanPhase}});

                if (scanPhase === 0) {{
                    // First move: save all matches
                    prevX = x; prevY = y;
                    var pat = [x, y];
                    prevMatches = scanAll(pat, 'xy');
                    send({{t: 'phase1', count: prevMatches.length, x: x, y: y}});
                    scanPhase = 1;
                }} else if (scanPhase === 1) {{
                    // Second move: scan for new values, cross-reference
                    var newMatches = scanAll([x, y], 'xy');

                    // Find intersection: addresses that were in prevMatches
                    var prevSet = {{}};
                    for (var i = 0; i < prevMatches.length; i++) prevSet[prevMatches[i]] = true;

                    var cross = [];
                    for (var i = 0; i < newMatches.length; i++) {{
                        if (prevSet[newMatches[i]]) {{
                            cross.push(newMatches[i]);
                            if (cross.length >= 20) break;
                        }}
                    }}

                    if (cross.length > 0) {{
                        send({{t: 'cross', count: cross.length, addrs: cross,
                               fromX: prevX, fromY: prevY, toX: x, toY: y}});
                    }} else {{
                        send({{t: 'no_cross', fromX: prevX, fromY: prevY, toX: x, toY: y,
                               prevCount: prevMatches.length, newCount: newMatches.length}});
                    }}

                    // Prepare for next round
                    prevMatches = newMatches;
                    prevX = x; prevY = y;
                }}
            }}

            lastX = x; lastY = y;
        }}
    }}
}});

send({{t: 'ready'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] 交叉扫描模式", flush=True)
        print("[*] 第1次移动 → 记录所有匹配地址", flush=True)
        print("[*] 第2次移动 → 找出值跟着变的地址（真坐标）", flush=True)
    elif ptype == 'move':
        print(f"\n[MOVE] ({payload['oldX']},{payload['oldY']}) -> ({payload['x']},{payload['y']})", flush=True)
    elif ptype == 'phase1':
        print(f"[PHASE1] {payload['count']} addresses match X={payload['x']} Y={payload['y']}", flush=True)
        print(f"[*] 再次移动以交叉比对...", flush=True)
    elif ptype == 'cross':
        print(f"\n[!!!] CROSS-MATCH: {payload['count']} addresses changed from ({payload['fromX']},{payload['fromY']}) to ({payload['toX']},{payload['toY']})", flush=True)
        for a in payload['addrs']:
            print(f"    {a}", flush=True)
    elif ptype == 'no_cross':
        print(f"\n[-] No cross-match: {payload['prevCount']} old / {payload['newCount']} new", flush=True)
        print(f"    Position ({payload['fromX']},{payload['fromY']}) -> ({payload['toX']},{payload['toY']})", flush=True)
        print(f"    Position value NOT stored as [X,Y] bytes in memory", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting... (click far to move twice)", flush=True)
try:
    for i in range(120):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
