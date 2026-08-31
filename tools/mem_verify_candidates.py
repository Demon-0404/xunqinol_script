# -*- coding: utf-8 -*-
"""Verify position candidate: read memory at candidate addresses, try to modify"""
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
var M1 = 0, M2 = 0;
var gotMarkers = false;
var testPhase = 0;  // 0=monitor, 1=test write

// Candidate addresses from cross-scan
var CANDIDATE_ADDRS = [
    "0xc2f9cf68",
    "0xc2f9cfb8"
];

function readNearby(addr, range) {{
    var result = [];
    try {{
        var base = ptr(addr).sub(range);
        var bytes = base.readByteArray(range * 2);
        if (!bytes) return "read failed";
        var arr = new Uint8Array(bytes);
        var s = "";
        for (var i = 0; i < arr.length; i++) {{
            if (i > 0 && i % 16 === 0) s += "\\n";
            s += ('0' + arr[i].toString(16)).slice(-2) + " ";
        }}
        return s;
    }} catch(e) {{
        return "err: " + e.toString();
    }}
}}

function readInt32(addrStr) {{
    try {{
        return ptr(addrStr).readU32();
    }} catch(e) {{
        return -1;
    }}
}}

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

            if (!gotMarkers) {{
                M1 = p[1]; M2 = p[3];
                gotMarkers = true;
            }}

            if (testPhase === 0 && lastX !== null && (x !== lastX || y !== lastY)) {{
                // Read candidate addresses
                var info = {{t: 'verify', x: x, y: y}};
                info['addr0_val'] = readInt32(CANDIDATE_ADDRS[0]);
                info['addr1_val'] = readInt32(CANDIDATE_ADDRS[1]);
                // Also read nearby Y candidates (offset from X addr)
                var yOffsets = [4, 8, 12, 16, -4, -8];
                info['nearby'] = {{}};
                yOffsets.forEach(function(off) {{
                    try {{
                        var addr = ptr(CANDIDATE_ADDRS[0]).add(off);
                        info['nearby'][off] = addr.readU32();
                    }} catch(e) {{}}
                }});
                send(info);
            }}

            if (testPhase === 1 && lastX !== null && x !== lastX) {{
                // After our write, check what the game reads
                send({{t: 'after_write', x: x, y: y, addr0: readInt32(CANDIDATE_ADDRS[0])}});
                testPhase = 2;
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
        if msg.get('type') == 'error':
            print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] 验证模式 - 监控候选地址", flush=True)
        print(f"[*] 候选: 0xc2f9cf68, 0xc2f9cfb8", flush=True)
        print("[*] 移动角色观察地址值是否跟随变化...", flush=True)
    elif ptype == 'verify':
        print(f"\n[POS] X={payload['x']} Y={payload['y']}", flush=True)
        print(f"    [0xc2f9cf68] u32 = {payload['addr0_val']} (0x{payload['addr0_val']:08x})", flush=True)
        print(f"    [0xc2f9cfb8] u32 = {payload['addr1_val']} (0x{payload['addr1_val']:08x})", flush=True)
        for off, val in sorted(payload.get('nearby', {}).items()):
            print(f"    [offset {off:+d}] u32 = {val} (0x{val:08x})", flush=True)
    elif ptype == 'after_write':
        print(f"\n[POST-WRITE] X={payload['x']} addr0={payload['addr0']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting... (move to verify)", flush=True)
try:
    for i in range(120):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
