// Find game TCP socket FDs
var libc = Process.getModuleByName("libc.so");
var readlink = new NativeFunction(Module.getExportByName('libc.so', 'readlink'), 'int', ['pointer', 'pointer', 'int']);
var getsockname = new NativeFunction(Module.getExportByName('libc.so', 'getsockname'), 'int', ['int', 'pointer', 'pointer']);
var getpeername = new NativeFunction(Module.getExportByName('libc.so', 'getpeername'), 'int', ['int', 'pointer', 'pointer']);

var gameFds = [];

for (var fd = 3; fd < 256; fd++) {
    var path = Memory.alloc(256);
    var fdPath = Memory.allocUtf8String('/proc/self/fd/' + fd);
    var ret = readlink(fdPath, path, 255);
    if (ret > 0) {
        var link = path.readUtf8String(ret);
        if (link.indexOf('socket') !== -1) {
            // Try getpeername to check if it's connected to a server
            var addr = Memory.alloc(128);
            var addrLen = Memory.alloc(4);
            addrLen.writeU32(128);

            var peerRet = getpeername(fd, addr, addrLen);
            if (peerRet === 0) {
                var family = addr.readU16();
                var port = ((addr.add(2).readU8() << 8) | addr.add(3).readU8());
                // Read IP (bytes 4-7 for IPv4)
                var ip = addr.add(4).readU8() + '.' + addr.add(5).readU8() + '.' +
                         addr.add(6).readU8() + '.' + addr.add(7).readU8();

                // Also check local port from getsockname
                var laddr = Memory.alloc(128);
                var laddrLen = Memory.alloc(4);
                laddrLen.writeU32(128);
                var sockRet = getsockname(fd, laddr, laddrLen);
                var lport = 0;
                if (sockRet === 0) {
                    lport = ((laddr.add(2).readU8() << 8) | laddr.add(3).readU8());
                }

                send({t: 'socket', fd: fd, peer: ip + ':' + port, local_port: lport});

                // Game servers usually have high ports or specific IPs
                // Mark as game FD if port > 10000 or it's an external IP
                if (port > 5000 || ip.indexOf('10.') === 0 || ip.indexOf('192.') === 0) {
                    gameFds.push(fd);
                    send({t: 'game_fd', fd: fd});
                }
            }
        }
    }
}

send({t: 'log', msg: 'Total game FDs found: ' + gameFds.length + ' -> [' + gameFds.join(',') + ']'});
send({t: 'ready', msg: 'done', fds: gameFds.join(',')});
