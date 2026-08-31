// Read strings directly from the jumpUrl pointer table
var base = ptr(0xc074000);

// Addresses from the g_jumpUrlCall table
var addrs = [
    0xc14db8d, 0xc14de1d, 0xc14df85, 0xc14dc8d, 0xc14dca5,
    0xc14dda9, 0xc14e0a3, 0xc14dca9, 0xc14dcc5,
    0xc14db9d, 0xc14de01, 0xc14df4d, 0xc14dcd1, 0xc14dce5,
    0xc14ddb1, 0xc14e019, 0xc14dce9, 0xc14dd05,
    0xc14dbad, 0xc14dde5, 0xc14df15, 0xc14dd11, 0xc14dd25,
    0xc14ddb9, 0xc14e025, 0xc14dd29, 0xc14dd45,
    0xc14dbbd, 0xc14ddc9, 0xc14def9, 0xc14dd51, 0xc14dd65,
    0xc14ddc1, 0xc14e011, 0xc14dd69, 0xc14dd85,
    0xc150685, 0xc1506fd, 0xc150721, 0xc150695, 0xc1506ad,
    0xc1506f5, 0xc1506af, 0xc1506d1, 0xc1506e9,
];

send({t: 'log', msg: '=== Reading strings from g_jumpUrlCall table ==='});

var seen = {};
for (var i = 0; i < addrs.length; i++) {
    var addr = addrs[i];
    if (seen[addr]) continue;
    seen[addr] = true;

    try {
        // Try to read as raw bytes first
        var bytes = ptr(addr).readByteArray(64);
        var arr = new Uint8Array(bytes);

        // Find null terminator
        var nullPos = -1;
        for (var j = 0; j < arr.length; j++) {
            if (arr[j] === 0) { nullPos = j; break; }
        }

        // Try to read as UTF-8 string
        var s = '';
        for (var j = 0; j < (nullPos > 0 ? nullPos : 64); j++) {
            if (arr[j] >= 32 && arr[j] < 127) {
                s += String.fromCharCode(arr[j]);
            } else if (arr[j] === 0) {
                break;
            } else {
                s += '\\x' + ('0' + arr[j].toString(16)).slice(-2);
            }
        }

        // Also show as hex
        var hex = '';
        for (var j = 0; j < Math.min(32, arr.length); j++) {
            hex += ('0' + arr[j].toString(16)).slice(-2) + ' ';
        }

        send({t: 'log', msg: '  0x' + addr.toString(16) + ' (' + s.length + ' chars): "' + s + '"'});
        send({t: 'log', msg: '    hex: ' + hex});
    } catch(e) {
        send({t: 'err', msg: '  0x' + addr.toString(16) + ': ERROR ' + e});
    }
}

// Also try a broader search: find all strings near 0xc14d000 area
send({t: 'log', msg: '=== Sampling strings in .rodata section (0xc14d000-0xc14e100) ==='});
try {
    var rodataStart = ptr(0xc14d000);
    var sample = rodataStart.readByteArray(0x1100);
    var sarr = new Uint8Array(sample);
    var current = '';
    var lastStart = 0;
    for (var bi = 0; bi < sarr.length; bi++) {
        var c = sarr[bi];
        if (c >= 32 && c <= 126) {
            if (current === '') lastStart = bi;
            current += String.fromCharCode(c);
        } else if (c === 0 && current.length > 2) {
            var strAbs = rodataStart.add(lastStart);
            send({t: 'log', msg: '  ' + strAbs + ' (off=0x' + lastStart.toString(16) + '): "' + current + '"'});
            current = '';
        } else {
            current = '';
        }
    }
} catch(e) {
    send({t: 'err', msg: 'Error reading .rodata: ' + e});
}

send({t: 'ready', msg: 'String reading done'});
