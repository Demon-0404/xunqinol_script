# -*- coding: utf-8 -*-
"""Test tiny position shift - modify in-memory position before game sends it"""
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
print("Attached!", flush=True)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var sendNative = new NativeFunction(libc.getExportByName("send"), 'int', ['int', 'pointer', 'int', 'int']);

var M1 = null, M2 = null;
var SHIFT_COUNT = 0;
var CAPTURED = null;

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();

        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var plain = [];
            for (var i = 0; i < 29; i++) {{
                plain.push(buf.add(i + 1).readU8() ^ key);
            }}

            // Session markers from header
            M1 = plain[1];
            M2 = plain[3];
            CAPTURED = plain;

            if (SHIFT_COUNT === 0) {{
                var hex = plain.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
                send({{t: 'first', hex: hex, m1: M1, m2: M2}});

                // Show the 6 position values
                var v1 = plain[17]; // pair (16,17): v1^M1, v1
                var v2 = plain[19]; // pair (18,19): v2^M2, v2
                var v3 = plain[21]; // pair (20,21): v3^M1, v3
                var v4 = plain[23]; // pair (22,23): v4^M2, v4
                send({{t: 'values', v1: v1, v2: v2, v3: v3, v4: v4}});
            }}

            if (SHIFT_COUNT < 5) {{
                SHIFT_COUNT++;
                // Apply increasing shifts to v1 (byte 17)
                var newV1 = (plain[17] + SHIFT_COUNT * 16) & 0xFF;
                plain[16] = newV1 ^ M1;  // re-encode pair
                plain[17] = newV1;

                // Re-encrypt with new random key
                var K = Math.floor(Math.random() * 254) + 1;
                var pkt = Memory.alloc(30);
                pkt.writeU8(3);
                for (var i = 0; i < 29; i++) {{
                    pkt.add(i + 1).writeU8(plain[i] ^ K);
                }}

                var newHex = plain.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
                var ret = sendNative(GAME_FD, pkt, 30, 0);
                send({{t: 'inject', id: SHIFT_COUNT, ret: ret, v1_new: newV1, hex: newHex}});
            }}
        }}
    }}
}});

Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 20) {{
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
        print("[*] 移动触发抓包，然后自动注入5次递增偏移...", flush=True)
    elif ptype == 'first':
        print(f"\n[FIRST] M1=0x{payload['m1']:02x} M2=0x{payload['m2']:02x}", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'values':
        print(f"  v1=0x{payload['v1']:02x} v2=0x{payload['v2']:02x} v3=0x{payload['v3']:02x} v4=0x{payload['v4']:02x}", flush=True)
    elif ptype == 'inject':
        s = "OK" if payload['ret'] >= 0 else "FAIL"
        print(f"\n[INJECT #{payload['id']}] v1=0x{payload['v1_new']:02x} send()={payload['ret']} {s}", flush=True)
        if payload['ret'] < 0:
            print(f"  断开于第{payload['id']}次注入!", flush=True)
    elif ptype == 'recv':
        print(f"  [RECV {payload['len']}B first=0x{payload['first']:02x}]", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("等待移动... (20秒)", flush=True)
try:
    for i in range(20):
        time.sleep(1)
except KeyboardInterrupt:
    pass
print("\nDone.", flush=True)
session.detach()
