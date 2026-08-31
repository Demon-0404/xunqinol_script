// Dump ALL libhoudini.so exports and look for dispatch/translation APIs
var houdini = Process.getModuleByName("libhoudini.so");

var exports = houdini.enumerateExports();
send({t: 'log', msg: '=== ALL ' + exports.length + ' libhoudini exports ==='});

// Sort by address
exports.sort(function(a, b) {
    return a.address.compare(b.address);
});

for (var i = 0; i < exports.length; i++) {
    var e = exports[i];
    var offset = e.address.sub(houdini.base).toInt32();
    send({t: 'log', msg: '  [0x' + offset.toString(16) + '] ' + e.type + ' ' + e.name});
}

// Now, let's look at the table entries more carefully
// First entry at 0xe02ee6b0 in houdini's rw- memory
var tableAddr = ptr(0xe02ee6b0);
send({t: 'log', msg: '=== Examining table at ' + tableAddr + ' ==='});

// Read 16 entries (8 bytes each — might be struct with more fields)
for (var i = 0; i < 16; i++) {
    var addr = tableAddr.add(i * 8);
    try {
        var bytes = addr.readByteArray(8);
        if (bytes) {
            var arr = new Uint8Array(bytes);
            var hex = '';
            for (var j = 0; j < 8; j++) {
                hex += ('0' + arr[j].toString(16)).slice(-2);
            }
            var lo = arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
            var hi = arr[4] | (arr[5] << 8) | (arr[6] << 16) | (arr[7] << 24);
            send({t: 'log', msg: '  [' + i + '] @' + addr + ': ' + hex + ' lo=0x' + lo.toString(16) + ' hi=0x' + hi.toString(16)});
        }
    } catch(e) {
        send({t: 'log', msg: '  [' + i + '] @' + addr + ': <error ' + e + '>'});
    }
}

// Also check if there's a larger structure before the table entries
// Look for magic numbers or table headers
var tableRegion = ptr(0xe02ee000);
try {
    var headerBytes = tableRegion.readByteArray(256);
    var arr = new Uint8Array(headerBytes);
    var hex = '';
    for (var j = 0; j < 256; j += 16) {
        var line = ('0000' + j.toString(16)).slice(-4) + ': ';
        for (var k = 0; k < 16 && (j + k) < 256; k++) {
            line += ('0' + arr[j + k].toString(16)).slice(-2) + ' ';
        }
        send({t: 'log', msg: line});
    }
} catch(e) {
    send({t: 'err', msg: 'Header error: ' + e});
}

send({t: 'ready', msg: 'all exports dumped'});
