// Scan the ENTIRE translation table in libhoudini's writable memory
// Looking for entries near our target function offsets

var testcppBase = ptr(0xc074000);
var cacheStart = ptr(0x0d120000);
var cacheEnd = ptr(0x11078000);

// Target ARM offsets (in libtestcpp.so)
var targets = [
    {name: 'jumpUrl', off: 0x000da099},
    {name: 'CCScheduler::update', off: 0x001a28c9},
    {name: 'CCDirector::sharedDirector', off: 0x001b8229},
    {name: 'setAnimationInterval', off: 0x001db495},
];

// Scan the first writable range of libhoudini more thoroughly
// The table is at 0xe02ee6b0 area, but let's scan a wider range
var scanStart = ptr(0xe0142000); // start of first rw- range
var scanSize = 2 * 1024 * 1024; // 2MB

send({t: 'log', msg: 'Scanning ' + scanStart + ' size=2MB for translation entries...'});

var allEntries = [];

var chunkSize = 65536;
var offset = 0;
var skipped = 0;

while (offset < scanSize) {
    var readSize = Math.min(chunkSize, scanSize - offset);
    try {
        var data = scanStart.add(offset).readByteArray(readSize);
        if (!data) { offset += chunkSize; continue; }

        var arr = new Uint8Array(data);
        // Look for 8-byte entries: 4 bytes ARM addr + 4 bytes x86 addr
        for (var bi = 0; bi + 7 < arr.length; bi += 4) {
            var armVal = arr[bi] | (arr[bi+1] << 8) | (arr[bi+2] << 16) | (arr[bi+3] << 24);
            var x86Val = arr[bi+4] | (arr[bi+5] << 8) | (arr[bi+6] << 16) | (arr[bi+7] << 24);

            // ARM addr must be in libtestcpp.so range
            if (armVal >= 0x0c074000 && armVal <= 0x0c4f4000) {
                // x86 must be in code cache
                if (x86Val >= 0x0d120000 && x86Val <= 0x11080000) {
                    var armOff = armVal - 0x0c074000;
                    var entry = {
                        armOff: armOff,
                        x86Addr: x86Val,
                        tableAddr: scanStart.add(offset + bi)
                    };
                    allEntries.push(entry);
                }
            }
        }
    } catch(e) {
        skipped++;
    }
    offset += chunkSize;

    // Progress update
    if (offset % (256 * 1024) < chunkSize) {
        send({t: 'log', msg: '  Progress: ' + (offset / 1048576).toFixed(1) + 'MB, found ' + allEntries.length + ' entries'});
    }
}

send({t: 'log', msg: 'Total entries: ' + allEntries.length + ' (skipped ' + skipped + ' chunks)'});

// Check against targets
for (var ti = 0; ti < targets.length; ti++) {
    var t = targets[ti];
    var exactMatches = [];
    var closeMatches = [];

    for (var ei = 0; ei < allEntries.length; ei++) {
        var diff = allEntries[ei].armOff - t.off;
        if (diff === 0) {
            exactMatches.push(allEntries[ei]);
        }
        if (Math.abs(diff) < 0x200) {
            closeMatches.push({entry: allEntries[ei], diff: diff});
        }
    }

    if (exactMatches.length > 0) {
        send({t: 'log', msg: '*** EXACT MATCH for ' + t.name + ' (0x' + t.off.toString(16) + '):'});
        for (var emi = 0; emi < exactMatches.length; emi++) {
            var em = exactMatches[emi];
            send({t: 'log', msg: '    x86=0x' + em.x86Addr.toString(16) + ' table@' + em.tableAddr});
        }
    } else {
        send({t: 'log', msg: 'No exact match for ' + t.name + ' (0x' + t.off.toString(16) + ')'});
        if (closeMatches.length > 0) {
            closeMatches.sort(function(a, b) { return Math.abs(a.diff) - Math.abs(b.diff); });
            send({t: 'log', msg: '  Closest ' + Math.min(5, closeMatches.length) + ' entries:'});
            for (var ci = 0; ci < Math.min(5, closeMatches.length); ci++) {
                var cm = closeMatches[ci];
                send({t: 'log', msg: '    ARM+0x' + cm.entry.armOff.toString(16) + ' (diff=' + cm.diff + ') -> x86@0x' + cm.entry.x86Addr.toString(16)});
            }
        } else {
            send({t: 'log', msg: '  No entries within +/-0x200 of target'});
        }
    }
}

// Also show distribution of ARM offsets to understand what's being cached
send({t: 'log', msg: 'ARM offset distribution (first ' + Math.min(10, allEntries.length) + '):'});
for (var di = 0; di < Math.min(10, allEntries.length); di++) {
    var e = allEntries[di];
    send({t: 'log', msg: '  ARM+0x' + e.armOff.toString(16) + ' -> x86@0x' + e.x86Addr.toString(16) + ' (table@' + e.tableAddr + ')'});
}

send({t: 'ready', msg: 'Full table scan complete. ' + allEntries.length + ' entries found.'});
