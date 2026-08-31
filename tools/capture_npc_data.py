# -*- coding: utf-8 -*-
"""Capture server entity data - look for NPC positions in recv packets"""
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
var playerX = null, playerY = null;
var recvCount = 0;
var sendCount = 0;

// Monitor send for player position
Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var p = [];
            for (var i = 0; i < 29; i++) p.push(buf.add(i + 1).readU8() ^ key);
            M1 = p[1]; M2 = p[3];
            sendCount++;
            var newX = p[17], newY = p[21];
            if (playerX === null || newX !== playerX || newY !== playerY) {{
                send({{t: 'player_pos', x: newX, y: newY, sub: p[6]}});
            }}
            playerX = newX;
            playerY = newY;
        }}
    }}
}});

// Monitor recv for entity data
Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 0) {{
            recvCount++;
            var data = [];
            for (var i = 0; i < n; i++) {{
                data.push(this.buf.add(i).readU8());
            }}
            send({{t: 'recv_raw', id: recvCount, len: n, data: data}});
        }}
    }}
}});

send({{t: 'ready'}});
"""

player_pos = None

def on_msg(msg, data):
    global player_pos
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("[*] 监控中... 让角色走到有 NPC 的地方（传送师附近），然后站在原地", flush=True)
        print("[*] 我会捕获服务端下发的实体数据", flush=True)
    elif ptype == 'player_pos':
        player_pos = (payload['x'], payload['y'])
        print(f"  PLAYER: X={payload['x']} Y={payload['y']}", flush=True)
    elif ptype == 'recv_raw':
        n = payload['len']
        raw = payload['data']

        # Skip small acks (33-byte 0xba heartbeats)
        if n == 33 and raw[0] == 0xba:
            return
        if n == 17 and raw[0] == 0xb9:
            return

        # Interesting packets
        print(f"\n[RECV #{payload['id']}] len={n} first=0x{raw[0]:02x}", flush=True)

        # Show raw hex
        hex_str = ' '.join(f"{b:02x}" for b in raw[:min(n, 256)])
        if n > 256:
            hex_str += f" ... (+{n-256} bytes)"
        print(f"  RAW: {hex_str}", flush=True)

        # Try decrypt with M1/M2 if available
        if player_pos and raw[0] not in [0xba, 0xb9, 0x03]:
            # Try XOR with first byte as key
            key = raw[0]
            dec = [b ^ key for b in raw[1:min(n, 200)]]
            dec_hex = ' '.join(f"{b:02x}" for b in dec)
            print(f"  DEC(key=0x{key:02x}): {dec_hex}", flush=True)

            # Look for patterns that look like coordinates (pairs of 0-255)
            # NPC data often has: [id...][x][y][name...]
            # Scan for byte pairs where both values are in reasonable range (10-246)
            pairs = []
            for i in range(len(dec) - 1):
                if 10 <= dec[i] <= 246 and 10 <= dec[i+1] <= 246:
                    # Found potential coordinate pair at offset i
                    pairs.append((i, dec[i], dec[i+1]))
            if pairs and len(pairs) <= 50:
                for offset, v1, v2 in pairs[:20]:
                    print(f"    Possible coord at +{offset}: ({v1}, {v2})", flush=True)

            # Also try without decryption
            pairs2 = []
            for i in range(len(raw) - 1):
                if 10 <= raw[i] <= 246 and 10 <= raw[i+1] <= 246:
                    pairs2.append((i, raw[i], raw[i+1]))
            if pairs2 and len(pairs2) <= 50:
                print(f"  RAW coord candidates ({len(pairs2)}):", flush=True)
                for offset, v1, v2 in pairs2[:15]:
                    print(f"    +{offset}: ({v1}, {v2})", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting 25s...", flush=True)
try:
    for i in range(25):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
