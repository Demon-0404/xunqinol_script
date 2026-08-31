"""Monitor send() calls and inject on first 03 packet"""
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
var GAME_FD = 63;
var PLAINTEXT = [0x00, 0x8a, 0x00, 0x8b, 0x01, 0x8b, 0x02, 0x74, 0xfe, 0x74, 0xfe, 0x77, 0xfd, 0x75, 0x00];
var replaced = false;
var sendCount = 0;

var sendPtr = Module.findExportByName("libc.so", "send");
Interceptor.attach(sendPtr, {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var len = args[2].toInt32();
        sendCount++;

        if (fd === GAME_FD && len > 0) {
            var firstByte = args[1].readU8();
            send({t:'send', fd: fd, len: len, first: firstByte, count: sendCount});

            // Replace first 03 packet with teleport
            if (!replaced && len >= 16 && firstByte === 3) {
                var K = Math.floor(Math.random() * 256);
                args[1].writeU8(3);
                for (var i = 0; i < 15; i++) {
                    args[1].add(i + 1).writeU8(PLAINTEXT[i] ^ K);
                }
                args[2] = ptr(16);
                replaced = true;
                send({t:'replaced', key: K});
            }
        }
    }
});

send({t:'ready', msg: 'Monitoring send() on fd=63...'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        print(f"[RAW] {msg}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"\n[*] {payload['msg']}", flush=True)
    elif ptype == 'send':
        print(f"  [SEND] fd={payload['fd']} len={payload['len']} first=0x{payload['first']:02x} (#{payload['count']})", flush=True)
    elif ptype == 'replaced':
        print(f"\n>>> 已替换为传送包! key=0x{payload['key']:02x} <<<", flush=True)
    elif ptype == 'error':
        print(f"[!] {payload['msg']}", flush=True)
    else:
        print(f"[{ptype}] {payload}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("等待 send() 调用... (Ctrl+C 停止)", flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n停止.", flush=True)
    session.detach()
