"""Inject teleport packet v4 - keep original length, verify replacement"""
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
var PLAINTEXT = [0x00, 0x8a, 0x00, 0x8b, 0x01, 0x8b, 0x02, 0x74, 0xfe, 0x74, 0xfe, 0x77, 0xFC, 0x89, 0xFC];  // 原始位置（传送前）
var STAGE = 'waiting';  // waiting -> captured -> injected -> verified

var libc = Process.getModuleByName("libc.so");

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        this.fd = fd;
        this.buf = buf;
        this.orig_len = len;

        if (fd === GAME_FD && len >= 16 && len <= 64) {{
            var firstByte = buf.readU8();
            if (STAGE === 'waiting' && firstByte === 3) {{
                STAGE = 'captured';
                send({{t: 'orig_pkt', len: len, hex: hexdump(buf, {{length: Math.min(len, 32)}})}});

                // Encrypt teleport plaintext with random key
                var K = Math.floor(Math.random() * 256);
                buf.writeU8(3);  // type byte
                for (var i = 0; i < 15; i++) {{
                    buf.add(i + 1).writeU8(PLAINTEXT[i] ^ K);
                }}

                // MODIFY SAME BUFFER — keep original length
                // Zero out remaining bytes (16 onwards)
                for (var j = 16; j < len; j++) {{
                    buf.add(j).writeU8(0);
                }}

                // Log modified buffer
                send({{t: 'mod_pkt', len: len, hex: hexdump(buf, {{length: Math.min(len, 32)}}), key: K}});

                // DON'T change args[2] — keep original length
                STAGE = 'injected';
            }}
        }}
    }},
    onLeave: function(ret) {{
        if (this.fd === GAME_FD && STAGE === 'injected') {{
            send({{t: 'send_ret', ret: ret.toInt32(), orig_len: this.orig_len}});
            STAGE = 'verified';
        }}
    }}
}});

// Hook recv() to see server response to our packet
Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.len = args[2].toInt32();
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 0 && n < 500) {{
            var firstFew = [];
            for (var i = 0; i < Math.min(n, 8); i++) {{
                firstFew.push(this.buf.add(i).readU8());
            }}
            send({{t: 'recv', len: n, first: firstFew, hex: hexdump(this.buf, {{length: Math.min(n, 64)}})}});
        }}
    }}
}});

send({{t: 'ready', msg: 'fd=' + GAME_FD + ' — move to trigger'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"\n[*] {payload['msg']}", flush=True)
    elif ptype == 'orig_pkt':
        print(f"\n--- 原始包 (len={payload['len']}) ---", flush=True)
        print(f"{payload['hex']}", flush=True)
    elif ptype == 'mod_pkt':
        print(f"\n--- 修改后包 (len={payload['len']}, key=0x{payload['key']:02x}) ---", flush=True)
        print(f"{payload['hex']}", flush=True)
    elif ptype == 'send_ret':
        print(f"\n>>> send() 返回值 = {payload['ret']} (原始长度={payload['orig_len']}) <<<", flush=True)
    elif ptype == 'recv':
        print(f"\n  [RECV] len={payload['len']}", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['msg']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("\n请在游戏中移动角色... (15秒自动停止)", flush=True)
try:
    for i in range(15):
        time.sleep(1)
except KeyboardInterrupt:
    pass
print("\n停止.", flush=True)
session.detach()
