"""Safe hook: only jlapp_jumpUrl + network send/recv"""
import sys, os, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16544"

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

    // Only hook the safe function: jlapp_jumpUrl
    try {
        Interceptor.attach(base.add(0x1375d0), {
            onEnter: function(args) {
                var url = args[0].readCString();
                send({t:'jumpUrl', url: url || '(null)'});
            }
        });
        send({t:'info', m:'jlapp_jumpUrl hooked OK'});
    } catch(e) {
        send({t:'err', m:'jumpUrl hook failed: '+e});
    }

    // Hook xqj_setJumpUrlCall (registers callback)
    try {
        Interceptor.attach(base.add(0x13efd4), {
            onEnter: function(args) {
                send({t:'setJumpCall', a0: args[0], a1: args[1]});
            }
        });
        send({t:'info', m:'xqj_setJumpUrlCall hooked OK'});
    } catch(e) {
        send({t:'err', m:'setJumpUrlCall: '+e});
    }

    // Read g_jumpUrlCall pointer (global callback)
    try {
        var ptr = base.add(0x464a18).readPointer();
        send({t:'info', m:'g_jumpUrlCall=' + ptr});
    } catch(e) {
        send({t:'err', m:'g_jumpUrlCall read: '+e});
    }
}

send({t:'ready'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("\n>>> READY <<<\n现在在游戏中做一次跨城传送！\n", flush=True)

    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)

    elif ptype == 'err':
        print(f"[!] {payload['m']}", flush=True)

    elif ptype == 'jumpUrl':
        print(f"\n>>> jlapp_jumpUrl CALLED! <<<")
        print(f"    URL: {payload['url']}", flush=True)

    elif ptype == 'setJumpCall':
        print(f"\n>>> xqj_setJumpUrlCall(a0={payload['a0']}, a1={payload['a1']})", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.", flush=True)
    session.detach()
