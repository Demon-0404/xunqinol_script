"""Hook SSL_write() to capture and inject teleport packets"""
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
var PLAINTEXT = [0x00, 0x8a, 0x00, 0x8b, 0x01, 0x8b, 0x02, 0x74, 0xfe, 0x74, 0xfe, 0x77, 0xfd, 0x75, 0x00];
var replaced = false;
var sslWriteCount = 0;

// Hook SSL_write from libssl.so
var sslWritePtr = Module.findExportByName("libssl.so", "SSL_write");
if (!sslWritePtr) {
    // Try alternative names
    sslWritePtr = Module.findExportByName("libssl.so", "SSL_write_ex");
}
if (!sslWritePtr) {
    // Fallback: enumerate libssl.so exports
    var mod = Process.findModuleByName("libssl.so");
    if (mod) {
        mod.enumerateExports().forEach(function(exp) {
            if (exp.name.indexOf("SSL_write") !== -1) {
                sslWritePtr = exp.address;
                send({t:'info', m: 'Found export: ' + exp.name + ' at ' + exp.address});
            }
        });
    }
}

if (!sslWritePtr) {
    send({t:'err', msg: 'SSL_write not found in libssl.so'});
} else {
    send({t:'info', m: 'SSL_write at ' + sslWritePtr});

    // Also hook SSL_read to confirm game uses SSL
    var sslReadPtr = Module.findExportByName("libssl.so", "SSL_read");
    if (sslReadPtr) {
        Interceptor.attach(sslReadPtr, {
            onEnter: function(args) {
                var ssl = args[0];
                var buf = args[1];
                var num = args[2].toInt32();
                send({t:'ssl_read', num: num});
            },
            onLeave: function(ret) {
                var n = ret.toInt32();
                if (n > 0 && n < 200) {
                    send({t:'ssl_read_data', len: n, hex: hexdump(this.context.r1, {length: Math.min(n, 64)})});
                }
            }
        });
    }

    Interceptor.attach(sslWritePtr, {
        onEnter: function(args) {
            sslWriteCount++;
            var ssl = args[0];
            var buf = args[1];
            var num = args[2].toInt32();

            if (num > 0 && num <= 64) {
                var firstByte = buf.readU8();
                var hex = hexdump(buf, {length: Math.min(num, 32)});
                send({t:'ssl_write', len: num, first: firstByte, count: sslWriteCount, hex: hex});

                // Replace first 03 packet with teleport
                if (!replaced && num >= 16 && firstByte === 3) {
                    var K = Math.floor(Math.random() * 256);
                    buf.writeU8(3);
                    for (var i = 0; i < 15; i++) {
                        buf.add(i + 1).writeU8(PLAINTEXT[i] ^ K);
                    }
                    // Note: can't change num via args[2] — SSL_write uses num from stack
                    // Instead, we minimize the payload and the server should handle it
                    send({t:'replaced', key: K, original_len: num});
                }
            } else if (num > 64) {
                send({t:'ssl_write_big', len: num, first: buf.readU8(), count: sslWriteCount});
            }
        }
    });
}

send({t:'ready', msg: 'Hooking SSL_write... move in game to trigger'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        print(f"[RAW] {msg}", flush=True)
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print(f"\n[*] {payload['msg']}", flush=True)
    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)
    elif ptype == 'ssl_write':
        print(f"\n  [SSL_WRITE] len={payload['len']} first=0x{payload['first']:02x} (#{payload['count']})", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'ssl_write_big':
        print(f"\n  [SSL_WRITE_BIG] len={payload['len']} first=0x{payload['first']:02x} (#{payload['count']})", flush=True)
    elif ptype == 'ssl_read':
        print(f"  [SSL_READ] requested={payload['num']}", flush=True)
    elif ptype == 'ssl_read_data':
        print(f"  [SSL_READ_DATA] len={payload['len']}", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'replaced':
        print(f"\n>>> 已替换为传送包! key=0x{payload['key']:02x} (原始长度={payload['original_len']}) <<<", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['msg']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("等待 SSL_write() 调用... (Ctrl+C 停止)", flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n停止.", flush=True)
    session.detach()
