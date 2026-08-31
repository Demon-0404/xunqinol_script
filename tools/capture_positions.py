"""Capture FULL position packets to find map ID bytes"""
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

# Find game fd
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

# Check frida-server
import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)
print("Attached! (显示完整包数据)", flush=True)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var lastCode = '';
var lastTime = Date.now();

function dec(buf, len) {{
    if (len < 2) return '';
    var key = buf.add(1).readU8();
    var maxData = Math.min(len - 1, 29);  // up to 29 data bytes
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

        if (fd === GAME_FD && len >= 16 && len <= 64) {{
            var firstByte = buf.readU8();
            if (firstByte === 3) {{
                var full = dec(buf, len);
                var now = Date.now();
                var dt = now - lastTime;

                // Only print if data changed from last line or >500ms
                if (full !== lastCode || dt > 500) {{
                    send({{t: 'pkt', len: len, data: full, dt: dt}});
                    lastCode = full;
                    lastTime = now;
                }}
            }}
        }}
    }}
}});

// Also capture recv for server responses (map data?)
Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.len = args[2].toInt32();
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 40) {{
            send({{t: 'recv', len: n, hex: hexdump(this.buf, {{length: Math.min(n, 48)}})}});
        }}
    }}
}});

send({{t: 'ready', msg: 'Full packet monitor on fd=' + GAME_FD}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"\n[*] {payload['msg']}", flush=True)
    elif ptype == 'pkt':
        print(f"  [OUT len={payload['len']:2d}] {payload['data']}", flush=True)
    elif ptype == 'recv':
        print(f"\n  [RECV len={payload['len']}]", flush=True)
        print(f"  {payload['hex']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("\n监控中... 在游戏里移动或传送 (Ctrl+C 停止)", flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n停止.", flush=True)
    session.detach()
