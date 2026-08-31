"""Final attempt: active call jlmap_getMapID + try calling jlapp_jumpUrl"""
import sys, os, time, subprocess
os.environ['PYTHONUNBUFFERED'] = '1'

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"

r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"],
                   capture_output=True, text=True, timeout=15)
pid = None
for line in r.stdout.split("\n"):
    if "proj.xqj" in line:
        parts = line.split()
        if len(parts) >= 2: pid = int(parts[1]); break
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
if (!base) { send({t:'err',m:'no base'}); } else {
    send({t:'info',m:'Base: '+base});

    // Try to call jlmap_getMapID (no args, returns int)
    var getMapID = new NativeFunction(base.add(0x12e760), 'int', []);
    var mid = getMapID();
    send({t:'map', id: mid});

    // Try calling jlmap_getMapRow (no args, returns int)
    var getMapRow = new NativeFunction(base.add(0x12c4d4), 'int', []);
    var row = getMapRow();
    send({t:'info',m:'MapRow='+row});

    var getMapCol = new NativeFunction(base.add(0x12c4bc), 'int', []);
    var col = getMapCol();
    send({t:'info',m:'MapCol='+col});

    // Try jlmap_getMapIsSafe (returns int/bool)
    var getSafe = new NativeFunction(base.add(0x12c3f0), 'int', []);
    var safe = getSafe();
    send({t:'info',m:'MapIsSafe='+safe});

    send({t:'info',m:'Active calls worked! No hooks - poll getMapID after teleport.'});
}
send({t:'ready'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict): return
    ptype = payload.get('t', '?')
    if ptype == 'map':
        print(f"\n>>> Current MapID: {payload['id']} <<<", flush=True)
    elif ptype == 'CM':
        print(f"\n>>> CREATE_MAP #{payload['hit']} <<<\n  a0={payload['a0']}\n  a1={payload['a1']}\n  a2={payload['a2']}", flush=True)
    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)
    elif ptype == 'ready':
        print("\n>>> READY <<<\nCurrent map info above. Now trigger a teleport!\n", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    while True: time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.", flush=True)
    session.detach()
