// Monitor game FDs and capture portal packets
var GAME_FDS = [59]; // Main game connection

var libc = Process.getModuleByName("libc.so");
var sessionKey = 0;
var capturedPortalHex = '';

function isGameFd(fd) {
    return GAME_FDS.indexOf(fd) !== -1;
}

// Hook recv to auto-detect key and capture big map data
Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.doProcess = isGameFd(this.fd);
    },
    onLeave: function(ret) {
        if (!this.doProcess) return;
        var realLen = ret.toInt32();
        if (realLen <= 0) {
            send({t: 'recv_neg', len: realLen, msg: 'recv error/disconnect'});
        }

        // Auto-detect session key from first packet (type byte = 0x03)
        if (sessionKey === 0 && realLen >= 4) {
            var tryKey = this.buf.readU8() ^ 0x03;
            if ((this.buf.add(1).readU8() ^ tryKey) === 0 &&
                (this.buf.add(2).readU8() ^ tryKey) === 0 &&
                (this.buf.add(3).readU8() ^ tryKey) === 0) {
                sessionKey = tryKey;
                send({t: 'key', key: sessionKey, msg: 'Session key detected!'});
            }
        }

        // Log every recv with type info
        if (sessionKey > 0 && realLen > 0) {
            var ptype = this.buf.readU8() ^ sessionKey;
            var hex = '';
            var dumpLen = Math.min(realLen, 60);
            for (var i = 0; i < dumpLen; i++) {
                hex += ('0' + this.buf.add(i).readU8().toString(16)).slice(-2);
            }
            send({t: 'recv', len: realLen, type: ptype, hex: hex});
        }
    }
});

// Hook send to detect portal packets
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (!isGameFd(fd)) return;

        var slen = args[2].toInt32();
        if (slen > 10) {
            var hex = '';
            var dumpLen = Math.min(slen, 60);
            for (var i = 0; i < dumpLen; i++) {
                hex += ('0' + args[1].add(i).readU8().toString(16)).slice(-2);
            }

            var ptype = '?';
            if (sessionKey > 0) {
                ptype = (args[1].readU8() ^ sessionKey).toString(16);
            }

            send({t: 'send', len: slen, type_plain: ptype, hex: hex});

            // Capture 29-byte portal packets (type 0x03 plain)
            if (slen === 29 && sessionKey > 0 && (args[1].readU8() ^ sessionKey) === 0x03) {
                // Decrypt and save the full plain text
                var plain = '';
                for (var pi = 0; pi < slen; pi++) {
                    plain += ('0' + (args[1].add(pi).readU8() ^ sessionKey).toString(16)).slice(-2);
                }
                capturedPortalHex = plain;
                send({t: 'portal_captured', plain: plain, msg: 'Portal packet captured!'});
            }
        }
    }
});

// Prevent disconnect
var closeBlocked = 0;
Interceptor.attach(libc.getExportByName("close"), {
    onEnter: function(args) {
        if (isGameFd(args[0].toInt32())) {
            closeBlocked++;
            this.blockClose = true;
            this.blockedFd = args[0].toInt32();
            send({t: 'close_warn', fd: this.blockedFd, total: closeBlocked, msg: 'close() on game fd BLOCKED!'});
        }
    },
    onLeave: function(ret) {
        if (this.blockClose) {
            ret.replace(0);
            this.blockClose = false;
        }
    }
});

Interceptor.attach(libc.getExportByName("shutdown"), {
    onEnter: function(args) {
        if (isGameFd(args[0].toInt32())) {
            this.blockShutdown = true;
            send({t: 'shutdown_warn', fd: args[0].toInt32(), msg: 'shutdown() on game fd BLOCKED!'});
        }
    },
    onLeave: function(ret) {
        if (this.blockShutdown) {
            ret.replace(0);
            this.blockShutdown = false;
        }
    }
});

rpc.exports = {
    getKey: function() { return sessionKey; },
    getPortal: function() { return capturedPortalHex; },
    clear: function() { capturedPortalHex = ''; return 'OK'; },
    setGameFds: function(fdsStr) {
        var parts = fdsStr.split(',');
        GAME_FDS = [];
        for (var i = 0; i < parts.length; i++) {
            GAME_FDS.push(parseInt(parts[i]));
        }
        return 'Fds set: ' + GAME_FDS.join(',');
    }
};

send({t: 'ready', msg: 'Monitor active. Walk through a portal!', fds: GAME_FDS.join(',')});
