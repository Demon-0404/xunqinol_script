var GAME_FDS = GAME_FDS_PLACEHOLDER;
var libc = Process.getModuleByName("libc.so");

function isGameFd(fd) {
    return GAME_FDS.indexOf(fd) !== -1;
}

var sessionKey = 0;
var captureMode = false;
var capturedRawHex = '';
var injectArmed = false;
var injectReady = false;
var injectPlainHex = '';
var injectEncHex = '';
var injectOffset = 0;
var monitorMode = false;
var capturePortalMode = false;
var capturedPortalList = [];
var silenceMode = false;
var silenceUntil = 0;
var silenceBlocked = 0;
var lastRecvTime = 0;
var lastFakeRecvTime = 0;
var aliveTimer = null;
var fakeRecvQueue = []; // fake recv data to inject (hex strings)
var portalRedirectMode = false;
var portalRedirectPlain = ''; // plain hex of target portal send
var byteRedirectKey = ''; // hex XOR key for bytes 24-27 (counter-independent!)
var byteRedirectArmed = false;
var byteRedirectStart = 24; // start position for byte redirect (default 24)
var diagBytePos = -1; // diagnostic: single byte position to XOR
var diagByteVal = 0;  // diagnostic: XOR value for that byte
var noSilenceMode = false; // if true, skip silence after injection
var recvFilterMode = false; // if true, filter recv only (block incompatible data) but allow sends

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

        // Inject fake recv data (queued heartbeat responses) during silence
        if (silenceMode && fakeRecvQueue.length > 0 && sessionKey > 0) {
            var fakeHex = fakeRecvQueue.shift();
            var fakeLen = fakeHex.length / 2;
            for (var fi = 0; fi < fakeLen; fi++) {
                var fb = parseInt(fakeHex.substring(fi * 2, fi * 2 + 2), 16);
                this.buf.add(fi).writeU8(fb ^ sessionKey);
            }
            ret.replace(fakeLen);
            send({t: 'fake_recv', len: fakeLen, msg: 'Injected fake heartbeat response'});
            return;
        }

        // Silence mode: block server FIN, inject fake heartbeat response instead
        if (silenceMode && realLen === 0) {
            var now = Date.now();
            if (now - lastFakeRecvTime > 10000 && sessionKey > 0) {
                lastFakeRecvTime = now;
                send({t: 'recv_zero_blocked', msg: 'Server FIN, injecting fake hb response', fd: this.fd});
                var fakeResp = [0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
                                0x01, 0x00, 0x00, 0x00, 0x04, 0x60, 0x29, 0xc0, 0x01];
                for (var fi = 0; fi < fakeResp.length; fi++) {
                    this.buf.add(fi).writeU8(fakeResp[fi] ^ sessionKey);
                }
                ret.replace(fakeResp.length);
            } else {
                ret.replace(-1);
            }
            return;
        }

        // Silence mode: log recv errors (RST etc)
        if (silenceMode && realLen < 0) {
            send({t: 'recv_err', len: realLen, msg: 'recv error during silence', fd: this.fd});
            ret.replace(-1);
            var _errnoPtr2 = libc.getExportByName("__errno");
            if (_errnoPtr2) {
                var errnoPtr2 = new NativeFunction(_errnoPtr2, 'pointer', []);
                errnoPtr2().writeInt(11); // EAGAIN
            }
            return;
        }

        // Recv filter mode: block incompatible server data after injection, but keep alive with fake HB
        if (recvFilterMode) {
            if (realLen === 0) {
                // Server FIN — block it, inject fake heartbeat response
                var now3 = Date.now();
                if (now3 - lastFakeRecvTime > 5000 && sessionKey > 0) {
                    lastFakeRecvTime = now3;
                    var fakeResp3 = [0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
                                    0x01, 0x00, 0x00, 0x00, 0x04, 0x60, 0x29, 0xc0, 0x01];
                    for (var fi3 = 0; fi3 < fakeResp3.length; fi3++) {
                        this.buf.add(fi3).writeU8(fakeResp3[fi3] ^ sessionKey);
                    }
                    ret.replace(fakeResp3.length);
                    send({t: 'recv_filter', msg: 'Blocked FIN, injected fake HB'});
                } else {
                    ret.replace(-1);
                }
                return;
            }
            if (realLen < 0) {
                ret.replace(-1);
                var _errnoPtr3 = libc.getExportByName("__errno");
                if (_errnoPtr3) {
                    var errnoPtr3 = new NativeFunction(_errnoPtr3, 'pointer', []);
                    errnoPtr3().writeInt(11); // EAGAIN
                }
                return;
            }
            // realLen > 0: block incompatible data, return EAGAIN
            send({t: 'recv_filter', msg: 'Blocked recv ' + realLen + 'B (incompatible map data)'});
            ret.replace(-1);
            var _errnoPtr4 = libc.getExportByName("__errno");
            if (_errnoPtr4) {
                var errnoPtr4 = new NativeFunction(_errnoPtr4, 'pointer', []);
                errnoPtr4().writeInt(11); // EAGAIN
            }
            return;
        }

        if (realLen <= 0) return;

        // Auto-detect session key
        if (sessionKey === 0 && realLen >= 4) {
            var tryKey = this.buf.readU8() ^ 0x03;
            if ((this.buf.add(1).readU8() ^ tryKey) === 0 &&
                (this.buf.add(2).readU8() ^ tryKey) === 0 &&
                (this.buf.add(3).readU8() ^ tryKey) === 0) {
                sessionKey = tryKey;
                send({t: 'key', key: sessionKey});
            }
        }

        // Capture: save raw encrypted bytes
        if (captureMode) {
            for (var i = 0; i < realLen; i++) {
                capturedRawHex += ('0' + this.buf.add(i).readU8().toString(16)).slice(-2);
            }
        }

        // Recv stream injection (encrypt on first recv with detected key)
        if (injectArmed && injectPlainHex && realLen > 0) {
            // Gate 1: wait for portal send detection
            if (!injectReady) {
                send({t: 'inj_wait', msg: 'No portal yet, skip recv=' + realLen});
                return;
            }
            // Gate 2: wait for session key
            if (sessionKey === 0) {
                send({t: 'inj_wait', msg: 'Waiting for session key, skip recv=' + realLen});
                return;
            }
            // Gate 3: first injection must be big recv (map data)
            if (!injectEncHex && realLen < 50) {
                send({t: 'inj_wait', msg: 'Small recv, waiting for map data, skip recv=' + realLen});
                return;
            }
            if (!injectEncHex) {
                for (var i = 0; i < injectPlainHex.length; i += 2) {
                    var b = parseInt(injectPlainHex.substring(i, i + 2), 16);
                    injectEncHex += ('0' + (b ^ sessionKey).toString(16)).slice(-2);
                }
                send({t: 'inj_key', key: sessionKey});
            }
            var totalLen = injectEncHex.length / 2;
            var remaining = totalLen - injectOffset;
            send({t: 'inj_log', len: realLen, remain: remaining});

            if (remaining > 0) {
                var chunk = Math.min(remaining, realLen);
                for (var i = 0; i < chunk; i++) {
                    var b = parseInt(injectEncHex.substring((injectOffset + i) * 2, (injectOffset + i) * 2 + 2), 16);
                    this.buf.add(i).writeU8(b);
                }
                injectOffset += chunk;
                ret.replace(realLen);
                send({t: 'inj_chunk', wrote: chunk, offset: injectOffset, total: totalLen, real: realLen});
            }

            if (injectOffset >= totalLen) {
                injectArmed = false;
                injectReady = false;
                if (noSilenceMode) {
                    recvFilterMode = true;
                    send({t: 'inj_done', msg: 'All data delivered, RECV FILTER ON (sends OK, recv blocked)'});
                } else {
                    silenceMode = true;
                    silenceUntil = Date.now() + 300000;
                    silenceBlocked = 0;
                    lastRecvTime = Date.now();
                    if (aliveTimer) clearInterval(aliveTimer);
                    aliveTimer = setInterval(function() {
                        var since = Date.now() - lastRecvTime;
                        send({t: 'alive', since_recv: since, silence_left: Math.max(0, silenceUntil - Date.now())});
                    }, 3000);
                    send({t: 'inj_done', msg: 'All data delivered, silence ON for 5min'});
                }
            }
        }

        // Log recv during silence mode — watch for server disconnect
        if (silenceMode && realLen > 0) {
            lastRecvTime = Date.now();
            lastFakeRecvTime = 0; // reset fake recv cooldown when real data arrives
            var hex = '';
            var dumpLen = Math.min(realLen, 200);
            for (var ri = 0; ri < dumpLen; ri++) {
                hex += ('0' + this.buf.add(ri).readU8().toString(16)).slice(-2);
            }
            send({t: 'silence_recv', len: realLen, hex: hex, fd: this.fd});
        }
    }
});

// Portal send detection
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        if (isGameFd(args[0].toInt32())) {
            this.fd = args[0].toInt32();
            var slen = args[2].toInt32();
            this.doBlock = false;

            // Silence mode: block all sends except heartbeats after teleport
            if (silenceMode) {
                var now = Date.now();
                if (now >= silenceUntil) {
                    silenceMode = false;
                    if (aliveTimer) { clearInterval(aliveTimer); aliveTimer = null; }
                    send({t: 'silence_off', msg: 'Silence expired, blocked ' + silenceBlocked + ' packets'});
                } else {
                    // Block everything — prevent state mismatch from reaching server
                    silenceBlocked++;
                    this.silenceOrigLen = slen;
                    this.doBlock = true;
                    args[2] = ptr(0);
                    // If this was a heartbeat (17B 0x01), queue a fake response for recv
                    if (slen === 17 && args[1].readU8() === 1 && sessionKey > 0) {
                        // Server's heartbeat response pattern (plain text)
                        var fakeHbResp = '010000000100000001000000046029c001';
                        fakeRecvQueue.push(fakeHbResp);
                        send({t: 'hb_queued', msg: 'Fake heartbeat response queued'});
                    }
                }
            }

            // Monitor mode: log ALL sends with full hex
            if (monitorMode) {
                var fullHex = '';
                for (var mi = 0; mi < slen; mi++) {
                    fullHex += ('0' + args[1].add(mi).readU8().toString(16)).slice(-2);
                }
                send({t: 'monitor', len: slen, hex: fullHex, fd: this.fd});
            }

            if (slen > 10) {
                var hex = '';
                var dumpLen = Math.min(slen, 40);
                for (var di = 0; di < dumpLen; di++) {
                    hex += ('0' + args[1].add(di).readU8().toString(16)).slice(-2);
                }
                send({t: 'send_log', len: slen, hex: hex, fd: this.fd});
            }

            // Portal detection for capture auto-stop
            if (captureMode && slen >= 28 && slen <= 31 && args[1].readU8() === 3) {
                setTimeout(function() {
                    if (captureMode) {
                        captureMode = false;
                        send({t: 'capture_done', len: capturedRawHex.length / 2});
                    }
                }, 8000);
            }

            // Portal redirect mode: replace portal destination with target map
            if (portalRedirectMode && slen === 29 && args[1].readU8() === 3 && portalRedirectPlain && sessionKey > 0) {
                var prLen = portalRedirectPlain.length / 2;
                for (var pri = 0; pri < prLen && pri < slen; pri++) {
                    var pb = parseInt(portalRedirectPlain.substring(pri * 2, pri * 2 + 2), 16);
                    args[1].add(pri).writeU8(pb ^ sessionKey);
                }
                send({t: 'portal_redirect', msg: 'Portal redirected to target map'});
            }

            // Byte redirect: XOR destination bytes at configurable position (counter-independent!)
            if (byteRedirectArmed && slen === 29 && args[1].readU8() === 3 && byteRedirectKey) {
                for (var bri = 0; bri < 8; bri += 2) {
                    var xorByte = parseInt(byteRedirectKey.substring(bri, bri + 2), 16);
                    var pos = byteRedirectStart + bri / 2;
                    var oldByte = args[1].add(pos).readU8();
                    args[1].add(pos).writeU8(oldByte ^ xorByte);
                }
                send({t: 'byte_redirect', msg: 'Bytes ' + byteRedirectStart + '-' + (byteRedirectStart+3) + ' XORed with ' + byteRedirectKey});
            }

            // Diagnostic: XOR a single byte at a specific position
            if (diagBytePos >= 0 && slen === 29 && args[1].readU8() === 3) {
                var oldByte = args[1].add(diagBytePos).readU8();
                args[1].add(diagBytePos).writeU8(oldByte ^ diagByteVal);
                send({t: 'diag_xor', pos: diagBytePos, old: oldByte, new: oldByte ^ diagByteVal, xor: diagByteVal});
            }

            // Set injectReady on portal send (must be exactly 29B — 30B is normal move)
            if (injectArmed && slen === 29 && args[1].readU8() === 3) {
                injectReady = true;
                send({t: 'inj_armed', msg: 'Portal detected, waiting for large recv with map data'});
            }

            // Capture REAL portal send packets (only 29B — 30B is normal move)
            if (capturePortalMode && slen === 29 && args[1].readU8() === 3) {
                var portalHex = '';
                for (var pi = 0; pi < slen; pi++) {
                    portalHex += ('0' + args[1].add(pi).readU8().toString(16)).slice(-2);
                }
                capturedPortalList.push(portalHex);
                send({t: 'portal_captured', len: slen, hex: portalHex});
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

// Hook close() — prevent game from disconnecting after teleport
var closeBlocked = 0;
Interceptor.attach(libc.getExportByName("close"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (isGameFd(fd) && (silenceMode || recvFilterMode)) {
            closeBlocked++;
            this.blockClose = true;
            this.blockedFd = fd;
            send({t: 'close_blocked', fd: fd, total: closeBlocked,
                stack: Thread.backtrace(this.context, Backtracer.ACCURATE)
                    .map(DebugSymbol.fromAddress).join(' <- ')});
        }
    },
    onLeave: function(ret) {
        if (this.blockClose) {
            ret.replace(0); // fake success
            this.blockClose = false;
        }
    }
});

// Hook shutdown() — same reason
var shutdownBlocked = 0;
Interceptor.attach(libc.getExportByName("shutdown"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (isGameFd(fd) && (silenceMode || recvFilterMode)) {
            shutdownBlocked++;
            this.blockShutdown = true;
            send({t: 'shutdown_blocked', fd: fd, how: args[1].toInt32(), total: shutdownBlocked,
                stack: Thread.backtrace(this.context, Backtracer.ACCURATE)
                    .map(DebugSymbol.fromAddress).join(' <- ')});
        }
    },
    onLeave: function(ret) {
        if (this.blockShutdown) {
            ret.replace(0); // fake success
            this.blockShutdown = false;
        }
    }
});

rpc.exports = {
    startCapture: function() { captureMode = true; capturedRawHex = ''; return 'OK'; },
    stopCapture: function() {
        captureMode = false;
        var key = sessionKey || 0xbe;
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
        noSilenceMode = false;
        return 'ARMED plain_len=' + (injectPlainHex.length / 2) + ' (3 gates: portal/key/big_recv)';
    },
    injectNoSilence: function(plainHex) {
        injectPlainHex = plainHex;
        injectEncHex = '';
        injectArmed = true;
        injectReady = false;
        injectOffset = 0;
        noSilenceMode = true;
        return 'ARMED_NO_SILENCE plain_len=' + (injectPlainHex.length / 2) + ' (sends flow freely after injection)';
    },
    getKey: function() { return sessionKey; },
    startMonitor: function() { monitorMode = true; return 'Monitor ON'; },
    stopMonitor: function() { monitorMode = false; return 'Monitor OFF'; },
    startPortalCapture: function() { capturePortalMode = true; capturedPortalList = []; return 'Portal capture armed'; },
    stopPortalCapture: function() { capturePortalMode = false; return JSON.stringify(capturedPortalList); },
    stopPortalCapturePlain: function() {
        capturePortalMode = false;
        var key = sessionKey || 0;
        var result = [];
        for (var i = 0; i < capturedPortalList.length; i++) {
            var enc = capturedPortalList[i];
            var plain = '';
            for (var j = 0; j < enc.length; j += 2) {
                var b = parseInt(enc.substring(j, j + 2), 16);
                plain += ('0' + (b ^ key).toString(16)).slice(-2);
            }
            result.push({enc: enc, plain: plain, key: key});
        }
        return JSON.stringify(result);
    },
    disableSilence: function() { silenceMode = false; recvFilterMode = false; if (aliveTimer) { clearInterval(aliveTimer); aliveTimer = null; } return 'Silence OFF, send_blocked=' + silenceBlocked + ' close_blocked=' + closeBlocked + ' shutdown_blocked=' + shutdownBlocked; },
    injectRecvFilter: function(plainHex) {
        injectPlainHex = plainHex;
        injectEncHex = '';
        injectArmed = true;
        injectReady = false;
        injectOffset = 0;
        noSilenceMode = true; // don't enable silence mode
        // recvFilterMode will be enabled after injection completes (in onLeave of recv)
        return 'RECV_FILTER armed plain_len=' + (injectPlainHex.length / 2) + ' (sends OK, recv filtered after inject)';
    },
    getStats: function() { return JSON.stringify({silence: silenceMode, send_blocked: silenceBlocked, close_blocked: closeBlocked, shutdown_blocked: shutdownBlocked}); },
    armPortalRedirect: function(plainHex) {
        portalRedirectPlain = plainHex;
        portalRedirectMode = true;
        return 'Portal redirect armed, plain_len=' + (portalRedirectPlain.length / 2);
    },
    disablePortalRedirect: function() { portalRedirectMode = false; return 'Portal redirect OFF'; },
    armByteRedirect: function(xorKeyHex) {
        byteRedirectKey = xorKeyHex;
        byteRedirectStart = 24;
        byteRedirectArmed = true;
        return 'Byte redirect armed at pos 24, xor_key=' + xorKeyHex;
    },
    armByteRedirectAt: function(startPos, xorKeyHex) {
        byteRedirectKey = xorKeyHex;
        byteRedirectStart = startPos;
        byteRedirectArmed = true;
        return 'Byte redirect armed at pos ' + startPos + ', xor_key=' + xorKeyHex;
    },
    disableByteRedirect: function() { byteRedirectArmed = false; return 'Byte redirect OFF'; },
    diagXorByte: function(pos, val) {
        diagBytePos = pos;
        diagByteVal = val;
        return 'Diag XOR armed: pos=' + pos + ' val=0x' + val.toString(16);
    },
    diagClear: function() { diagBytePos = -1; diagByteVal = 0; return 'Diag OFF'; }
};

send({t: 'ready', msg: 'Recv inject v5 ready.'});
