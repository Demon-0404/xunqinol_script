# -*- coding: utf-8 -*-
"""Analyze server response packets after position updates - look for position data"""
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
var M1 = null, M2 = null;
var sendCount = 0;
var lastSendTime = 0;

// Hook send - count position packets
Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD) {{
            var first = buf.readU8();
            if (len === 30 && first === 3) {{
                var key = buf.add(1).readU8();
                var p = [];
                for (var i = 0; i < Math.min(len-1, 30); i++) p.push(buf.add(i+1).readU8() ^ key);
                if (M1 === null) {{ M1 = p[1]; M2 = p[3]; }}
                sendCount++;
                send({{t: 'send', n: sendCount, x: p[17], y: p[21], sub: p[6],
                       hex: p.slice(0,29).map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ')}});
                lastSendTime = Date.now();
            }} else if (first === 3) {{
                send({{t: 'send_other', len: len,
                       hex: hexdump(buf, {{length: Math.min(len, 32)}})}});
            }}
        }}
    }}
}});

// Hook recv - capture ALL responses with hex dump
Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 0) {{
            var elapsed = Date.now() - lastSendTime;
            var first = this.buf.readU8();
            var dump = '';
            if (n <= 256) {{
                dump = hexdump(this.buf, {{length: Math.min(n, 128)}});
            }} else {{
                // For large packets, show first and last 32 bytes
                var first32 = hexdump(this.buf, {{length: 32}});
                var last32 = hexdump(this.buf.add(n - 32), {{length: 32, ansi: false}});
                dump = first32 + '... [SKIP ' + (n-64) + ' bytes] ...' + last32;
            }}
            send({{t: 'recv', len: n, first: first, elapsed: elapsed, dump: dump}});
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
        print("[*] 监控 send/recv... 请点击远处让角色走动！", flush=True)
    elif ptype == 'send':
        print(f"\n[SEND #{payload['n']}] X={payload['x']} Y={payload['y']} sub=0x{payload['sub']:02x}", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'send_other':
        print(f"\n[SEND OTHER] len={payload['len']}", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'recv':
        ms = payload['elapsed']
        print(f"\n[RECV] len={payload['len']} first=0x{payload['first']:02x} elapsed={ms}ms", flush=True)
        print(f"  {payload['dump']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting 30s...", flush=True)
try:
    for i in range(30):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
