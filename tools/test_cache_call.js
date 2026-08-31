// Test: try to call a translated x86 function in the code cache
// The translation table at 0xe02ee6b0 maps ARM -> x86 addresses
// Entry 0: ARM 0x0c212328 -> x86 0x0d3b4670

var cacheStart = ptr(0x0d120000);
var cacheEnd = ptr(0x11078000);

// Verify code cache is executable
var execRanges = Process.enumerateRanges({protection: 'rwx', coalesce: true});
for (var i = 0; i < execRanges.length; i++) {
    if (execRanges[i].base.compare(cacheStart) >= 0 && execRanges[i].base.compare(cacheEnd) <= 0) {
        send({t: 'log', msg: 'Code cache rwx confirmed: ' + execRanges[i].base + ' size=' + (execRanges[i].size/1048576).toFixed(1) + 'MB'});
    }
}

// Read translation table entry
var tableAddr = ptr(0xe02ee6b0);
var entryBytes = tableAddr.readByteArray(8);
var arr = new Uint8Array(entryBytes);
var armLo = arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
var x86Lo = arr[4] | (arr[5] << 8) | (arr[6] << 16) | (arr[7] << 24);

var armAddr = ptr(armLo);
var x86Addr = cacheStart.add(x86Lo);

send({t: 'log', msg: 'Table entry 0: ARM=' + armAddr + ' x86=' + x86Addr});

// ARM offset in libtestcpp.so
var testcppBase = ptr(0xc074000);
var armOffset = armAddr.sub(testcppBase).toInt32();
send({t: 'log', msg: 'ARM offset: 0x' + armOffset.toString(16)});

// The first 4 bytes of the ARM function — read to understand what it does
try {
    var armCode = armAddr.readByteArray(16);
    var codeArr = new Uint8Array(armCode);
    var hex = '';
    for (var j = 0; j < 16; j++) {
        hex += ('0' + codeArr[j].toString(16)).slice(-2) + ' ';
    }
    send({t: 'log', msg: 'ARM code at ' + armAddr + ': ' + hex});
} catch(e) {
    send({t: 'err', msg: 'Cannot read ARM code: ' + e});
}

// Read the x86 code in the cache
try {
    var x86Code = x86Addr.readByteArray(16);
    var xarr = new Uint8Array(x86Code);
    var xhex = '';
    for (var j = 0; j < 16; j++) {
        xhex += ('0' + xarr[j].toString(16)).slice(-2) + ' ';
    }
    send({t: 'log', msg: 'x86 code at ' + x86Addr + ': ' + xhex});
} catch(e) {
    send({t: 'err', msg: 'Cannot read x86 code: ' + e});
}

// Try to call the x86 function via NativeFunction
// We don't know the signature, so try common Cocos2d-x patterns
send({t: 'log', msg: 'Attempting NativeFunction call...'});

// Many Cocos2d-x functions return pointer and take pointer or nothing
// Try: void* func(void) — common for getInstance / sharedXxx patterns
try {
    var testFn = new NativeFunction(x86Addr, 'pointer', []);
    var result = testFn();
    send({t: 'log', msg: 'Called x86 function! Result: ' + result});

    if (result && !result.isNull()) {
        // Try to read what it points to
        try {
            var pointed = result.readByteArray(32);
            var parr = new Uint8Array(pointed);
            var phex = '';
            for (var j = 0; j < 32; j++) {
                phex += ('0' + parr[j].toString(16)).slice(-2) + ' ';
            }
            send({t: 'log', msg: 'Result points to: ' + phex});
        } catch(e) {
            send({t: 'log', msg: 'Result points to unreadable memory'});
        }
    }
} catch(e) {
    send({t: 'err', msg: 'NativeFunction call failed: ' + e});
}

// Also try calling the ARM function at offset 0x001db495 (setAnimationInterval)
// This takes (CCApplication*, double) and returns void
// First need to get CCApplication instance
// CCDirector::sharedDirector() -> CCApplication::sharedApplication()
// Or we can try reading globals

// Let's search for "CCApplication" string in memory to find the class
send({t: 'log', msg: '--- Searching for Cocos2d-x class strings ---'});
var searchStrings = ['CCApplication', 'CCDirector', 'CCScheduler', 'AppDelegate'];
for (var si = 0; si < searchStrings.length; si++) {
    try {
        Memory.scan(testcppBase, 0x480000, searchStrings[si], {
            onMatch: function(address, size) {
                send({t: 'log', msg: '  Found "' + searchStrings[si] + '" at ' + address});
                return 'stop';
            },
            onError: function(reason) {
                // skip
            },
            onComplete: function() {}
        });
    } catch(e) {
        // Memory.scan might not work with strings this way
        send({t: 'err', msg: 'String scan error: ' + e});
    }
}

send({t: 'ready', msg: 'cache call test done'});
