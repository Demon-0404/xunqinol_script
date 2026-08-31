# -*- coding: utf-8 -*-
"""Capture ALL packets during real teleport - no dedup, full detail"""
import sys, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"  # 七伤盾

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

r = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/net/tcp"],
                   capture_output=True, text=True, timeout=10)
game_inode = None
for line in r.stdout.split("\n"):
    if "7532" in line:
        parts = line.strip().split()
        if len(parts) >= 10:
            game_inode = parts[9]
            break

game_fd = 63
if game_inode:
    r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/ | grep {game_inode}"],
                       capture_output=True, text=True, timeout=10)
    for line in r2.stdout.split("\n"):
        parts = line.strip().split()
        if len(parts) >= 8:
            game_fd = int(parts[7])
            break
print(f"Game fd={game_fd}", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)
print("Attached! Capturing ALL packets...\n", flush=True)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");

function decFull(buf, len) {{
    if (len < 2) return 'too_short';
    var key = buf.add(1).readU8();
    var maxData = Math.min(len - 1, 32);
    var parts = [];
    for (var i = 0; i < maxData; i++) {{
        var b = buf.add(i + 1).readU8() ^ key;
        parts.push(('0' + b.toString(16)).slice(-2));
    }}
    return parts.join(' ');
}}

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len >= 12 && len <= 64) {{
            var first = buf.readU8();
            var plain = decFull(buf, len);
            send({{t: 'OUT', len: len, type: first, plain: plain,
                   hex: hexdump(buf, {{length: Math.min(len, 36)}})}});
        }}
    }}
}});

Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.len = args[2].toInt32();
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 0) {{
            var first = this.buf.readU8();
            send({{t: 'IN', len: n, first: first,
                   hex: hexdump(this.buf, {{length: Math.min(n, 64)}})}});
        }}
    }}
}});

send({{t: 'ready'}});
"""

pkt_count = 0

def on_msg(msg, data):
    global pkt_count
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] 监控中！请用 NPC 传送到邯郸...\n", flush=True)
    elif ptype == 'OUT':
        pkt_count += 1
        sub = payload.get('plain', '').split(' ')[6] if len(payload.get('plain', '').split(' ')) > 6 else '?'
        print(f"\n[{pkt_count}] >>> OUT len={payload['len']} type=0x{payload['type']:02x} sub=0x{sub}", flush=True)
        print(f"    RAW: {payload['hex']}", flush=True)
        print(f"    DEC: {payload.get('plain', '?')}", flush=True)
    elif ptype == 'IN':
        pkt_count += 1
        print(f"\n[{pkt_count}] <<< IN  len={payload['len']} first=0x{payload['first']:02x}", flush=True)
        print(f"    RAW: {payload['hex']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("现在请点击 NPC 开始传送！(30秒)", flush=True)
try:
    for i in range(30):
        time.sleep(1)
except KeyboardInterrupt:
    pass
print("\n停止.", flush=True)
session.detach()
