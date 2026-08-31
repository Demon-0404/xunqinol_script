// Deep exploration: scan code cache for ARM address references
// and probe libhoudini's internal data structures

// Get libtestcpp.so base from memory (not module — not visible via Frida)
// The base was around 0x0c074000 previously. Let's find it dynamically.
var testcppBase = null;

// Method 1: search Process ranges for libtestcpp.so
var ranges = Process.enumerateRanges({protection: 'r--', coalesce: true});
send({t: 'log', msg: 'Searching for libtestcpp.so base...'});
for (var i = 0; i < ranges.length; i++) {
    var baseStr = ranges[i].base.toString();
    // libtestcpp.so is typically at 0x0c000000-0x0c600000 range
    if (baseStr.indexOf('0xc0') === 0 && ranges[i].size > 3000000 && ranges[i].size < 8000000) {
        send({t: 'log', msg: 'Candidate: ' + ranges[i].base + ' size=' + (ranges[i].size/1048576).toFixed(1) + 'MB prot=' + ranges[i].protection});
        // Verify by reading first bytes — ELF header
        try {
            var magic = ranges[i].base.readByteArray(4);
            if (magic) {
                var hex = '';
                var arr = new Uint8Array(magic);
                for (var j = 0; j < arr.length; j++) {
                    hex += ('0' + arr[j].toString(16)).slice(-2);
                }
                send({t: 'log', msg: '  First 4 bytes: ' + hex});
                if (hex === '7f454c46') {
                    testcppBase = ranges[i].base;
                    send({t: 'log', msg: '  >>> FOUND libtestcpp.so ELF at ' + testcppBase + ' <<<'});
                }
            }
        } catch(e) {
            send({t: 'log', msg: '  Error reading: ' + e});
        }
    }
}

if (!testcppBase) {
    send({t: 'err', msg: 'Cannot find libtestcpp.so base'});
} else {
    send({t: 'log', msg: 'libtestcpp.so base = ' + testcppBase});

    // Known ARM function offsets
    var funcs = {
        'jumpUrl': 0x000da099,
        'CCScheduler_update': 0x001a28c9,
        'CCDirector_sharedDirector': 0x001b8229,
        'setAnimationInterval': 0x001db495,
    };

    // Compute full ARM addresses
    var armAddrs = {};
    for (var name in funcs) {
        var addr = testcppBase.add(funcs[name]);
        armAddrs[name] = addr;
        send({t: 'log', msg: 'ARM func ' + name + ' @ ' + addr});
    }

    // Scan code cache for these addresses
    // Code cache: 0x0d120000 - 0x11078000 (rwxp)
    var cacheStart = ptr(0x0d120000);
    var cacheEnd = ptr(0x11078000);
    var cacheSize = cacheEnd.sub(cacheStart).toInt32();

    send({t: 'log', msg: 'Scanning code cache (' + (cacheSize/1048576).toFixed(1) + 'MB) for ARM address references...'});

    // Search for each ARM address as a little-endian 4-byte immediate
    // In x86_64, a mov with immediate would be: 48 B8 <8 bytes> or similar
    // But simpler: search for the 4-byte address value directly
    for (var fname in armAddrs) {
        var target = armAddrs[fname];
        var targetBytes = [
            target.and(0xff).toInt32(),
            target.shr(8).and(0xff).toInt32(),
            target.shr(16).and(0xff).toInt32(),
            target.shr(24).and(0xff).toInt32()
        ];
        var pattern = '';
        for (var b = 0; b < 4; b++) {
            pattern += ('0' + targetBytes[b].toString(16)).slice(-2) + ' ';
        }
        pattern = pattern.trim();
        send({t: 'log', msg: '  Searching for ' + fname + ' pattern: ' + pattern});

        try {
            var matchList = [];
            Memory.scan(cacheStart, cacheSize, pattern, {
                onMatch: function(address, size) {
                    matchList.push(address);
                    if (matchList.length <= 5) {
                        send({t: 'log', msg: '    ' + address + ' (cache+0x' + address.sub(cacheStart).toString(16) + ')'});
                    }
                    return 'stop'; // stop after first match for each
                },
                onError: function(reason) {
                    send({t: 'err', msg: '  Scan error for ' + fname + ': ' + reason});
                },
                onComplete: function() {
                    send({t: 'log', msg: '  ' + matchList.length + ' matches for ' + fname});
                }
            });
        } catch(e) {
            send({t: 'err', msg: '  Scan exception for ' + fname + ': ' + e});
        }
    }
}

// Also: look at libhoudini's internal data
// libhoudini is at 0xdfa8f000, size 10579968 (~10MB)
// Let's look for pointers to the code cache within libhoudini
var houdini = Process.getModuleByName("libhoudini.so");
send({t: 'log', msg: '--- libhoudini data scan ---'});

// Look at .data and .bss sections
var sections = [
    {name: '.got', type: 'pointer array'},
    {name: '.data', type: 'data'},
    {name: '.bss', type: 'bss'},
];

// Actually, enumerate memory ranges that belong to libhoudini
var hStart = houdini.base;
var hEnd = houdini.base.add(houdini.size);
var hRanges = Process.enumerateRanges({protection: 'rw-', coalesce: true});
send({t: 'log', msg: 'libhoudini rw- ranges:'});
for (var hr = 0; hr < hRanges.length; hr++) {
    var rBase = hRanges[hr].base;
    if (rBase.compare(hStart) >= 0 && rBase.compare(hEnd) < 0) {
        send({t: 'log', msg: '  ' + rBase + ' size=' + hRanges[hr].size + ' prot=' + hRanges[hr].protection});
    }
}

send({t: 'ready', msg: 'deep exploration complete'});
