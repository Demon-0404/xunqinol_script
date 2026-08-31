"""Inject teleport packet v2 - find socket via /proc/self/fd"""
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

# Check socket connections
print("Checking sockets...", flush=True)
r = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/ 2>/dev/null | head -30"],
                   capture_output=True, text=True, timeout=10)
print(r.stdout, flush=True)

# Check which fd connects to game server
r = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/net/tcp 2>/dev/null | head -20"],
                   capture_output=True, text=True, timeout=10)
print("TCP connections:", flush=True)
print(r.stdout, flush=True)

# Parse to find the fd for server connection
# Format: sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode
game_server_ip = "2BCC883F"  # 43.136.63.204 in hex (little-endian)
game_server_port = "3075"     # 30002 in hex = 0x7530

for line in r.stdout.split("\n"):
    parts = line.strip().split()
    if len(parts) >= 8:
        local = parts[1]
        remote = parts[2]
        if game_server_port in remote or game_server_ip in remote:
            print(f"Found game connection: local={local} remote={remote}", flush=True)
            inode = parts[9]
            print(f"  inode={inode}", flush=True)
            # Find fd by matching inode
            r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/ | grep {inode}"],
                               capture_output=True, text=True, timeout=10)
            print(f"  fd: {r2.stdout}", flush=True)

print("\n=== Starting Frida injection ===", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)
print("Attached!", flush=True)

JS = """
// Find game socket fd by scanning
var GAME_SERVER = "43.136.63.204";
var GAME_PORT = 30002;
var gameFd = -1;

// Hook getpeername to find the socket
var getpeernamePtr = Module.findExportByName("libc.so", "getpeername");
if (getpeernamePtr) {
    Interceptor.attach(getpeernamePtr, {
        onLeave: function(ret) {
            if (ret.toInt32() === 0 && gameFd === -1) {
                // Check if this is the game server
                var fd = this.fd;
                // Read sockaddr from args
                try {
                    var addr = this.context.r1; // sockaddr pointer
                    var family = addr.readU16();
                    if (family === 2) {
                        var port = ((addr.add(2).readU8() << 8) | addr.add(3).readU8());
                        var ip = addr.add(4).readU8() + '.' +
                                 addr.add(5).readU8() + '.' +
                                 addr.add(6).readU8() + '.' +
                                 addr.add(7).readU8();
                        if (ip === GAME_SERVER && port === GAME_PORT) {
                            gameFd = fd;
                            send({t:'found', fd: fd, ip: ip, port: port});
                        }
                    }
                } catch(e) {}
            }
        }
    });
}

// Alternative: scan fds by trying to getpeername on each
function scanFds() {
    for (var fd = 3; fd < 256; fd++) {
        try {
            var sockaddr = Memory.alloc(16);
            var addrlen = Memory.alloc(4);
            addrlen.writeU32(16);
            var ret = getpeernamePtr(fd, sockaddr, addrlen);
            if (ret.toInt32() === 0) {
                var family = sockaddr.readU16();
                if (family === 2) {
                    var port = ((sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8());
                    var ip = sockaddr.add(4).readU8() + '.' +
                             sockaddr.add(5).readU8() + '.' +
                             sockaddr.add(6).readU8() + '.' +
                             sockaddr.add(7).readU8();
                    send({t:'scan', fd: fd, ip: ip, port: port});
                    if (ip === GAME_SERVER && port === GAME_PORT) {
                        gameFd = fd;
                        send({t:'found', fd: fd});
                        return;
                    }
                }
            }
        } catch(e) {}
    }
}

// Run scan
scanFds();

// After finding, inject
if (gameFd >= 0) {
    var PLAINTEXT = [0x00, 0x8a, 0x00, 0x8b, 0x01, 0x8b, 0x02, 0x74, 0xfe, 0x74, 0xfe, 0x77, 0xfd, 0x75, 0x00];
    var K = Math.floor(Math.random() * 256);
    var pkt = Memory.alloc(16);
    pkt.writeU8(3);  // type
    for (var i = 0; i < 15; i++) {
        pkt.add(i + 1).writeU8(PLAINTEXT[i] ^ K);
    }

    send({t:'inject', hex: hexdump(pkt, {length: 16})});

    // Call send via syscall to avoid libc overhead
    var sendPtr = Module.findExportByName("libc.so", "send");
    var sendFunc = new NativeFunction(sendPtr, 'ssize_t', ['int', 'pointer', 'size_t', 'int']);
    var ret = sendFunc(gameFd, pkt, 16, 0);
    send({t:'result', ret: ret});
} else {
    send({t:'err', m:'Socket not found'});
}

send({t:'ready'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("\n>>> DONE <<<", flush=True)
    elif ptype == 'found':
        print(f">>> Game socket: fd={payload['fd']} <<<", flush=True)
    elif ptype == 'scan':
        print(f"[SCAN] fd={payload['fd']} -> {payload['ip']}:{payload['port']}", flush=True)
    elif ptype == 'inject':
        print(f"\n[INJECT] {payload['hex']}", flush=True)
    elif ptype == 'result':
        print(f"[RESULT] send() = {payload['ret']}", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['m']}", flush=True)
    else:
        print(f"[{ptype}] {str(payload)[:200]}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.", flush=True)
    session.detach()
