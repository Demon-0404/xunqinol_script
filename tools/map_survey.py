# -*- coding: utf-8 -*-
"""Map survey: track player pos + capture server entity data + record map bounds"""
import sys, time, subprocess, json, os

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

# Log file
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs', 'map_survey.jsonl')
print(f"Logging to {log_path}", flush=True)
logf = open(log_path, 'w', encoding='utf-8')

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;
var recvId = 0;

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var p = [];
            for (var i = 0; i < 29; i++) p.push(buf.add(i + 1).readU8() ^ key);
            var x = p[17], y = p[21];
            if (x !== lastX || y !== lastY) {{
                send({{t: 'pos', x: x, y: y, sub: p[6]}});
                lastX = x; lastY = y;
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
        if (this.fd === GAME_FD && n > 0) {{
            recvId++;
            var data = [];
            for (var i = 0; i < n; i++) data.push(this.buf.add(i).readU8());
            var first = data[0];

            // Skip heartbeats
            if (n === 33 && first === 0xba) return;
            if (n === 17 && first === 0xb9) return;

            send({{t: 'entity', id: recvId, len: n, first: first, data: data}});
        }}
    }}
}});

send({{t: 'ready'}});
"""

min_x, max_x = 255, 0
min_y, max_y = 255, 0

def on_msg(msg, data):
    global min_x, max_x, min_y, max_y
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("=" * 55)
        print("测绘模式已启动")
        print("1. 绕地图边缘走一圈 → 确定地图大小")
        print("2. 遇到 NPC 停下 2 秒 → 捕获实体数据")
        print("3. 按 Ctrl+C 结束")
        print("=" * 55)
    elif ptype == 'pos':
        x, y = payload['x'], payload['y']
        if x < min_x: min_x = x
        if x > max_x: max_x = x
        if y < min_y: min_y = y
        if y > max_y: max_y = y
        print(f"[POS] X={x:3d} Y={y:3d}  |  范围: X[{min_x}-{max_x}] Y[{min_y}-{max_y}]  地图约 {max_x-min_x+1}x{max_y-min_y+1}", flush=True)

        logf.write(json.dumps({'type': 'pos', 'x': x, 'y': y, 'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y}) + '\n')
        logf.flush()
    elif ptype == 'entity':
        n = payload['len']
        raw = payload['data']
        first = payload['first']

        # Decrypt with first byte as key
        key = first
        dec = [b ^ key for b in raw[1:]]

        # Extract UTF-8 strings from decrypted data
        strings = []
        i = 0
        while i < len(dec) - 2:
            # Look for UTF-8 multi-byte sequences (CJK range: E4-E9)
            if 0xe4 <= dec[i] <= 0xe9 and i + 2 < len(dec):
                # Try to decode a UTF-8 character sequence
                start = i
                while i < len(dec):
                    b = dec[i]
                    if b >= 0xc0 or (0x20 <= b <= 0x7e) or b >= 0x80:
                        i += 1
                        # Estimate end
                        if i - start > 80:
                            break
                    else:
                        break
                if i - start >= 6:  # At least 2 Chinese chars
                    try:
                        s = bytes(dec[start:i]).decode('utf-8', errors='replace')
                        # Filter: only keep if has Chinese chars
                        has_cjk = any('一' <= c <= '鿿' or '　' <= c <= '〿' for c in s)
                        if has_cjk and len(s) >= 2:
                            strings.append({'offset': start, 'text': s})
                    except:
                        pass
            else:
                i += 1

        # Also try to find potential coordinate pairs (two consecutive bytes in 5-250 range)
        coords = []
        for i in range(len(raw) - 1):
            b1, b2 = raw[i], raw[i+1]
            if 5 <= b1 <= 250 and 5 <= b2 <= 250:
                coords.append({'offset': i, 'v1': b1, 'v2': b2})

        hex_preview = ' '.join(f"{b:02x}" for b in raw[:min(n, 80)])

        entry = {
            'type': 'entity',
            'id': payload['id'],
            'len': n,
            'first': first,
            'hex': hex_preview,
            'strings': strings[:10],
            'raw_coord_candidates': coords[:20]
        }

        print(f"\n[ENTITY #{payload['id']}] len={n} key=0x{first:02x}", flush=True)
        if strings:
            print(f"  Names found ({len(strings)}):", flush=True)
            for s in strings[:5]:
                print(f"    +{s['offset']}: {s['text']}", flush=True)

        logf.write(json.dumps(entry, ensure_ascii=False) + '\n')
        logf.flush()

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Running... (Ctrl+C to stop)", flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

session.detach()
logf.close()
print(f"\n===== 测绘结果 =====")
print(f"X 范围: {min_x} ~ {max_x} (宽度: {max_x - min_x + 1})")
print(f"Y 范围: {min_y} ~ {max_y} (高度: {max_y - min_y + 1})")
print(f"地图尺寸约: {max_x - min_x + 1} x {max_y - min_y + 1}")
print(f"数据已保存: {log_path}")
