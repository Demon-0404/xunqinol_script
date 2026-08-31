var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;
var M1 = 0, M2 = 0;
var posAddr = null;
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

function dumpRegion(addr, bytesBefore, bytesAfter) {
    try {
        var start = ptr(addr).sub(bytesBefore);
        var total = bytesBefore + bytesAfter;
        var raw = start.readByteArray(total);
        var arr = new Uint8Array(raw);

        // Format as u32 values
        var u32s = [];
        for (var i = 0; i + 3 < arr.length; i += 4) {
            var v = arr[i] | (arr[i+1] << 8) | (arr[i+2] << 16) | (arr[i+3] << 24);
            u32s.push(v);
        }

        // Also format as floats
        var floats = [];
        var fbuf = new ArrayBuffer(4);
        var fv = new DataView(fbuf);
        for (var i = 0; i + 3 < arr.length; i += 4) {
            fv.setUint8(0, arr[i]);
            fv.setUint8(1, arr[i+1]);
            fv.setUint8(2, arr[i+2]);
            fv.setUint8(3, arr[i+3]);
            floats.push(fv.getFloat32(0, true));
        }

        return {u32s: u32s, floats: floats, raw: arr};
    } catch(e) {
        return null;
    }
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

            // Phase 0-1: find address
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
                        // Dump the region immediately
                        var dump = dumpRegion(posAddr, 64, 128);
                        if (dump) {
                            send({t: 'dump', addr: posAddr, u32s: dump.u32s, floats: dump.floats});
                        }
                    }
                }
            }
            // After finding, dump on each move to see what changes
            else if (posAddr && lastX !== null && (x !== lastX || y !== lastY)) {
                var dump = dumpRegion(posAddr, 64, 128);
                if (dump) {
                    send({t: 'changed', x: x, y: y, u32s: dump.u32s, floats: dump.floats});
                }
            }
            lastX = x; lastY = y;
        }
    }
});

send({t: 'ready'});
