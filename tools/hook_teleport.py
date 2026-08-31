"""Hook teleport + network capture for 跑商"""
import sys, os, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16544"

# Parse PID
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

# Forward
subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)
print("Attached!", flush=True)

JS = """
var base = null;
Process.enumerateRanges('r--').forEach(function(r) {
    if (r.file && r.file.path && r.file.path.indexOf('libtestcpp.so') !== -1) {
        if (base === null || r.base.compare(base) < 0) base = r.base;
    }
});
if (!base) {
    send({t:'err', m:'libtestcpp.so not found'});
} else {
    send({t:'info', m:'Base=' + base});

    // ── Safe hooks ────────────────────────────

    // jlapp_jumpUrl - safe to hook, logs URL parameter
    try {
        Interceptor.attach(base.add(0x1375d0), {
            onEnter: function(args) {
                send({t:'jumpUrl', a0: ptr(args[0]).readCString() || 'null'});
            },
            onLeave: function(ret) {}
        });
        send({t:'info', m:'jlapp_jumpUrl hooked'});
    } catch(e) { send({t:'err', m:'jumpUrl: '+e}); }

    // ── Hook send/recv to capture game packets ──

    var sendPtr = Module.findExportByName("libc.so", "send");
    var recvPtr = Module.findExportByName("libc.so", "recv");
    var sendtoPtr = Module.findExportByName("libc.so", "sendto");
    var recvfromPtr = Module.findExportByName("libc.so", "recvfrom");

    if (sendPtr) {
        Interceptor.attach(sendPtr, {
            onEnter: function(args) {
                var fd = args[0].toInt32();
                var buf = args[1];
                var len = args[2].toInt32();
                if (len > 0 && len < 4096) {
                    var data = hexdump(buf, {length: Math.min(len, 128)});
                    send({t:'send', fd: fd, len: len, hex: data});
                }
            }
        });
        send({t:'info', m:'send hooked'});
    }
    if (recvPtr) {
        Interceptor.attach(recvPtr, {
            onEnter: function(args) {
                this.fd = args[0].toInt32();
                this.buf = args[1];
                this.len = args[2].toInt32();
            },
            onLeave: function(ret) {
                var rv = ret.toInt32();
                if (rv > 0 && rv < 4096) {
                    var data = hexdump(this.buf, {length: Math.min(rv, 128)});
                    send({t:'recv', fd: this.fd, len: rv, hex: data});
                }
            }
        });
        send({t:'info', m:'recv hooked'});
    }

    // ── poll map info ──────────────────────────

    var getMapID = new NativeFunction(base.add(0x12e760), 'int', []);
    var mid = getMapID();
    send({t:'info', m:'Current MapID=' + mid});

    // ── Hook jlmap_createMapForID via try/catch ──
    try {
        Interceptor.attach(base.add(0x12e778), {
            onEnter: function(args) {
                send({t:'createMap', a0: args[0], a1: args[1], a2: args[2]});
            }
        });
        send({t:'info', m:'jlmap_createMapForID hooked'});
    } catch(e) { send({t:'err', m:'createMapForID: '+e}); }

    // ── Hook jlmap_moveto ──
    try {
        Interceptor.attach(base.add(0x12d6f0), {
            onEnter: function(args) {
                send({t:'moveto', a0: args[0], a1: args[1], a2: args[2], a3: args[3]});
            }
        });
        send({t:'info', m:'jlmap_moveto hooked'});
    } catch(e) { send({t:'err', m:'moveto: '+e}); }
}

send({t:'ready'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("\n>>> READY <<<\n现在请在游戏中触发一次传送！\n", flush=True)

    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)

    elif ptype == 'err':
        print(f"[!] {payload['m']}", flush=True)

    elif ptype == 'jumpUrl':
        print(f"\n>>> jlapp_jumpUrl: {payload['a0']}", flush=True)

    elif ptype == 'createMap':
        print(f"\n>>> jlmap_createMapForID: a0={payload['a0']} a1={payload['a1']} a2={payload['a2']}", flush=True)

    elif ptype == 'moveto':
        print(f"\n>>> jlmap_moveto: a0={payload['a0']} a1={payload['a1']} a2={payload['a2']} a3={payload['a3']}", flush=True)

    elif ptype == 'send':
        print(f"\n[SEND fd={payload['fd']} len={payload['len']}]\n{payload['hex']}", flush=True)

    elif ptype == 'recv':
        print(f"\n[RECV fd={payload['fd']} len={payload['len']}]\n{payload['hex']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.", flush=True)
    session.detach()
