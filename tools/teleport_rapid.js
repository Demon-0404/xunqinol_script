var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var M1 = 0, M2 = 0;
var lastX = null, lastY = null;
var targetX = null, targetY = null;
var posAddr = null;
var writeInterval = null;
var speedMult = 1.0;

// Phase 1: find position address using 12-byte pattern
var scanPhase = 0;
var prevMatches = [];

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

function scanXY12(ranges, x, y) {
    var pat = ('0' + x.toString(16)).slice(-2) + ' 00 00 00 ?? ?? ?? ?? ' +
              ('0' + y.toString(16)).slice(-2) + ' 00 00 00';
    var res = [];
    ranges.forEach(function(r) {
        try {
            var m = Memory.scanSync(r.base, r.size, pat);
            for (var i = 0; i < m.length; i++) {
                res.push(m[i].address.toString());
                if (res.length >= 100) return;
            }
        } catch(e) {}
    });
    return res;
}

// Rapid write to memory
function rapidWrite() {
    if (!posAddr || targetX === null) return;
    try {
        ptr(posAddr).writeU32(targetX);
        ptr(posAddr).add(8).writeU32(targetY);
    } catch(e) {}
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

            // Phase 0-1: find position address (same as before)
            if (!posAddr && lastX !== null && (x !== lastX || y !== lastY)) {
                if (scanPhase === 0) {
                    var ranges = collectRanges();
                    prevMatches = scanXY12(ranges, x, y);
                    send({t: 'scan1', x: x, y: y, count: prevMatches.length});
                    scanPhase = 1;
                } else if (scanPhase === 1) {
                    var ranges = collectRanges();
                    var newMatches = scanXY12(ranges, x, y);
                    send({t: 'scan2', x: x, y: y, count: newMatches.length});

                    var prevSet = {};
                    for (var i = 0; i < prevMatches.length; i++) prevSet[prevMatches[i]] = true;

                    for (var i = 0; i < newMatches.length; i++) {
                        if (prevSet[newMatches[i]]) {
                            posAddr = newMatches[i];
                            send({t: 'found', addr: posAddr, x: x, y: y});
                            break;
                        }
                    }
                    if (!posAddr) {
                        prevMatches = newMatches;
                        send({t: 'retry'});
                    } else {
                        scanPhase = 2;
                    }
                }
            }

            // Modify packet position if target is set
            if (targetX !== null && targetY !== null) {
                buf.add(18).writeU8(targetX ^ key);
                buf.add(20).writeU8(targetX ^ M1 ^ key);
                buf.add(22).writeU8(targetY ^ key);
                buf.add(24).writeU8(targetY ^ M2 ^ key);
            }

            // Speed hack: amplify position delta in packet
            if (speedMult !== 1.0 && lastX !== null && targetX === null) {
                var dx = x - lastX;
                var dy = y - lastY;
                var nx = (lastX + Math.round(dx * speedMult)) & 0xFF;
                var ny = (lastY + Math.round(dy * speedMult)) & 0xFF;
                buf.add(18).writeU8(nx ^ key);
                buf.add(20).writeU8(nx ^ M1 ^ key);
                buf.add(22).writeU8(ny ^ key);
                buf.add(24).writeU8(ny ^ M2 ^ key);
            }

            if (lastX === null || x !== lastX || y !== lastY) {
                // Also read memory for verification
                var memInfo = '';
                if (posAddr) {
                    try {
                        var mx = ptr(posAddr).readU32() & 0xFF;
                        var my = ptr(posAddr).add(8).readU32() & 0xFF;
                        if (mx !== x || my !== y) {
                            memInfo = ' mem=(' + mx + ',' + my + ')';
                        }
                    } catch(e) {}
                }
                send({t: 'pos', x: x, y: y, mem: memInfo, target: targetX !== null});
            }
            lastX = x; lastY = y;
        }
    }
});

// Commands
recv('teleport', function(data) {
    targetX = data.x & 0xFF;
    targetY = data.y & 0xFF;
    // Start rapid write interval (every 30ms)
    if (writeInterval) clearInterval(writeInterval);
    if (posAddr) {
        writeInterval = setInterval(rapidWrite, 30);
        send({t: 'tp_start', x: targetX, y: targetY, addr: posAddr});
    } else {
        send({t: 'tp_noaddr', x: targetX, y: targetY});
    }
});

recv('stop_tp', function(data) {
    targetX = null; targetY = null;
    if (writeInterval) { clearInterval(writeInterval); writeInterval = null; }
    send({t: 'tp_stop'});
});

recv('speed', function(data) {
    speedMult = data.mult;
    send({t: 'speed_set', mult: speedMult});
});

send({t: 'ready'});
