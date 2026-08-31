"""Minimal Frida hook test - v3 with Module instance methods"""
import sys, time, subprocess, json

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
try {
    send({t:'info', msg: 'Step1: Starting...'});

    // Check if Module global exists
    send({t:'info', msg: 'Step1b: typeof Module=' + (typeof Module)});

    // Try using Process.getModuleByName instead
    var libc = Process.getModuleByName("libc.so");
    send({t:'info', msg: 'Step2: libc=' + libc.name + ' base=' + libc.base});

    // Use module instance method to find export
    var sendAddr = libc.getExportByName("send");
    send({t:'info', msg: 'Step3: send=' + sendAddr});

    Interceptor.attach(sendAddr, {
        onEnter: function(args) {
            send({t:'hooked', fd: args[0].toInt32(), len: args[2].toInt32()});
        }
    });
    send({t:'info', msg: 'Step5: SUCCESS!'});
} catch(e) {
    send({t:'err', msg: 'ERR: ' + e.toString()});
}

send({t:'ready'});
"""

def on_msg(msg, data):
    print(f"\nRAW: {json.dumps(msg, default=str)}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("\nWaiting 15s...", flush=True)
try:
    for i in range(15):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
