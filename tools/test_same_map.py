# -*- coding: utf-8 -*-
"""Same-map teleport test - capture then inject with shifted coords"""
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
print(f"Game fd={game_fd}", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var sendNative = new NativeFunction(libc.getExportByName("send"), 'int', ['int', 'pointer', 'int', 'int']);

var CAPTURED = null;
var DONE = false;

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();

        if (fd === GAME_FD && !DONE && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var plain = [];
            for (var i = 0; i < 29; i++) {{
                plain.push(buf.add(i + 1).readU8() ^ key);
            }}
            CAPTURED = plain;
            DONE = true;

            var hex = plain.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
            send({{t: 'captured', hex: hex}});

            // Now inject 3 different position shifts with delays
            injectShift(0x80, 0x00, 1);   // big X shift
            setTimeout(function(){{ injectShift(0x00, 0x80, 2); }}, 600);
            setTimeout(function(){{ injectShift(0x80, 0x80, 3); }}, 1200);
            setTimeout(function(){{ injectShift(0x40, 0x40, 4); }}, 1800);
        }}
    }}
}});

function injectShift(dx, dy, id) {{
    var mod = CAPTURED.slice(0);
    mod[26] = (mod[26] + dx) & 0xFF;
    mod[27] = (mod[27] + dy) & 0xFF;

    var K = Math.floor(Math.random() * 254) + 1;
    var pkt = Memory.alloc(30);
    pkt.writeU8(3);
    for (var i = 0; i < 29; i++) {{
        pkt.add(i + 1).writeU8(mod[i] ^ K);
    }}

    var ret = sendNative(GAME_FD, pkt, 30, 0);
    var h = mod.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
    send({{t: 'inject', id: id, ret: ret, hex: h}});
}}

Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 40) {{
            send({{t: 'recv', len: n, first: this.buf.readU8()}});
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
        print("[*] 移动角色触发抓包...", flush=True)
    elif ptype == 'captured':
        print(f"\n[CAPTURED] {payload['hex']}", flush=True)
        print("自动注入4次不同偏移...", flush=True)
    elif ptype == 'inject':
        status = "OK" if payload['ret'] >= 0 else "FAIL"
        print(f"\n[INJECT #{payload['id']}] send()={payload['ret']} {status}", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'recv':
        print(f"  [RECV {payload['len']}B first=0x{payload['first']:02x}]", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("等待抓包和注入... (15秒)", flush=True)
try:
    for i in range(15):
        time.sleep(1)
except KeyboardInterrupt:
    pass
print("\nDone.", flush=True)
session.detach()
