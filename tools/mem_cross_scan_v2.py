# -*- coding: utf-8 -*-
"""Cross-scan v2: try multiple encoding patterns for position in memory"""
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
var lastX = null, lastY = null;
var scanPhase = 0;
var prevResults = {{}};  // pattern_type -> Set of address strings
var prevX = 0, prevY = 0;
var prevM1 = 0, prevM2 = 0;
var M1 = 0, M2 = 0;
var gotMarkers = false;

function bytesToHex(arr) {{
    return arr.map(function(b){{return ('0'+b.toString(16)).slice(-2);}}).join(' ');
}}

function scanForPattern(ranges, patBytes) {{
    var patStr = bytesToHex(patBytes);
    var results = [];
    ranges.forEach(function(range) {{
        try {{
            var matches = Memory.scanSync(range.base, range.size, patStr);
            for (var i = 0; i < matches.length; i++) {{
                results.push(matches[i].address.toString());
            }}
        }} catch(e) {{}}
    }});
    return results;
}}

function scanAllPatterns(x, y, m1, m2) {{
    // Collect ranges once
    var allRanges = [];
    var ranges = Process.enumerateRanges({{protection: 'rw-', coalesce: true}});
    ranges.forEach(function(range) {{
        var size = range.size.toInt32 ? range.size.toInt32() : Number(range.size);
        if (size >= 65536 && size <= 67108864) {{
            allRanges.push({{base: range.base, size: size}});
        }}
    }});

    var result = {{}};

    // Pattern 1: [X, Y] 2 bytes
    result['xy'] = scanForPattern(allRanges, [x, y]);

    // Pattern 2: [X^M1, X] 2 bytes
    result['x_xor1'] = scanForPattern(allRanges, [x ^ m1, x]);

    // Pattern 3: [X, X^M1] 2 bytes
    result['x_xor2'] = scanForPattern(allRanges, [x, x ^ m1]);

    // Pattern 4: [Y^M2, Y] 2 bytes
    result['y_xor1'] = scanForPattern(allRanges, [y ^ m2, y]);

    // Pattern 5: [Y, Y^M2] 2 bytes
    result['y_xor2'] = scanForPattern(allRanges, [y, y ^ m2]);

    // Pattern 6: [X, X^M1, Y, Y^M2] 4 bytes
    result['full_xor'] = scanForPattern(allRanges, [x, x ^ m1, y, y ^ m2]);

    // Pattern 7: [X^M1, X, Y^M2, Y] 4 bytes
    result['full_xor2'] = scanForPattern(allRanges, [x ^ m1, x, y ^ m2, y]);

    // Pattern 8: X as little-endian int32 (4 bytes)
    result['x_int32'] = scanForPattern(allRanges, [x & 0xFF, (x >> 8) & 0xFF, 0, 0]);

    // Pattern 9: X as little-endian int16 then Y as int16
    result['xy_int16'] = scanForPattern(allRanges, [x & 0xFF, (x >> 8) & 0xFF, y & 0xFF, (y >> 8) & 0xFF]);

    // Pattern 10: X as float, Y as float
    var fbuf = new ArrayBuffer(4);
    var fv = new DataView(fbuf);
    fv.setFloat32(0, x, true);
    var fx = [fv.getUint8(0), fv.getUint8(1), fv.getUint8(2), fv.getUint8(3)];
    fv.setFloat32(0, y, true);
    var fy = [fv.getUint8(0), fv.getUint8(1), fv.getUint8(2), fv.getUint8(3)];
    result['xy_float'] = scanForPattern(allRanges, fx.concat(fy));

    // Count totals
    var summary = {{}};
    for (var k in result) {{
        summary[k] = result[k].length;
    }}
    result['_summary'] = summary;
    return result;
}}

// Monitor position and do cross-scan
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

            // Extract M1, M2 from first packet
            if (!gotMarkers) {{
                M1 = p[1];
                M2 = p[3];
                gotMarkers = true;
                send({{t: 'markers', M1: M1, M2: M2}});
            }}

            if (lastX !== null && (x !== lastX || y !== lastY)) {{
                send({{t: 'move', x: x, y: y, oldX: lastX, oldY: lastY, phase: scanPhase}});

                if (scanPhase === 0) {{
                    prevX = x; prevY = y;
                    prevM1 = M1; prevM2 = M2;
                    prevResults = scanAllPatterns(x, y, M1, M2);
                    var s = prevResults['_summary'];
                    send({{t: 'phase1', x: x, y: y, summary: s}});
                    scanPhase = 1;
                }} else if (scanPhase === 1) {{
                    var newResults = scanAllPatterns(x, y, M1, M2);

                    // Cross-reference each pattern
                    for (var pat in prevResults) {{
                        if (pat === '_summary') continue;
                        var prevSet = {{}};
                        var prevArr = prevResults[pat];
                        for (var i = 0; i < prevArr.length; i++) prevSet[prevArr[i]] = true;

                        var newArr = newResults[pat] || [];
                        var cross = [];
                        for (var i = 0; i < newArr.length; i++) {{
                            if (prevSet[newArr[i]]) {{
                                cross.push(newArr[i]);
                                if (cross.length >= 10) break;
                            }}
                        }}

                        if (cross.length > 0) {{
                            send({{t: 'cross', pattern: pat, count: cross.length, addrs: cross,
                                   fromX: prevX, fromY: prevY, toX: x, toY: y}});
                        }}
                    }}

                    // Prepare for next round
                    prevResults = newResults;
                    prevX = x; prevY = y;
                    prevM1 = M1; prevM2 = M2;
                }}
            }}

            lastX = x; lastY = y;
        }}
    }}
}});

send({{t: 'ready'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        if msg.get('type') == 'error':
            print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] 交叉扫描 v2 - 多种编码模式", flush=True)
        print("[*] 第1次移动 -> 记录所有匹配", flush=True)
        print("[*] 第2次移动 -> 交叉比对", flush=True)
    elif ptype == 'markers':
        print(f"[*] M1=0x{payload['M1']:02x} M2=0x{payload['M2']:02x}", flush=True)
    elif ptype == 'move':
        print(f"\n[MOVE] ({payload['oldX']},{payload['oldY']}) -> ({payload['x']},{payload['y']})", flush=True)
    elif ptype == 'phase1':
        print(f"[PHASE1] X={payload['x']} Y={payload['y']}", flush=True)
        for k, v in sorted(payload['summary'].items()):
            print(f"    {k}: {v} matches", flush=True)
        print(f"[*] 再次移动以交叉比对...", flush=True)
    elif ptype == 'cross':
        print(f"\n[!!!] CROSS [{payload['pattern']}]: {payload['count']} match", flush=True)
        print(f"    ({payload['fromX']},{payload['fromY']}) -> ({payload['toX']},{payload['toY']})", flush=True)
        for a in payload['addrs']:
            print(f"    {a}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting... (move to trigger scan, then move again to cross-reference)", flush=True)
try:
    for i in range(180):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
