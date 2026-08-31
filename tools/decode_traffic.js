// Decode game traffic to understand position/manipulation
var libc = Process.getModuleByName('libc.so');
var GAME_FDS = [59];
var sessionKey = 0;
var sendLog = [];
var recvLog = [];

function isGameFd(fd) {
    return GAME_FDS.indexOf(fd) !== -1;
}

// Recv: auto-detect key and log all recv types
Interceptor.attach(libc.getExportByName('recv'), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.doProcess = isGameFd(this.fd);
    },
    onLeave: function(ret) {
        if (!this.doProcess) return;
        var realLen = ret.toInt32();
        if (realLen <= 0) return;

        // Auto-detect key from repeated byte patterns (bytes 1-3 identical)
        if (sessionKey === 0 && realLen >= 4) {
            var b0 = this.buf.readU8();
            var b1 = this.buf.add(1).readU8();
            var b2 = this.buf.add(2).readU8();
            var b3 = this.buf.add(3).readU8();
            if (b1 === b2 && b2 === b3) {
                var tryKey = b0 ^ 0x02;
                if (tryKey > 0) {
                    sessionKey = tryKey;
                    send({t: 'key', key: sessionKey});
                }
            }
        }

        if (sessionKey > 0) {
            var ptype = this.buf.readU8() ^ sessionKey;
            // Log first 20 bytes of plain text for analysis
            var plain = '';
            var dumpLen = Math.min(realLen, 64);
            for (var i = 0; i < dumpLen; i++) {
                plain += ('0' + (this.buf.add(i).readU8() ^ sessionKey).toString(16)).slice(-2);
            }

            if (recvLog.length < 30) {
                recvLog.push({type: ptype, len: realLen, plain: plain});
            }

            // Only show interesting ones
            if (ptype === 0x03 && realLen > 100) {
                send({t: 'recv_map', len: realLen, plain: plain});
            } else if (ptype === 0x05) {
                send({t: 'recv_move', len: realLen, plain: plain, msg: 'Movement data recv!'});
            }
        }
    }
});

// Send: log all sends with plain text
Interceptor.attach(libc.getExportByName('send'), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (!isGameFd(fd)) return;
        var slen = args[2].toInt32();
        if (slen >= 10 && sessionKey > 0) {
            var ptype = args[1].readU8() ^ sessionKey;
            var plain = '';
            var dumpLen = Math.min(slen, 64);
            for (var i = 0; i < dumpLen; i++) {
                plain += ('0' + (args[1].add(i).readU8() ^ sessionKey).toString(16)).slice(-2);
            }

            if (sendLog.length < 30) {
                sendLog.push({type: ptype, len: slen, plain: plain});
            }

            // Portal detection - need to be extra careful here
            if (slen === 29 && ptype === 0x03) {
                send({t: 'portal_send', len: slen, plain: plain, msg: 'PORTAL SEND DETECTED!'});
            } else if (slen === 30 && ptype === 0x05) {
                send({t: 'move_send', len: slen, plain: plain, msg: 'Movement send'});
            } else if (slen > 10 && slen !== 17) {
                send({t: 'send_other', len: slen, type: ptype, plain: plain});
            }
        }
    }
});

// Log summary every 15 seconds
var logInterval = setInterval(function() {
    send({t: 'log_summary', key: sessionKey, sends: sendLog.length, recvs: recvLog.length,
        sendTypes: JSON.stringify(sendLog.map(function(s) { return {t: s.type, l: s.len}; })),
        recvTypes: JSON.stringify(recvLog.map(function(r) { return {t: r.type, l: r.len}; }))
    });
    // Show last 5 sends and recvs
    var showSends = sendLog.slice(-5);
    for (var si = 0; si < showSends.length; si++) {
        send({t: 'send_detail', type: showSends[si].type, len: showSends[si].len, plain: showSends[si].plain});
    }
    var showRecvs = recvLog.slice(-5);
    for (var ri = 0; ri < showRecvs.length; ri++) {
        send({t: 'recv_detail', type: showRecvs[ri].type, len: showRecvs[ri].len, plain: showRecvs[ri].plain});
    }
}, 15000);

send({t: 'ready', msg: 'Traffic decoder active. Move around in game to generate movement data.'});
