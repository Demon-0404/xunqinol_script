"""Inject position packet with swapped map data (汉中→邯郸) via NativeFunction send()"""
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

# Find game socket fd
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
// 邯郸行政区 map segment (11 bytes at plaintext positions 17-27)
var HANDAN_MAP = [0x70, 0xc8, 0x70, 0xc9, 0x3f, 0x87, 0x3f, 0x86, 0xa1, 0xd2, 0x95];

var libc = Process.getModuleByName("libc.so");
var sendNative = new NativeFunction(libc.getExportByName("send"), 'int', ['int', 'pointer', 'int', 'int']);

var INJECTED = false;

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();

        if (fd === GAME_FD && !INJECTED && len >= 28 && buf.readU8() === 3) {{
            INJECTED = true;

            // Decrypt original
            var key = buf.add(1).readU8();
            var plaintext = [];
            for (var i = 0; i < len - 1; i++) {{
                plaintext.push(buf.add(i + 1).readU8() ^ key);
            }}
            var origHex = [];
            for (var j = 0; j < plaintext.length; j++) {{
                origHex.push(('0' + plaintext[j].toString(16)).slice(-2));
            }}
            send({{t: 'orig', len: len, data: origHex.join(' ')}});

            // Swap map segment: bytes 17-27 → HANDAN_MAP
            for (var k = 0; k < 11; k++) {{
                plaintext[17 + k] = HANDAN_MAP[k];
            }}

            var modHex = [];
            for (var m = 0; m < plaintext.length; m++) {{
                modHex.push(('0' + plaintext[m].toString(16)).slice(-2));
            }}
            send({{t: 'mod', len: len, data: modHex.join(' ')}});

            // Build new packet with random key
            var K = Math.floor(Math.random() * 254) + 1;
            var pkt = Memory.alloc(len);
            pkt.writeU8(3);  // type byte
            for (var n = 0; n < plaintext.length; n++) {{
                pkt.add(n + 1).writeU8(plaintext[n] ^ K);
            }}

            send({{t: 'sending', len: len, key: K, hex: hexdump(pkt, {{length: Math.min(len, 36)}})}});

            // Send additional packet
            var ret = sendNative(GAME_FD, pkt, len, 0);
            send({{t: 'result', ret: ret, msg: 'send() returned ' + ret}});
        }}
    }}
}});

// Monitor recv for server response
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
            send({{t: 'recv', len: n, first: first, hex: hexdump(this.buf, {{length: Math.min(n, 80)}})}});
        }}
    }}
}});

send({{t: 'ready', msg: 'Waiting for first 03 packet... (move character)'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"\n[*] {payload['msg']}", flush=True)
    elif ptype == 'orig':
        print(f"\n--- 原始包 (len={payload['len']}) ---", flush=True)
        print(f"  {payload['data']}", flush=True)
    elif ptype == 'mod':
        print(f"\n--- 修改后 (替换地图段为邯郸) ---", flush=True)
        print(f"  {payload['data']}", flush=True)
    elif ptype == 'sending':
        print(f"\n>>> 注入包 (len={payload['len']}, key=0x{payload['key']:02x})", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'result':
        print(f"\n=== send() 返回值 = {payload['ret']} ===", flush=True)
        if payload['ret'] >= 0:
            print("✓ 注入成功! 观察游戏是否切换地图...", flush=True)
        else:
            print("✗ send() 失败!", flush=True)
    elif ptype == 'recv':
        if payload['len'] > 100:
            print(f"\n  [RECV LARGE] len={payload['len']} first=0x{payload['first']:02x}", flush=True)
            print(f"  {payload['hex']}", flush=True)
        else:
            print(f"\n  [RECV] len={payload['len']} first=0x{payload['first']:02x}", flush=True)
            print(f"  {payload['hex']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("\n请在游戏中移动角色触发传送包... (20秒自动停止)", flush=True)
try:
    for i in range(20):
        time.sleep(1)
except KeyboardInterrupt:
    pass
print("\n停止.", flush=True)
session.detach()
