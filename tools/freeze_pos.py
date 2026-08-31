# -*- coding: utf-8 -*-
"""Freeze position in movement packets, test if server accepts it"""
import sys, time, subprocess, os

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

if game_fd < 0:
    print("Game not connected!", flush=True)
    sys.exit(1)

print(f"PID={pid} fd={game_fd}", flush=True)
subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

import frida

JS2 = """
var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var frozenPayload = null;
var frozen = false;
var capturedHex = '';

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD) return;
        if (buf.readU8() !== 3) return;
        var key = buf.add(1).readU8();

        // Capture first movement packet
        if (len === 30 && !capturedHex) {
            var payloadHex = '';
            for (var i = 0; i < 28; i++) {
                payloadHex += ('0' + (buf.add(i + 2).readU8() ^ key).toString(16)).slice(-2);
            }
            capturedHex = payloadHex;
            // Build frozenPayload array
            frozenPayload = [];
            for (var i = 0; i < payloadHex.length; i += 2) {
                frozenPayload.push(parseInt(payloadHex.substring(i, i + 2), 16));
            }
            send({t: 'captured', hex: capturedHex});
        }

        // If frozen, replace movement
        if (len === 30 && frozen && frozenPayload) {
            for (var i = 0; i < 28; i++) {
                buf.add(i + 2).writeU8(frozenPayload[i] ^ key);
            }
        }
    }
});

rpc.exports = {
    freeze: function() { frozen = true; send({t: 'status', msg: 'FROZEN'}); return 'OK'; },
    unfreeze: function() { frozen = false; send({t: 'status', msg: 'UNFROZEN'}); return 'OK'; },
    hasCapture: function() { return capturedHex !== ''; }
};

send({t: 'ready', msg: 'Position freeze ready.'});
""" % game_fd

dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

captured = False

def on_msg(msg, data):
    global captured
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"[*] {payload['msg']}", flush=True)
    elif ptype == 'captured':
        captured = True
        print(f"\n[CAPTURE] payload: {payload['hex']}", flush=True)
    elif ptype == 'status':
        print(f"[*] {payload['msg']}", flush=True)

script = session.create_script(JS2)
script.on('message', on_msg)
script.load()

print("[*] 先走几步让脚本捕获位置包...", flush=True)
for i in range(30):
    time.sleep(1)
    if captured:
        break

if not captured:
    print("[!] 未捕获到，请走动一下", flush=True)
    time.sleep(10)

if script.exports_sync.hasCapture():
    print("\n[*] 冻结位置中... 现在你再走动，看会不会掉线！", flush=True)
    script.exports_sync.freeze()
    time.sleep(20)
    script.exports_sync.unfreeze()
    print("[*] 已解除冻结", flush=True)
else:
    print("[!] 仍未捕获", flush=True)

session.detach()
print("Done.", flush=True)
