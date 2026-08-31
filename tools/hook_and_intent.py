"""Hook jlapp_jumpUrl + test URL intents via ADB"""
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
    send({t:'err', m:'no base'});
} else {
    send({t:'info', m:'Base='+base});

    // Hook jlapp_jumpUrl
    Interceptor.attach(base.add(0x1375d0), {
        onEnter: function(args) {
            send({t:'jumpUrl', url: args[0].readCString() || '(null)'});
        }
    });
    send({t:'info', m:'jlapp_jumpUrl hooked'});

    // Hook AppDelegate::jumpUrl (thunk @ 0xda099)
    // Don't hook - just try to READ its instructions to find where it jumps
    var thunk = base.add(0xda099);
    send({t:'info', m:'thunk bytes: ' + hexdump(thunk, {length: 12})});
}

send({t:'ready'});
"""

script = None

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("\n>>> READY <<<", flush=True)
        # Send intents via ADB
        urls = [
            "xqj://map?name=北冥城",
            "xqj://teleport?city=北冥城",
            "xqj://jump?map_id=1",
            "xqj://open?scene=beiming",
            "xqj://main",
        ]
        for url in urls:
            print(f"\n[ADB] Sending intent: {url}", flush=True)
            subprocess.run(
                [ADB, "-s", SERIAL, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url],
                capture_output=True, timeout=10)
            time.sleep(1)

        print("\nAll intents sent. Check game screen!", flush=True)

    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['m']}", flush=True)
    elif ptype == 'jumpUrl':
        print(f"\n>>> jlapp_jumpUrl FIRED! URL: {payload['url']} <<<", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.", flush=True)
    session.detach()
