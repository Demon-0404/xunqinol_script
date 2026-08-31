# -*- coding: utf-8 -*-
"""Diagnose: show ALL traffic on game fd"""
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
print(f"Game fd={game_fd}, inode={game_inode}", flush=True)

# Also show all tcp connections
r3 = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/net/tcp | head -20"],
                    capture_output=True, text=True, timeout=10)
print(f"TCP connections:\n{r3.stdout[:500]}", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var count = 0;

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        if (fd === GAME_FD) {{
            var len = args[2].toInt32();
            var first = args[1].readU8();
            count++;
            send({{t: 'send', n: count, fd: fd, len: len, first: first,
                   hex: hexdump(args[1], {{length: Math.min(len, 32)}})}});
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
            count++;
            send({{t: 'recv', n: count, len: n, first: this.buf.readU8()}});
        }}
    }}
}});

send({{t: 'ready', fd: GAME_FD}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"\n[*] 监控 fd={payload['fd']}, 请在游戏中移动...", flush=True)
    elif ptype == 'send':
        print(f"\n[{payload['n']}] SEND len={payload['len']} first=0x{payload['first']:02x}", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'recv':
        print(f"\n[{payload['n']}] RECV len={payload['len']} first=0x{payload['first']:02x}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("监控15秒...", flush=True)
try:
    for i in range(15):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
