"""Test teleport portal capture and redirect on 天音"""
import frida, time, sys, json

# First: get game FDs
JS_DISCOVER = r'''
var fds = [];
var libc = Process.getModuleByName("libc.so");
var socket = libc.getExportByName("socket");
var connect = libc.getExportByName("connect");
var getpeername = libc.getExportByName("getpeername");

// Hook connect to find game sockets
Interceptor.attach(connect, {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.addr = args[1];
    },
    onLeave: function(ret) {
        if (ret.toInt32() === 0 && this.addr) {
            try {
                var family = this.addr.readU16();
                var port = ((this.addr.add(2).readU8() << 8) | this.addr.add(3).readU8());
                // Check for game server ports (usually high ports)
                var ip = '';
                for (var i = 4; i < 8; i++) {
                    ip += this.addr.add(i).readU8();
                    if (i < 7) ip += '.';
                }
                send({t: 'connect', fd: this.fd, ip: ip, port: port});
                if (fds.indexOf(this.fd) === -1) fds.push(this.fd);
            } catch(e) {}
        }
    }
});

// Also check existing FDs by reading /proc/self/fd
var procFd = Process.getCurrentThreadId(); // just to have some context
send({t: 'ready', msg: 'Discover mode active. Need to trigger a new connection or check existing ones.'});
'''

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict): return
    t = payload.get('t', '?')
    m = payload.get('msg', '')
    if t == 'ready': print(f'[*] {m}')
    elif t == 'connect': print(f'  CONNECT fd={payload["fd"]} {payload["ip"]}:{payload["port"]}')
    else: print(f'  [{t}] {m}')
    sys.stdout.flush()

# First, discover game FDs by reading /proc/self/fd
JS_FIND_FD = r'''
// Find game sockets by reading /proc/self/fd
var fds = [];
try {
    var fdDir = new File('/proc/self/fd', 'r');
    send({t: 'log', msg: 'Cannot use File API, trying alternative'});
} catch(e) {}

// Use readlink via native calls to scan /proc/self/fd
var readlinkPtr = Module.getExportByName('libc.so', 'readlink');
var readlink = new NativeFunction(readlinkPtr, 'int', ['pointer', 'pointer', 'int']);

for (var fd = 30; fd < 200; fd++) {
    var path = Memory.alloc(256);
    var fdPath = Memory.allocUtf8String('/proc/self/fd/' + fd);
    var ret = readlink(fdPath, path, 255);
    if (ret > 0) {
        var link = path.readUtf8String(ret);
        if (link.indexOf('socket') !== -1) {
            // Check if it's a connected socket by trying getpeername
            // For now just list all sockets
            fds.push({fd: fd, link: link});
        }
    }
}

send({t: 'log', msg: 'Found ' + fds.length + ' sockets'});
for (var i = 0; i < fds.length; i++) {
    send({t: 'log', msg: '  fd=' + fds[i].fd + ' -> ' + fds[i].link});
}

send({t: 'ready', msg: 'done'});
'''

print("=== Finding game sockets ===")
dev = frida.get_device_manager().add_remote_device('127.0.0.1:27056')
session = dev.attach(2793)
script = session.create_script(JS_FIND_FD)
script.on('message', on_msg)
script.load()
time.sleep(5)

# Now try to detect which FDs are the game's TCP connections
# by sending a test packet and watching
JS_DETECT = r'''
var libc = Process.getModuleByName("libc.so");
var sendPtr = libc.getExportByName("send");

var gameFds = [];

Interceptor.attach(sendPtr, {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var len = args[2].toInt32();
        if (len > 10 && len < 100) {
            // Check first byte - game packets start with type byte
            var b0 = args[1].readU8();
            if (b0 >= 1 && b0 <= 10) {
                if (gameFds.indexOf(fd) === -1) {
                    gameFds.push(fd);
                    send({t: 'game_fd', fd: fd, len: len, type: b0});
                }
            }
        }
    }
});

send({t: 'log', msg: 'Monitoring send() for game packets...'});
send({t: 'ready', msg: 'Send monitor active. Move character in game to trigger sends.'});
'''

script2 = session.create_script(JS_DETECT)
script2.on('message', on_msg)
script2.load()

print("\n=== Monitoring for game FDs (move character in game) ===")
print("Waiting 10 seconds for game packets...")
time.sleep(10)

# Now read back the detected game FDs
JS_GET_FDS = r'''
send({t: 'game_fds', fds: JSON.stringify(gameFds)});
'''
try:
    script3 = session.create_script(JS_GET_FDS)
    script3.on('message', on_msg)
    script3.load()
    time.sleep(2)
except Exception as e:
    print(f"Error: {e}")

session.detach()
print("Done")
