# -*- coding: utf-8 -*-
"""Find position in memory by comparing before/after movement snapshots"""
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
var scanCount = 0;

// Monitor position
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

            if (lastX !== null && (x !== lastX || y !== lastY) && scanCount < 3) {{
                scanCount++;
                send({{t: 'move', x: x, y: y, oldX: lastX, oldY: lastY}});
                scanForPosition(x, y);
            }}

            lastX = x; lastY = y;
        }}
    }}
}});

function scanForPosition(targetX, targetY) {{
    send({{t: 'scan_start', x: targetX, y: targetY}});

    var ranges = Process.enumerateRanges({{protection: 'rw-', coalesce: true}});
    var found = [];

    ranges.forEach(function(range) {{
        var size = range.size.toInt32 ? range.size.toInt32() : Number(range.size);
        if (size < 65536 || size > 67108864) return; // 64KB - 64MB
        if (found.length >= 10) return;

        try {{
            // Pattern: [X, X, Y, Y] as consecutive bytes (duplicate encoding)
            var p1 = [targetX, targetX, targetY, targetY];
            var ps1 = '';
            for (var i = 0; i < 4; i++) {{
                if (ps1.length > 0) ps1 += ' ';
                ps1 += ('0' + p1[i].toString(16)).slice(-2);
            }}
            var m1 = Memory.scanSync(range.base, size, ps1);
            if (m1.length > 0) {{
                found.push({{addr: m1[0].address.toString(), count: m1.length, pattern: 'xxyy', base: range.base.toString(), size_mb: (size/1048576).toFixed(1)}});
            }}

            // Pattern: [X, Y] as 2 bytes
            var p2 = [targetX, targetY];
            var ps2 = '';
            for (var i = 0; i < 2; i++) {{
                if (ps2.length > 0) ps2 += ' ';
                ps2 += ('0' + p2[i].toString(16)).slice(-2);
            }}
            var m2 = Memory.scanSync(range.base, size, ps2);
            if (m2.length > 0 && m2.length < 100) {{
                found.push({{addr: m2[0].address.toString(), count: m2.length, pattern: 'xy', base: range.base.toString(), size_mb: (size/1048576).toFixed(1)}});
            }}

            // Pattern: X as 4-byte LE int
            var p3 = [targetX & 0xFF, (targetX >> 8) & 0xFF, 0, 0, targetY & 0xFF, (targetY >> 8) & 0xFF, 0, 0];
            var ps3 = '';
            for (var i = 0; i < 8; i++) {{
                if (ps3.length > 0) ps3 += ' ';
                ps3 += ('0' + p3[i].toString(16)).slice(-2);
            }}
            var m3 = Memory.scanSync(range.base, size, ps3);
            if (m3.length > 0 && m3.length < 100) {{
                found.push({{addr: m3[0].address.toString(), count: m3.length, pattern: 'int32', base: range.base.toString(), size_mb: (size/1048576).toFixed(1)}});
            }}

            // Pattern: X and Y as float (IEEE 754)
            // Convert to float bytes
            var fbuf = new ArrayBuffer(4);
            var fview = new DataView(fbuf);
            fview.setFloat32(0, targetX, true);
            var fx = [];
            for (var i = 0; i < 4; i++) fx.push(('0' + fview.getUint8(i).toString(16)).slice(-2));
            fview.setFloat32(0, targetY, true);
            var fy = [];
            for (var i = 0; i < 4; i++) fy.push(('0' + fview.getUint8(i).toString(16)).slice(-2));
            var ps4 = fx.join(' ') + ' ' + fy.join(' ');
            var m4 = Memory.scanSync(range.base, size, ps4);
            if (m4.length > 0 && m4.length < 100) {{
                found.push({{addr: m4[0].address.toString(), count: m4.length, pattern: 'float', base: range.base.toString(), size_mb: (size/1048576).toFixed(1)}});
            }}
        }} catch(e) {{}}
    }});

    if (found.length > 0) {{
        send({{t: 'found', results: found.slice(0, 20)}});
    }} else {{
        send({{t: 'not_found'}});
    }}
}}

send({{t: 'ready'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] 请点击远处让角色移动...", flush=True)
    elif ptype == 'move':
        print(f"\n[MOVE] {payload['oldX']},{payload['oldY']} -> {payload['x']},{payload['y']}", flush=True)
    elif ptype == 'scan_start':
        print(f"[SCAN] Searching for X={payload['x']} Y={payload['y']}...", flush=True)
    elif ptype == 'found':
        print(f"[+] {len(payload['results'])} matches:", flush=True)
        for r in payload['results']:
            print(f"    {r['addr']} [{r['pattern']}] x{r['count']} base={r['base']} sz={r['size_mb']}MB", flush=True)
    elif ptype == 'not_found':
        print("[-] No matches found", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("Waiting 60s for movement... (click far away!)", flush=True)
try:
    for i in range(60):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
