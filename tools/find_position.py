# -*- coding: utf-8 -*-
"""Find player position in game memory by scanning for coordinate patterns"""
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
    sys.exit(1)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var currentPos = null;
var M1 = null, M2 = null;

// Capture current position from send()
Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var plain = [];
            for (var i = 0; i < 29; i++) plain.push(buf.add(i + 1).readU8() ^ key);
            M1 = plain[1]; M2 = plain[3];
            currentPos = {{x: plain[17], y: plain[21]}};
        }}
    }}
}});

// Wait for first position capture, then scan memory
function doScan() {{
    if (currentPos === null) {{
        setTimeout(doScan, 1000);
        return;
    }}

    var x = currentPos.x;
    var y = currentPos.y;
    send({{t: 'scan_for', x: x, y: y, hex_x: ('0'+x.toString(16)).slice(-2),
           hex_y: ('0'+y.toString(16)).slice(-2)}});

    var ranges = Process.enumerateRanges({{protection: 'rw-', coalesce: true}});
    var candidates = [];

    ranges.forEach(function(range) {{
        var size = range.size.toInt32 ? range.size.toInt32() : Number(range.size);
        if (size < 65536 || size > 33554432) return; // 64KB - 32MB

        try {{
            // Pattern 1: [x, x, y, y] as consecutive bytes (with duplicate encoding)
            var p1 = [x, x, y, y].map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
            var m1 = Memory.scan(range.base, size, p1);
            if (m1 && m1.length > 0) {{
                candidates.push({{base: range.base, size_mb: (size/1048576).toFixed(1),
                                  pattern: 'xxyy', addr: m1[0].address, count: m1.length}});
            }}

            // Pattern 2: [x, y] as 2 bytes
            var p2 = [x, y].map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
            var m2 = Memory.scan(range.base, size, p2);
            if (m2 && m2.length > 0) {{
                candidates.push({{base: range.base, size_mb: (size/1048576).toFixed(1),
                                  pattern: 'xy', addr: m2[0].address, count: m2.length}});
            }}

            // Pattern 3: [x, y] as 16-bit little-endian values (2 bytes each)
            var p3 = [x, 0, y, 0].map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
            var m3 = Memory.scan(range.base, size, p3);
            if (m3 && m3.length > 0) {{
                candidates.push({{base: range.base, size_mb: (size/1048576).toFixed(1),
                                  pattern: 'x0y0', addr: m3[0].address, count: m3.length}});
            }}

            // Pattern 4: 4-byte ints (little endian)
            var p4 = [];
            p4.push(x & 0xFF);
            p4.push((x >> 8) & 0xFF);
            p4.push(0);
            p4.push(0);
            p4.push(y & 0xFF);
            p4.push((y >> 8) & 0xFF);
            p4.push(0);
            p4.push(0);
            var p4s = p4.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
            var m4 = Memory.scan(range.base, size, p4s);
            if (m4 && m4.length > 0) {{
                candidates.push({{base: range.base, size_mb: (size/1048576).toFixed(1),
                                  pattern: 'int32', addr: m4[0].address, count: m4.length}});
            }}
        }} catch(e) {{}}
    }});

    if (candidates.length > 0) {{
        send({{t: 'found', total: candidates.length}});
        for (var i = 0; i < Math.min(20, candidates.length); i++) {{
            var c = candidates[i];
            send({{t: 'cand', i: i, base: c.base, size_mb: c.size_mb,
                   pattern: c.pattern, addr: c.addr.toString(), count: c.count}});
        }}
    }} else {{
        send({{t: 'none', x: x, y: y}});
    }}
}}

setTimeout(doScan, 3000);
send({{t: 'ready'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] Ready, 等待位置包后扫描内存...", flush=True)
    elif ptype == 'scan_for':
        print(f"[*] Scanning for X={payload['x']} (0x{payload['hex_x']}) Y={payload['y']} (0x{payload['hex_y']})", flush=True)
    elif ptype == 'found':
        print(f"[+] Found {payload['total']} candidate matches!", flush=True)
    elif ptype == 'cand':
        print(f"  [{payload['i']}] {payload['addr']} base={payload['base']} "
              f"size={payload['size_mb']}MB pattern={payload['pattern']} count={payload['count']}", flush=True)
    elif ptype == 'none':
        print(f"[-] No matches for X={payload['x']} Y={payload['y']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting 15s...", flush=True)
try:
    for i in range(15):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
