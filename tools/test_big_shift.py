# -*- coding: utf-8 -*-
"""Test large position shift + capture server response for position sync data"""
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
var count = 0;
var SHIFT_X = 90;
var SHIFT_Y = 90;

// Hook send: apply position shift in-place
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
                send({{t: 'init', m1: M1, m2: M2}});
            }}

            count++;
            var oldX = plain[17], oldY = plain[21];

            if (count >= 3) {{
                // Apply shift
                var newX = (oldX + SHIFT_X) & 0xFF;
                var newY = (oldY + SHIFT_Y) & 0xFF;

                plain[16] = newX ^ M1;
                plain[17] = newX;
                plain[20] = newY ^ M1;
                plain[21] = newY;

                // Re-encrypt with same key
                for (var i = 0; i < 29; i++) {{
                    buf.add(i + 1).writeU8(plain[i] ^ key);
                }}
                send({{t: 'mod', n: count, old_x: oldX, old_y: oldY, new_x: newX, new_y: newY}});
            }} else {{
                send({{t: 'base', n: count, x: oldX, y: oldY}});
            }}
        }}
    }}
}});

// Hook recv: capture ALL server responses
Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 0) {{
            // Try to decrypt with M1/M2 if we have them
            var first = this.buf.readU8();
            var info = 'len=' + n + ' first=0x' + ('0'+first.toString(16)).slice(-2);

            if (M1 !== null && n > 1) {{
                // Try XOR with key=first_byte
                var key = first;
                var decoded = [];
                for (var i = 1; i < Math.min(n, 20); i++) {{
                    decoded.push(this.buf.add(i).readU8() ^ key);
                }}
                info += ' dec20=' + decoded.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
            }}

            if (n > 100) {{
                send({{t: 'big_recv', info: info}});
            }} else if (n !== 33) {{
                send({{t: 'recv', info: info}});
            }}
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
        print("[*] 先抓2个基础位置包，然后施加 +90/+90 偏移", flush=True)
        print("[*] 请站在原地不要动！", flush=True)
    elif ptype == 'init':
        print(f"[*] Session: M1=0x{payload['m1']:02x} M2=0x{payload['m2']:02x}", flush=True)
    elif ptype == 'base':
        print(f"  [BASE #{payload['n']}] X={payload['x']} Y={payload['y']}", flush=True)
    elif ptype == 'mod':
        print(f"  [MOD #{payload['n']}] X: {payload['old_x']}->{payload['new_x']} Y: {payload['old_y']}->{payload['new_y']}", flush=True)
    elif ptype == 'recv':
        print(f"  RECV: {payload['info']}", flush=True)
    elif ptype == 'big_recv':
        print(f"  BIG_RECV: {payload['info']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting 20s...", flush=True)
try:
    for i in range(20):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
