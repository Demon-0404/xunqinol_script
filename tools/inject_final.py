"""Inject teleport packet via known fd=63 - with error handling"""
import sys, os, time, subprocess, random

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

# Screenshot before
subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
               stdout=open("E:/DATA/xunqinol_script/logs/_before_inject.png", "wb"), timeout=10)
print("Before screenshot saved", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)
print("Attached!", flush=True)

JS = """
var GAME_FD = 63;
var PLAINTEXT = [0x00, 0x8a, 0x00, 0x8b, 0x01, 0x8b, 0x02, 0x74, 0xfe, 0x74, 0xfe, 0x77, 0xfd, 0x75, 0x00];

var K = Math.floor(Math.random() * 256);
var pkt = Memory.alloc(16);
pkt.writeU8(3);
for (var i = 0; i < 15; i++) {
    pkt.add(i + 1).writeU8(PLAINTEXT[i] ^ K);
}
send({t:'packet', hex: hexdump(pkt, {length: 16}), key: K});

// Method 1: Hook approach - replace next outgoing packet
var sendPtr = Module.findExportByName("libc.so", "send");
var hooked = false;

Interceptor.attach(sendPtr, {
    onEnter: function(args) {
        if (hooked) return;
        var fd = args[0].toInt32();
        var len = args[2].toInt32();
        // Only replace packets to game server (fd 63) that are small (likely game packets)
        if (fd === GAME_FD && len >= 16 && len <= 30) {
            var typeByte = args[1].readU8();
            if (typeByte === 3) {
                // Replace with our teleport packet
                var newK = K;
                args[1].writeU8(3);
                for (var i = 0; i < 15; i++) {
                    args[1].add(i + 1).writeU8(PLAINTEXT[i] ^ newK);
                }
                args[2] = ptr(16);
                hooked = true;
                send({t:'replaced', msg: 'Replaced a position packet with teleport packet'});
            }
        }
    }
});

send({t:'ready', msg: 'Send hook active. Move in game to trigger packet replacement...'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        print(f"[RAW] {msg}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'packet':
        print(f"\n>>> 传送包已就绪 (key=0x{payload['key']:02x}) <<<", flush=True)
        print(f"{payload['hex']}", flush=True)
    elif ptype == 'ready':
        print(f"\n[*] {payload['msg']}", flush=True)
    elif ptype == 'replaced':
        print(f"\n>>> {payload['msg']} <<<", flush=True)
    elif ptype == 'error':
        print(f"[错误] {payload['msg']}", flush=True)
    elif ptype == 'done':
        print("脚本完成", flush=True)
    else:
        print(f"[{ptype}] {payload}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("\n等待游戏移动触发替换... (Ctrl+C 停止)", flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
