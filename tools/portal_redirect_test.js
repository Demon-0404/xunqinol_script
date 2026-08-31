// Portal redirect test script for 天音
// Game connection: fd 59 (10.0.2.15:37746 -> 43.136.63.204:30002)
var GAME_FDS = [59];
var libc = Process.getModuleByName("libc.so");

var sessionKey = 0;
var captureMode = false;
var capturedRawHex = '';
var injectArmed = false;
var injectReady = false;
var injectPlainHex = '';
var injectEncHex = '';
var injectOffset = 0;
var silenceMode = false;
var silenceUntil = 0;
var silenceBlocked = 0;
var lastRecvTime = 0;
var lastFakeRecvTime = 0;
var aliveTimer = null;
var fakeRecvQueue = [];
var portalRedirectMode = false;
var portalRedirectPlain = '';
var byteRedirectArmed = false;
var byteRedirectKey = '';
var byteRedirectStart = 24;
var recvFilterMode = false;

function isGameFd(fd) {
    return GAME_FDS.indexOf(fd) !== -1;
}

// Recv hook
Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.bufSize = args[2].toInt32();
        this.doProcess = isGameFd(this.fd);
    },
    onLeave: function(ret) {
        if (!this.doProcess) return;
        var realLen = ret.toInt32();

        // Inject fake recv data (heartbeat responses during silence)
        if (silenceMode && fakeRecvQueue.length > 0 && sessionKey > 0) {
            var fakeHex = fakeRecvQueue.shift();
            var fakeLen = fakeHex.length / 2;
            for (var fi = 0; fi < fakeLen; fi++) {
                var fb = parseInt(fakeHex.substring(fi * 2, fi * 2 + 2), 16);
                this.buf.add(fi).writeU8(fb ^ sessionKey);
            }
            ret.replace(fakeLen);
            send({t: 'fake_recv', len: fakeLen});
            return;
        }

        // Silence mode: block server FIN
        if (silenceMode && realLen === 0) {
            var now = Date.now();
            if (now - lastFakeRecvTime > 10000 && sessionKey > 0) {
                lastFakeRecvTime = now;
                var fakeResp = '010000000100000001000000046029c001';
                var frLen = fakeResp.length / 2;
                for (var fi2 = 0; fi2 < frLen; fi2++) {
                    var fb2 = parseInt(fakeResp.substring(fi2 * 2, fi2 * 2 + 2), 16);
                    this.buf.add(fi2).writeU8(fb2 ^ sessionKey);
                }
                ret.replace(frLen);
                send({t: 'recv_blocked', msg: 'Blocked FIN, injected fake HB'});
            } else {
                ret.replace(-1);
            }
            return;
        }

        if (silenceMode && realLen < 0) {
            ret.replace(-1);
            var _errnoPtr = libc.getExportByName("__errno");
            if (_errnoPtr) {
                var errnoFn = new NativeFunction(_errnoPtr, 'pointer', []);
                errnoFn().writeInt(11); // EAGAIN
            }
            return;
        }

        // Recv filter mode: block all recv data
        if (recvFilterMode) {
            if (realLen === 0) {
                var now3 = Date.now();
                if (now3 - lastFakeRecvTime > 5000 && sessionKey > 0) {
                    lastFakeRecvTime = now3;
                    var fakeResp3 = '010000000100000001000000046029c001';
                    var fr3Len = fakeResp3.length / 2;
                    for (var fi3 = 0; fi3 < fr3Len; fi3++) {
                        var fb3 = parseInt(fakeResp3.substring(fi3 * 2, fi3 * 2 + 2), 16);
                        this.buf.add(fi3).writeU8(fb3 ^ sessionKey);
                    }
                    ret.replace(fr3Len);
                    send({t: 'recv_filter_hb', msg: 'Filter mode: injected fake HB'});
                } else {
                    ret.replace(-1);
                }
                return;
            }
            if (realLen < 0) {
                ret.replace(-1);
                return;
            }
            // Block data
            ret.replace(-1);
            var _errnoPtr2 = libc.getExportByName("__errno");
            if (_errnoPtr2) {
                var errnoFn2 = new NativeFunction(_errnoPtr2, 'pointer', []);
                errnoFn2().writeInt(11);
            }
            return;
        }

        if (realLen <= 0) return;

        // Auto-detect session key from first recv packet (any type)
        if (sessionKey === 0 && realLen >= 4) {
            // Try to detect key by checking if bytes 1-3 XOR with key give 0
            var b0 = this.buf.readU8();
            var b1 = this.buf.add(1).readU8();
            var b2 = this.buf.add(2).readU8();
            var b3 = this.buf.add(3).readU8();

            // Most game packets have 0x00 in bytes 1-3
            if (b1 === b2 && b2 === b3) {
                // Possible key: b0 ^ type_guess
                // Type 2 is most common (position update)
                var tryKey = b0 ^ 0x02;
                if (tryKey > 0) {
                    sessionKey = tryKey;
                    send({t: 'key', key: sessionKey, msg: 'Key detected (type 2 pattern)'});
                }
            }
            // Also try type 3 pattern
            if (sessionKey === 0) {
                var tryKey2 = b0 ^ 0x03;
                if (tryKey2 > 0 && (b1 ^ tryKey2) === 0 && (b2 ^ tryKey2) === 0 && (b3 ^ tryKey2) === 0) {
                    sessionKey = tryKey2;
                    send({t: 'key', key: sessionKey, msg: 'Key detected (type 3 pattern)'});
                }
            }
        }

        // Log recv
        if (sessionKey > 0) {
            var ptype = this.buf.readU8() ^ sessionKey;
            if (ptype === 0x03) {
                send({t: 'recv_type3', len: realLen, msg: 'Map/entity data recv'});
            }
        }

        // Capture mode
        if (captureMode) {
            for (var ci = 0; ci < realLen; ci++) {
                capturedRawHex += ('0' + this.buf.add(ci).readU8().toString(16)).slice(-2);
            }
        }

        // Injection gating
        if (injectArmed && injectPlainHex && realLen > 0) {
            if (!injectReady) {
                // Wait for portal send detection (set by send hook)
                return;
            }
            if (sessionKey === 0) {
                send({t: 'inj_wait', msg: 'Waiting for key'});
                return;
            }
            if (!injectEncHex && realLen < 50) {
                send({t: 'inj_wait', msg: 'Small recv, waiting for map data'});
                return;
            }
            if (!injectEncHex) {
                for (var ii = 0; ii < injectPlainHex.length; ii += 2) {
                    var ib = parseInt(injectPlainHex.substring(ii, ii + 2), 16);
                    injectEncHex += ('0' + (ib ^ sessionKey).toString(16)).slice(-2);
                }
            }
            var totalLen = injectEncHex.length / 2;
            var remaining = totalLen - injectOffset;
            if (remaining > 0) {
                var chunk = Math.min(remaining, realLen);
                for (var ci2 = 0; ci2 < chunk; ci2++) {
                    var ib2 = parseInt(injectEncHex.substring((injectOffset + ci2) * 2, (injectOffset + ci2) * 2 + 2), 16);
                    this.buf.add(ci2).writeU8(ib2);
                }
                injectOffset += chunk;
                ret.replace(realLen);
                send({t: 'inj_chunk', wrote: chunk, offset: injectOffset, total: totalLen});
            }
            if (injectOffset >= totalLen) {
                injectArmed = false;
                injectReady = false;
                recvFilterMode = true;
                send({t: 'inj_done', msg: 'Injection done, recv filter ON'});
            }
        }
    }
});

// Send hook
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (!isGameFd(fd)) return;
        var slen = args[2].toInt32();

        // Silence mode: block all sends except heartbeats
        if (silenceMode) {
            var now = Date.now();
            if (now >= silenceUntil) {
                silenceMode = false;
                if (aliveTimer) { clearInterval(aliveTimer); aliveTimer = null; }
                send({t: 'silence_off', msg: 'Silence expired'});
            } else {
                silenceBlocked++;
                this.silenceOrigLen = slen;
                this.doBlock = true;
                args[2] = ptr(0);
                if (slen === 17 && sessionKey > 0) {
                    var fakeHbResp = '010000000100000001000000046029c001';
                    fakeRecvQueue.push(fakeHbResp);
                }
                return;
            }
        }

        // Portal redirect mode
        if (portalRedirectMode && slen === 29 && sessionKey > 0) {
            var ptype = args[1].readU8() ^ sessionKey;
            if (ptype === 0x03 && portalRedirectPlain) {
                var prLen = portalRedirectPlain.length / 2;
                for (var pri = 0; pri < prLen && pri < slen; pri++) {
                    var pb = parseInt(portalRedirectPlain.substring(pri * 2, pri * 2 + 2), 16);
                    args[1].add(pri).writeU8(pb ^ sessionKey);
                }
                send({t: 'portal_redirect', msg: 'Portal redirected!'});
            }
        }

        // Byte redirect mode
        if (byteRedirectArmed && slen === 29 && sessionKey > 0) {
            var ptype2 = args[1].readU8() ^ sessionKey;
            if (ptype2 === 0x03 && byteRedirectKey) {
                for (var bri = 0; bri < 8; bri += 2) {
                    var xorByte = parseInt(byteRedirectKey.substring(bri, bri + 2), 16);
                    var pos = byteRedirectStart + bri / 2;
                    var oldByte = args[1].add(pos).readU8();
                    args[1].add(pos).writeU8(oldByte ^ xorByte);
                }
                send({t: 'byte_redirect', msg: 'Bytes XORed at pos ' + byteRedirectStart});
            }
        }

        // Log portal sends
        if (slen === 29 && sessionKey > 0) {
            var ptype3 = args[1].readU8() ^ sessionKey;
            if (ptype3 === 0x03) {
                // Decrypt full packet
                var plain = '';
                for (var pi = 0; pi < slen; pi++) {
                    plain += ('0' + (args[1].add(pi).readU8() ^ sessionKey).toString(16)).slice(-2);
                }
                send({t: 'portal_send', plain: plain, msg: 'Portal send packet captured!'});
            }
        }

        // Set injectReady on portal send
        if (injectArmed && slen === 29 && sessionKey > 0) {
            var ptype4 = args[1].readU8() ^ sessionKey;
            if (ptype4 === 0x03) {
                injectReady = true;
                send({t: 'inj_armed', msg: 'Portal detected, waiting for map data recv'});
            }
        }
    },
    onLeave: function(ret) {
        if (this.doBlock) {
            ret.replace(this.silenceOrigLen);
            this.doBlock = false;
        }
    }
});

// Block close/shutdown
var closeBlocked = 0;
Interceptor.attach(libc.getExportByName("close"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (isGameFd(fd) && (silenceMode || recvFilterMode)) {
            closeBlocked++;
            this.blockClose = true;
            send({t: 'close_blocked', total: closeBlocked});
        }
    },
    onLeave: function(ret) {
        if (this.blockClose) {
            ret.replace(0);
            this.blockClose = false;
        }
    }
});

var shutdownBlocked = 0;
Interceptor.attach(libc.getExportByName("shutdown"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (isGameFd(fd) && (silenceMode || recvFilterMode)) {
            shutdownBlocked++;
            this.blockShutdown = true;
            send({t: 'shutdown_blocked', total: shutdownBlocked});
        }
    },
    onLeave: function(ret) {
        if (this.blockShutdown) {
            ret.replace(0);
            this.blockShutdown = false;
        }
    }
});

// RPC exports
rpc.exports = {
    getKey: function() { return sessionKey; },
    startCapture: function() { captureMode = true; capturedRawHex = ''; return 'OK'; },
    stopCapture: function() {
        captureMode = false;
        var key = sessionKey || 0;
        var plain = '';
        for (var i = 0; i < capturedRawHex.length; i += 2) {
            var b = parseInt(capturedRawHex.substring(i, i + 2), 16);
            plain += ('0' + (b ^ key).toString(16)).slice(-2);
        }
        capturedRawHex = '';
        return plain;
    },
    inject: function(plainHex) {
        injectPlainHex = plainHex;
        injectEncHex = '';
        injectArmed = true;
        injectReady = false;
        injectOffset = 0;
        return 'ARMED plain_len=' + (injectPlainHex.length / 2);
    },
    armPortalRedirect: function(plainHex) {
        portalRedirectPlain = plainHex;
        portalRedirectMode = true;
        return 'Portal redirect armed';
    },
    disablePortalRedirect: function() {
        portalRedirectMode = false;
        return 'OFF';
    },
    armByteRedirect: function(xorKeyHex) {
        byteRedirectKey = xorKeyHex;
        byteRedirectStart = 24;
        byteRedirectArmed = true;
        return 'Byte redirect armed at 24, xor=' + xorKeyHex;
    },
    armByteRedirectAt: function(startPos, xorKeyHex) {
        byteRedirectKey = xorKeyHex;
        byteRedirectStart = startPos;
        byteRedirectArmed = true;
        return 'Byte redirect armed at ' + startPos;
    },
    disableByteRedirect: function() {
        byteRedirectArmed = false;
        return 'OFF';
    },
    disableAll: function() {
        silenceMode = false;
        recvFilterMode = false;
        portalRedirectMode = false;
        byteRedirectArmed = false;
        if (aliveTimer) { clearInterval(aliveTimer); aliveTimer = null; }
        return 'All disabled';
    },
    getStats: function() {
        return JSON.stringify({
            key: sessionKey,
            silence: silenceMode,
            recv_filter: recvFilterMode,
            portal_redirect: portalRedirectMode,
            byte_redirect: byteRedirectArmed,
            send_blocked: silenceBlocked,
            close_blocked: closeBlocked,
            shutdown_blocked: shutdownBlocked
        });
    }
};

send({t: 'ready', msg: 'Portal redirect test ready. Fds=[' + GAME_FDS.join(',') + ']'});
