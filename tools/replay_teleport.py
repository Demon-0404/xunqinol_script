# -*- coding: utf-8 -*-
"""Replay teleport v2 - NPC payloads XOR'd with session M1 marker"""
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

// === CONSTANTS (same across all sessions after XOR with M1) ===
// NPC Interact 1 (21B total, sub=0x09): 13-byte payload
// Raw pairs: (90,90)(90,90)(98,98)(98,98)(98,9d)(68,89) + last_byte cd
var NPC1_CONST = [0x90, 0x90, 0x90, 0x90, 0x98, 0x98, 0x98, 0x98, 0x98, 0x9d, 0x68, 0x89, 0xcd];

// NPC Interact 2 (16B total, sub=0x09): 8-byte payload
// Raw pairs: (92,92)(92,92)(91,94)(94,ad)
var NPC2_CONST = [0x92, 0x92, 0x92, 0x92, 0x91, 0x94, 0x94, 0xad];

// Map Confirm (24B total, sub=0x05): 16-byte payload (first 12 constant, last 4 from capture #12)
// First 6 pairs: (07,07)(07,07)(0c,0d)(0d,0d)(0d,0d)(0d,0d)
// Last 4 bytes from capture: 6b ad 9b fc → constants: 0c ca fc 9b (XOR'd with M1=0x67)
var CONFIRM_CONST = [0x07, 0x07, 0x07, 0x07, 0x0c, 0x0d, 0x0d, 0x0d,
                     0x0d, 0x0d, 0x0d, 0x0d, 0x0c, 0xca, 0xfc, 0x9b];

// Handan position (from capture #17): bytes 16-28
var HANDAN_POS = [0x70, 0x17, 0x70, 0x16, 0x3f, 0x58, 0x3f, 0x59, 0xa1, 0x0a, 0x79, 0xc4, 0x33];

var M1 = null;  // Session marker (byte 1 of header)
var HEADER16 = null;  // Bytes 0-15 of position header
var STAGE = 'capture';

// Capture M1 from a live packet
Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && STAGE === 'capture' && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var plain = [];
            for (var i = 0; i < len - 1; i++) {{
                plain.push(buf.add(i + 1).readU8() ^ key);
            }}
            M1 = plain[1];  // Session marker
            HEADER16 = plain.slice(0, 16);
            send({{t: 'captured', m1: M1, header: HEADER16,
                   m1_hex: ('0' + M1.toString(16)).slice(-2)}});
            STAGE = 'injecting';
        }}
    }}
}});

// Monitor recv
Interceptor.attach(libc.getExportByName("recv"), {{
    onEnter: function(args) {{
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.len = args[2].toInt32();
    }},
    onLeave: function(ret) {{
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 0) {{
            send({{t: 'recv', len: n, first: this.buf.readU8()}});
        }}
    }}
}});

// Build packet: [header6, subtype, payload...] with M1 XOR on even payload bytes
function buildNPC(header6, subtype, consts) {{
    // header6: [00, M1, 00, M2, 01, M2]
    // Apply M1 XOR to even-indexed bytes in consts
    var enc = [];
    for (var i = 0; i < consts.length; i++) {{
        if (i % 2 === 0) {{
            enc.push(consts[i] ^ M1);  // Even: XOR with M1
        }} else {{
            enc.push(consts[i]);       // Odd: raw value
        }}
    }}
    return header6.concat([subtype]).concat(enc);
}}

function buildAndSend(plaintext) {{
    var K = Math.floor(Math.random() * 254) + 1;
    var totalLen = plaintext.length + 1;
    var pkt = Memory.alloc(totalLen);
    pkt.writeU8(3);
    for (var i = 0; i < plaintext.length; i++) {{
        pkt.add(i + 1).writeU8(plaintext[i] ^ K);
    }}
    send({{t: 'pkt', len: totalLen, hex: hexdump(pkt, {{length: Math.min(totalLen, 36)}})}});
    return sendNative(GAME_FD, pkt, totalLen, 0);
}}

function doInject() {{
    var H6 = HEADER16.slice(0, 6);  // [00, M1, 00, M2, 01, M2]
    // Also need the full header for position packets
    var HFULL = HEADER16;  // 16 bytes

    // Step 1: NPC interact 1
    send({{t: 'step', msg: 'Step 1/4: NPC interact 1 (sub=09, 21B)'}});
    var npc1 = buildNPC(H6, 0x09, NPC1_CONST);
    send({{t: 'plain', data: npc1.map(function(b) {{ return ('0'+b.toString(16)).slice(-2); }}).join(' ')}});
    var r1 = buildAndSend(npc1);
    send({{t: 'ret', r: r1}});

    // Step 2: Map confirm (after short delay for server)
    setTimeout(function() {{
        send({{t: 'step', msg: 'Step 2/4: Map confirm (sub=05, 24B)'}});
        var confirm = buildNPC(H6, 0x05, CONFIRM_CONST);
        send({{t: 'plain', data: confirm.map(function(b) {{ return ('0'+b.toString(16)).slice(-2); }}).join(' ')}});
        var r2 = buildAndSend(confirm);
        send({{t: 'ret', r: r2}});

        // Step 3: NPC interact 2
        setTimeout(function() {{
            send({{t: 'step', msg: 'Step 3/4: NPC interact 2 (sub=09, 16B)'}});
            var npc2 = buildNPC(H6, 0x09, NPC2_CONST);
            send({{t: 'plain', data: npc2.map(function(b) {{ return ('0'+b.toString(16)).slice(-2); }}).join(' ')}});
            var r3 = buildAndSend(npc2);
            send({{t: 'ret', r: r3}});

            // Step 4: Handan position
            setTimeout(function() {{
                send({{t: 'step', msg: 'Step 4/4: Handan position (sub=02, 30B)'}});
                var handan = HFULL.concat(HANDAN_POS);
                send({{t: 'plain', data: handan.map(function(b) {{ return ('0'+b.toString(16)).slice(-2); }}).join(' ')}});
                var r4 = buildAndSend(handan);
                send({{t: 'ret', r: r4}});
                STAGE = 'done';
                send({{t: 'done'}});
            }}, 800);
        }}, 500);
    }}, 300);
}}

var poll = setInterval(function() {{
    if (M1 !== null && STAGE === 'injecting') {{
        clearInterval(poll);
        doInject();
    }}
}}, 200);

send({{t: 'ready'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("\n[*] 请在游戏中轻微移动触发抓包...", flush=True)
    elif ptype == 'captured':
        print(f"\n[CAPTURED] M1=0x{payload['m1_hex']} header={payload['header']}", flush=True)
    elif ptype == 'step':
        print(f"\n>>> {payload['msg']}", flush=True)
    elif ptype == 'plain':
        print(f"    DEC: {payload['data']}", flush=True)
    elif ptype == 'pkt':
        print(f"    RAW: {payload['hex']}", flush=True)
    elif ptype == 'ret':
        print(f"    send() = {payload['r']} {'OK' if payload['r'] >= 0 else 'FAIL'}", flush=True)
    elif ptype == 'recv':
        if payload['len'] > 200:
            print(f"  [RECV {payload['len']}B] first=0x{payload['first']:02x}", flush=True)
        else:
            print(f"  [RECV {payload['len']}B] first=0x{payload['first']:02x}", flush=True)
    elif ptype == 'done':
        print("\n=== All packets injected! Watch game screen ===", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("轻微移动角色... (20秒)", flush=True)
try:
    for i in range(20):
        time.sleep(1)
except KeyboardInterrupt:
    pass
print("\nDone.", flush=True)
session.detach()
