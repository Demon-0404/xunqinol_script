var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;
var M1 = 0, M2 = 0;
var POS_ADDR = null;
var scanPhase = 0;
var prevXAddrs = [];
var testPhase = 0; // 0=waiting, 1=wrote pending, 2=done
var savedX = 0, savedY = 0;

function collectRanges() {
    var all = [];
    var ranges = Process.enumerateRanges({protection: 'rw-', coalesce: true});
    ranges.forEach(function(r) {
        var sz = typeof r.size === 'number' ? r.size : Number(r.size);
        if (sz >= 65536 && sz <= 67108864) {
            all.push({base: r.base, size: sz});
        }
    });
    return all;
}

function scanPat(ranges, patBytes) {
    var patStr = '';
    for (var i = 0; i < patBytes.length; i++) {
        if (i > 0) patStr += ' ';
        patStr += ('0' + patBytes[i].toString(16)).slice(-2);
    }
    var results = [];
    ranges.forEach(function(r) {
        try {
            var matches = Memory.scanSync(r.base, r.size, patStr);
            for (var i = 0; i < matches.length; i++) {
                results.push(matches[i].address.toString());
                if (results.length >= 5000) return;
            }
        } catch(e) {}
    });
    return results;
}

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {
            var key = buf.add(1).readU8();
            var p = [];
            for (var i = 0; i < 29; i++) p.push(buf.add(i + 1).readU8() ^ key);
            var x = p[17], y = p[21];
            if (!M1) { M1 = p[1]; M2 = p[3]; }

            if (lastX !== null && (x !== lastX || y !== lastY)) {
                // Phase 0: first scan
                if (scanPhase === 0) {
                    send({t: 'scanning', phase: 1, x: x});
                    var ranges = collectRanges();
                    prevXAddrs = scanPat(ranges, [x & 0xFF, (x>>8) & 0xFF, 0, 0]);
                    send({t: 'scanned', phase: 1, count: prevXAddrs.length});
                    scanPhase = 1;
                }
                // Phase 1: second scan + cross reference
                else if (scanPhase === 1) {
                    send({t: 'scanning', phase: 2, x: x});
                    var ranges2 = collectRanges();
                    var newXAddrs = scanPat(ranges2, [x & 0xFF, (x>>8) & 0xFF, 0, 0]);
                    send({t: 'scanned', phase: 2, count: newXAddrs.length});

                    var prevSet = {};
                    for (var i = 0; i < prevXAddrs.length; i++) prevSet[prevXAddrs[i]] = true;

                    for (var i = 0; i < newXAddrs.length; i++) {
                        if (prevSet[newXAddrs[i]]) {
                            try {
                                var u0 = ptr(newXAddrs[i]).readU32();
                                var u8 = ptr(newXAddrs[i]).add(8).readU32();
                                if ((u0 & 0xFF) === (x & 0xFF) && (u8 & 0xFF) === (y & 0xFF)) {
                                    POS_ADDR = newXAddrs[i];
                                    send({t: 'found', addr: POS_ADDR, x: x, y: y,
                                          u0: u0, u8: u8});
                                    break;
                                }
                            } catch(e) {}
                        }
                    }

                    if (POS_ADDR) {
                        scanPhase = 2;
                        // Auto test: write X+50 to memory
                        savedX = x; savedY = y;
                        var newX = (x + 50) & 0xFF;
                        try {
                            ptr(POS_ADDR).writeU32(newX);
                            send({t: 'test_write', addr: POS_ADDR, oldX: x, newX: newX, oldY: y});
                            testPhase = 1;
                        } catch(e) {
                            send({t: 'write_fail', err: e.toString()});
                        }
                    } else {
                        // Try next pair of moves
                        prevXAddrs = newXAddrs;
                        send({t: 'retry', msg: 'Move again to narrow down'});
                    }
                }
                // Test phase 1: after write, check if next position reflects our change
                else if (testPhase === 1) {
                    send({t: 'test_result',
                          beforeX: savedX, beforeY: savedY,
                          afterX: x, afterY: y,
                          expectedX: (savedX + 50) & 0xFF,
                          match: x === ((savedX + 50) & 0xFF)});
                    // Restore original value
                    try {
                        ptr(POS_ADDR).writeU32(savedX);
                        send({t: 'restored', x: savedX});
                    } catch(e) {}
                    testPhase = 2;
                }
                // After test, keep reporting for verification
                else {
                    try {
                        var memX = ptr(POS_ADDR).readU32() & 0xFF;
                        var memY = ptr(POS_ADDR).add(8).readU32() & 0xFF;
                        if (memX !== x || memY !== y) {
                            send({t: 'desync', pktX: x, pktY: y, memX: memX, memY: memY});
                        }
                    } catch(e) {}
                }
            }
            lastX = x; lastY = y;
        }
    }
});

send({t: 'ready'});
