// Search for player position coordinates in game memory
// Game uses cocos2d-x, position stored as float (x, y) or (x, y, z)
// Typical coordinate ranges: small values like 100-5000

var base = ptr(0xc19c000);

// Scan writable memory for coordinate patterns
// Strategy: find two consecutive floats that look like game coordinates
function readFloat(addr) {
    var b = addr.readByteArray(4);
    var arr = new Uint8Array(b);
    var bits = arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
    // Convert to float
    var sign = (bits >> 31) ? -1 : 1;
    var exp = ((bits >> 23) & 0xff) - 127;
    var mantissa = (bits & 0x7fffff) | 0x800000;
    var val = sign * mantissa * Math.pow(2, exp - 23);
    return val;
}

// Quick scan: read bytes and check if they look like valid floats
// Float values in range 100-10000 for x, 100-10000 for y
function isValidCoord(val) {
    return val > 50 && val < 50000 && Math.abs(val - Math.round(val)) < 0.01;
}

// Scan the rw- regions of libtestcpp.so
var ranges = Process.enumerateRanges('rw-');
send({t: 'log', msg: 'Scanning ' + ranges.length + ' rw- regions for coordinates...'});

var candidates = [];
var scanned = 0;

for (var ri = 0; ri < ranges.length; ri++) {
    var r = ranges[ri];
    // Skip tiny regions and very large ones
    if (r.size < 0x1000 || r.size > 0x1000000) continue;

    var end = r.base.add(r.size - 16);
    for (var addr = r.base; addr.compare(end) < 0; addr = addr.add(4)) {
        scanned++;
        if (scanned > 5000000) break; // safety limit

        try {
            var v1 = readFloat(addr);
            if (isValidCoord(v1)) {
                var v2 = readFloat(addr.add(4));
                if (isValidCoord(v2)) {
                    // Found a pair that looks like coordinates
                    // Check for a third (z) coordinate
                    var v3 = readFloat(addr.add(8));
                    var hasZ = isValidCoord(v3) && v3 < 1000;

                    // Also check nearby for name-like pattern
                    candidates.push({
                        addr: addr.toString(),
                        x: v1,
                        y: v2,
                        z: v3,
                        hasZ: hasZ
                    });

                    if (candidates.length <= 10) {
                        send({t: 'candidate', addr: addr.toString(), x: v1.toFixed(1), y: v2.toFixed(1), z: v3.toFixed(1)});
                    }
                    if (candidates.length >= 30) break;
                }
            }
        } catch(e) {
            break; // unreadable region
        }
    }
    if (scanned > 5000000) break;
    if (candidates.length >= 30) break;
}

send({t: 'log', msg: 'Scanned ~' + scanned + ' locations, found ' + candidates.length + ' candidates'});

// Now: try to narrow down by writing to a few candidates and checking if player moves
// But first, let's try interactive testing with a known good candidate
// Store the first 5 for interactive testing
rpc.exports = {
    candidates: candidates.slice(0, 5),
    getCandidates: function() { return JSON.stringify(candidates.slice(0, 5)); },
    writeCoord: function(idx, newX, newY) {
        if (idx >= candidates.length) return 'Invalid index';
        var c = candidates[idx];
        var addr = ptr(c.addr);
        try {
            Memory.protect(addr.and(ptr(0xfffff000)), 4096, 'rwx');
            addr.writeFloat(newX);
            addr.add(4).writeFloat(newY);
            return 'Wrote (' + newX + ', ' + newY + ') to ' + addr;
        } catch(e) {
            return 'Error: ' + e;
        }
    },
    readCoord: function(idx) {
        if (idx >= candidates.length) return 'Invalid index';
        var c = candidates[idx];
        var addr = ptr(c.addr);
        var x = addr.readFloat();
        var y = addr.add(4).readFloat();
        return 'Addr=' + addr + ' x=' + x.toFixed(1) + ' y=' + y.toFixed(1);
    }
};

send({t: 'ready', msg: 'done'});
