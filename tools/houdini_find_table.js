// Fast scan: read chunks and look for ARM->x86 pointer pairs locally
var houdini = Process.getModuleByName("libhoudini.so");
var testcppBase = ptr(0xc074000);
var testcppEnd = testcppBase.add(0x480000);
var cacheStart = ptr(0x0d120000);
var cacheEnd = ptr(0x11078000);

send({t: 'log', msg: 'libhoudini: ' + houdini.base + ' size=' + (houdini.size/1048576).toFixed(1) + 'MB'});
send({t: 'log', msg: 'Code cache: ' + cacheStart + ' - ' + cacheEnd});
send({t: 'log', msg: 'libtestcpp: ' + testcppBase + ' - ' + testcppEnd});

// Get libhoudini's writable ranges
var hEnd = houdini.base.add(houdini.size);
var allRanges = Process.enumerateRanges({protection: 'rw-', coalesce: true});
var hRanges = [];

for (var i = 0; i < allRanges.length; i++) {
    if (allRanges[i].base.compare(houdini.base) >= 0 && allRanges[i].base.compare(hEnd) < 0) {
        hRanges.push(allRanges[i]);
    }
}

// For each range, read in chunks and scan for pointer pairs
// A potential entry: two 32-bit values (ARM addr, x86 addr)
// ARM addr range: 0x0c074000 - 0x0c4c0000 (low 32 bits)
// x86 addr range: 0x0d120000 - 0x11080000 (low 32 bits)

var ARM_LO_MIN = testcppBase.and(ptr(0xffffffff)).toInt32() >>> 0;
var ARM_LO_MAX = testcppEnd.and(ptr(0xffffffff)).toInt32() >>> 0;
var X86_LO_MIN = cacheStart.and(ptr(0xffffffff)).toInt32() >>> 0;
var X86_LO_MAX = cacheEnd.and(ptr(0xffffffff)).toInt32() >>> 0;

var foundPairs = [];

for (var ri = 0; ri < hRanges.length; ri++) {
    var rng = hRanges[ri];
    var rSize = rng.size;
    var rBase = rng.base;

    send({t: 'log', msg: 'Scanning: ' + rBase + ' (' + (rSize/1024).toFixed(0) + 'KB)...'});

    var chunkSize = 65536; // 64KB chunks
    var offset = 0;

    while (offset < rSize && foundPairs.length < 50) {
        var readSize = Math.min(chunkSize, rSize - offset);
        try {
            var data = rBase.add(offset).readByteArray(readSize);
            if (!data) { offset += chunkSize; continue; }

            var arr = new Uint8Array(data);
            // Scan for 8-byte entries: 4 bytes ARM + 4 bytes x86
            for (var bi = 0; bi + 7 < arr.length; bi += 4) {
                var v1 = arr[bi] | (arr[bi+1] << 8) | (arr[bi+2] << 16) | (arr[bi+3] << 24);
                var v2 = arr[bi+4] | (arr[bi+5] << 8) | (arr[bi+6] << 16) | (arr[bi+7] << 24);

                var inARM = (v1 >= ARM_LO_MIN && v1 <= ARM_LO_MAX);
                var inX86 = (v2 >= X86_LO_MIN && v2 <= X86_LO_MAX);

                if (inARM && inX86) {
                    var armOff = v1 - ARM_LO_MIN;
                    var x86Off = v2 - X86_LO_MIN;
                    var foundAt = rBase.add(offset + bi);
                    foundPairs.push({armOff: armOff, x86Off: x86Off, at: foundAt});
                    if (foundPairs.length <= 10) {
                        send({t: 'log', msg: '  #' + foundPairs.length + ': @' + foundAt + ' ARM+0x' + armOff.toString(16) + ' -> x86+0x' + x86Off.toString(16)});
                    }
                }
            }
        } catch(e) {
            send({t: 'err', msg: 'Read error at ' + rBase.add(offset) + ': ' + e});
        }
        offset += chunkSize;
    }
}

send({t: 'log', msg: 'Total pairs found: ' + foundPairs.length});

// Check against our target functions
var targets = [
    {name: 'jumpUrl', off: 0x000da099},
    {name: 'CCScheduler::update', off: 0x001a28c9},
    {name: 'CCDirector::sharedDirector', off: 0x001b8229},
    {name: 'setAnimationInterval', off: 0x001db495},
];

for (var ti = 0; ti < targets.length; ti++) {
    var t = targets[ti];
    // Look for exact match
    var found = false;
    for (var pi = 0; pi < foundPairs.length; pi++) {
        if (foundPairs[pi].armOff === t.off) {
            send({t: 'log', msg: 'EXACT MATCH: ' + t.name + ' -> x86@cache+0x' + foundPairs[pi].x86Off.toString(16) + ' table@' + foundPairs[pi].at});
            found = true;
        }
    }
    if (!found) {
        // Find closest
        var best = null;
        var bestDiff = 999999999;
        for (var pi = 0; pi < foundPairs.length; pi++) {
            var diff = Math.abs(foundPairs[pi].armOff - t.off);
            if (diff < bestDiff) { bestDiff = diff; best = foundPairs[pi]; }
        }
        if (best) {
            send({t: 'log', msg: 'Closest to ' + t.name + '(+0x' + t.off.toString(16) + '): ARM+0x' + best.armOff.toString(16) + ' diff=' + bestDiff + ' -> x86+0x' + best.x86Off.toString(16)});
        }
    }
}

// Also scan for 8-byte pointer pairs (64-bit format)
send({t: 'log', msg: '--- Scanning for 64-bit pointer pairs ---'});
var found64 = [];

for (var ri = 0; ri < hRanges.length; ri++) {
    var rng = hRanges[ri];
    var rSize = rng.size;
    var rBase = rng.base;

    var chunkSize = 65536;
    var offset = 0;

    while (offset < rSize && found64.length < 20) {
        var readSize = Math.min(chunkSize, rSize - offset);
        try {
            var data = rBase.add(offset).readByteArray(readSize);
            if (!data) { offset += chunkSize; continue; }

            var arr = new Uint8Array(data);
            // Scan for 16-byte entries: 8 bytes ARM ptr + 8 bytes x86 ptr
            for (var bi = 0; bi + 15 < arr.length; bi += 8) {
                // Read as little-endian 64-bit
                var lo1 = arr[bi] | (arr[bi+1] << 8) | (arr[bi+2] << 16) | (arr[bi+3] << 24);
                var hi1 = arr[bi+4] | (arr[bi+5] << 8) | (arr[bi+6] << 16) | (arr[bi+7] << 24);
                var lo2 = arr[bi+8] | (arr[bi+9] << 8) | (arr[bi+10] << 16) | (arr[bi+11] << 24);
                var hi2 = arr[bi+12] | (arr[bi+13] << 8) | (arr[bi+14] << 16) | (arr[bi+15] << 24);

                // Check if v1 is in libtestcpp.so range
                // On 32-bit ARM, the address fits in 32 bits but is stored as 64-bit
                if (hi1 === 0 && lo1 >= ARM_LO_MIN && lo1 <= ARM_LO_MAX) {
                    // Check if v2 is in code cache
                    if (lo2 >= X86_LO_MIN && lo2 <= X86_LO_MAX) {
                        var armOff = lo1 - ARM_LO_MIN;
                        var x86Off = lo2 - X86_LO_MIN;
                        found64.push({armOff: armOff, x86Off: x86Off, at: rBase.add(offset + bi)});
                    }
                }
            }
        } catch(e) {
            // skip
        }
        offset += chunkSize;
    }
}

send({t: 'log', msg: '64-bit pairs found: ' + found64.length});
for (var fi = 0; fi < Math.min(found64.length, 10); fi++) {
    var f = found64[fi];
    send({t: 'log', msg: '  @' + f.at + ' ARM+0x' + f.armOff.toString(16) + ' -> x86+0x' + f.x86Off.toString(16)});
}

// Check against targets for 64-bit
for (var ti = 0; ti < targets.length; ti++) {
    var t = targets[ti];
    for (var pi = 0; pi < found64.length; pi++) {
        if (found64[pi].armOff === t.off) {
            send({t: 'log', msg: '64-BIT MATCH: ' + t.name + ' -> x86@cache+0x' + found64[pi].x86Off.toString(16)});
        }
    }
}

send({t: 'ready', msg: 'All scans complete. 32-bit pairs: ' + foundPairs.length + ', 64-bit pairs: ' + found64.length});
