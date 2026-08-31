// Read the string table pointed to by g_jumpUrlCall
var base = ptr(0xc074000);

function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

var g_jumpUrlCall = base.add(0x464a18);
var gValPtr = g_jumpUrlCall.readPointer();
send({t: 'log', msg: 'g_jumpUrlCall value: ' + gValPtr});

// Read the first 100 bytes as an array of pointers
var rawData = gValPtr.readByteArray(256);
var arr = new Uint8Array(rawData);

send({t: 'log', msg: '=== Pointer table at g_jumpUrlCall ==='});

for (var i = 0; i < 240; i += 4) {
    var val = arr[i] | (arr[i+1] << 8) | (arr[i+2] << 16) | (arr[i+3] << 24);
    if (val === 0) {
        send({t: 'log', msg: '  [' + (i/4) + '] NULL'});
        continue;
    }
    if (val >= 0x0c074000 && val <= 0x0c4f4000) {
        // In libtestcpp.so range - likely a string pointer
        var strAddr = ptr(val);
        try {
            var s = strAddr.readUtf8String(128);
            send({t: 'log', msg: '  [' + (i/4) + '] 0x' + val.toString(16) + ' -> "' + s + '"'});
        } catch(e) {
            send({t: 'log', msg: '  [' + (i/4) + '] 0x' + val.toString(16) + ' -> (unreadable)'});
        }
    } else {
        send({t: 'log', msg: '  [' + (i/4) + '] 0x' + val.toString(16) + ' (outside libtestcpp.so)'});
    }
}

// Also try to find jlapp_interactivePosition (might tell us position/teleport info)
// and check what calls jlapp_jumpUrl by looking at cross-references
send({t: 'log', msg: '=== Searching for xrefs to jlapp_jumpUrl ==='});

// Search for the absolute address 0xc1ab5d0 in the binary
var targetAbs = 0xc1ab5d0;
var searchSize = 0x480000;
var found = [];

// Search for the 4-byte value in little-endian
var targetBytes = [
    targetAbs & 0xff,
    (targetAbs >> 8) & 0xff,
    (targetAbs >> 16) & 0xff,
    (targetAbs >> 24) & 0xff
];

var chunkSize = 65536;
for (var offset = 0; offset < searchSize; offset += chunkSize) {
    var readSize = Math.min(chunkSize, searchSize - offset);
    try {
        var data = base.add(offset).readByteArray(readSize);
        var darr = new Uint8Array(data);
        for (var bi = 0; bi + 3 < darr.length; bi++) {
            if (darr[bi] === targetBytes[0] &&
                darr[bi+1] === targetBytes[1] &&
                darr[bi+2] === targetBytes[2] &&
                darr[bi+3] === targetBytes[3]) {
                found.push(offset + bi);
                if (found.length >= 20) break;
            }
        }
    } catch(e) {}
    if (found.length >= 20) break;
}

send({t: 'log', msg: 'Found ' + found.length + ' references to 0x' + targetAbs.toString(16)});
for (var fi = 0; fi < found.length; fi++) {
    send({t: 'log', msg: '  offset 0x' + found[fi].toString(16) + ' absolute ' + base.add(found[fi])});
}

// Also check: is there a JNI_OnLoad that registers this function?
// Typical pattern: JNI_OnLoad -> RegisterNatives with method table
// Search for JNI_OnLoad in dynsym
send({t: 'log', msg: '=== Looking for JNI_OnLoad ==='});

function readU16(addr) {
    var bytes = addr.readByteArray(2);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8);
}

var dynstrAddr = 0x2f178;
var dynsymAddr = 0x148;
var symEnt = 16;

for (var si = 0; si < 30000; si++) {
    var sym = base.add(dynsymAddr + si * symEnt);
    var st_name = readU32(sym);
    if (st_name === 0) continue;
    try {
        var name = base.add(dynstrAddr + st_name).readUtf8String(128);
        if (name.indexOf('JNI_OnLoad') !== -1 || name.indexOf('RegisterNatives') !== -1) {
            var st_value = readU32(sym.add(4));
            send({t: 'log', msg: 'FOUND: ' + name + ' @ 0x' + st_value.toString(16)});
        }
        if (name.indexOf('jlapp') !== -1 || name.indexOf('jumpUrl') !== -1 || name.indexOf('jump_url') !== -1) {
            var sv = readU32(sym.add(4));
            send({t: 'log', msg: 'FOUND: ' + name + ' @ 0x' + sv.toString(16)});
        }
    } catch(e) {}
}

send({t: 'ready', msg: 'g_jumpUrlCall analysis done'});
