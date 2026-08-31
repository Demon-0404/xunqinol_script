var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;
var M1 = 0, M2 = 0;
var scanPhase = 0;
var prevMatches = [];
var prevScanX = 0, prevScanY = 0;
var testedAddr = null;
var writePending = false;
var wroteTargetX = 0, wroteTargetY = 0;

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

// Scan for [X,0,0,0, ?,?,?,?, Y,0,0,0] 12-byte pattern with wildcards
function scanXY12(ranges, x, y) {
    // Build pattern: XX 00 00 00 ?? ?? ?? ?? YY 00 00 00
    var pat = ('0' + x.toString(16)).slice(-2) + ' 00 00 00 ?? ?? ?? ?? ' +
              ('0' + y.toString(16)).slice(-2) + ' 00 00 00';
    var res = [];
    ranges.forEach(function(r) {
        try {
            var m = Memory.scanSync(r.base, r.size, pat);
            for (var i = 0; i < m.length; i++) {
                res.push(m[i].address.toString());
                if (res.length >= 1000) return;
            }
        } catch(e) {}
    });
    return res;
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

            // Check if previous write test had effect
            if (writePending && testedAddr) {
                try {
                    var currX = ptr(testedAddr).readU32() & 0xFF;
                    var currY = ptr(testedAddr).add(8).readU32() & 0xFF;
                    send({t: 'write_result',
                          addr: testedAddr,
                          wroteX: wroteTargetX, wroteY: wroteTargetY,
                          memX: currX, memY: currY,
                          pktX: x, pktY: y});
                } catch(e) {}
                writePending = false;
            }

            if (lastX !== null && (x !== lastX || y !== lastY)) {
                send({t: 'move', x: x, y: y});

                if (scanPhase === 0) {
                    send({t: 'scanning', phase: 1, x: x, y: y});
                    var ranges = collectRanges();
                    prevMatches = scanXY12(ranges, x, y);
                    prevScanX = x; prevScanY = y;
                    send({t: 'scanned', phase: 1, count: prevMatches.length});
                    scanPhase = 1;

                } else if (scanPhase === 1) {
                    send({t: 'scanning', phase: 2, x: x, y: y});
                    var ranges = collectRanges();
                    var newMatches = scanXY12(ranges, x, y);
                    send({t: 'scanned', phase: 2, count: newMatches.length});

                    // Cross-reference
                    var prevSet = {};
                    for (var i = 0; i < prevMatches.length; i++) {
                        prevSet[prevMatches[i]] = true;
                    }

                    var cross = [];
                    for (var i = 0; i < newMatches.length; i++) {
                        if (prevSet[newMatches[i]]) {
                            cross.push(newMatches[i]);
                            if (cross.length >= 10) break;
                        }
                    }

                    if (cross.length > 0) {
                        // Verify and test write on best candidate
                        for (var ci = 0; ci < cross.length; ci++) {
                            try {
                                var addr = cross[ci];
                                var u0 = ptr(addr).readU32();
                                var u4 = ptr(addr).add(4).readU32();
                                var u8 = ptr(addr).add(8).readU32();
                                var u12 = ptr(addr).add(12).readU32();

                                send({t: 'candidate', addr: addr,
                                      u0: u0, u4: u4, u8: u8, u12: u12,
                                      pktX: x, pktY: y});

                                // Write test: add 30 to X and Y (with wraparound)
                                var newX = ((x + 30) & 0xFF);
                                var newY = ((y + 30) & 0xFF);

                                // Preserve upper bytes from original value
                                var writeX = newX | (u0 & 0xFFFFFF00);
                                var writeY = newY | (u8 & 0xFFFFFF00);

                                ptr(addr).writeU32(writeX);
                                ptr(addr).add(8).writeU32(writeY);

                                // Read back immediately
                                var cbX = ptr(addr).readU32() & 0xFF;
                                var cbY = ptr(addr).add(8).readU32() & 0xFF;

                                if (cbX === newX && cbY === newY) {
                                    testedAddr = addr;
                                    wroteTargetX = newX;
                                    wroteTargetY = newY;
                                    writePending = true;
                                    send({t: 'tested', addr: addr,
                                          oldX: u0 & 0xFF, oldY: u8 & 0xFF,
                                          newX: newX, newY: newY,
                                          writeOk: true});
                                    break;  // Only test first match
                                }
                            } catch(e) {
                                send({t: 'test_err', addr: cross[ci], err: e.toString()});
                            }
                        }
                        scanPhase = 2;
                    } else {
                        send({t: 'no_cross', prevCount: prevMatches.length, newCount: newMatches.length});
                        prevMatches = newMatches;
                        prevScanX = x; prevScanY = y;
                    }
                }
                // Phase 2+: monitor the found address
                else if (scanPhase >= 2 && testedAddr) {
                    try {
                        var mx = ptr(testedAddr).readU32() & 0xFF;
                        var my = ptr(testedAddr).add(8).readU32() & 0xFF;
                        if (mx !== x || my !== y) {
                            send({t: 'desync', addr: testedAddr, memX: mx, memY: my, pktX: x, pktY: y});
                        }
                    } catch(e) {}
                }
            }
            lastX = x; lastY = y;
        }
    }
});

send({t: 'ready'});
