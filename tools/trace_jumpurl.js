// Trace jlapp_jumpUrl internal state to find exact crash point
var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0);

Memory.protect(jumpUrlFunc.and(ptr(0xfffff000)), 4096, 'rwx');
send({t: 'log', msg: 'Page rwx'});

// Read the literal pool and compute global addresses
function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

// Read the function's literal pool (at offsets 0x6c-0x7f)
send({t: 'log', msg: '=== Function literal pool ==='});
var lpOffsets = [0x6c, 0x70, 0x74, 0x78, 0x7c];
for (var li = 0; li < lpOffsets.length; li++) {
    var off = lpOffsets[li];
    var lpVal = readU32(jumpUrlFunc.add(off));
    var signed = lpVal | 0; // force signed 32-bit
    send({t: 'log', msg: '  +0x' + off.toString(16) + ': 0x' + lpVal.toString(16) + ' (' + signed + ')'});
}

// Compute the global address (step 0x10-0x14 in function)
// R4 = PC + literal[0x6c]
// PC at instruction +0x10 is func + 0x18
// R4 = base + 0x1375d0 + 0x18 + literal[0x6c]
var literal6c = readU32(jumpUrlFunc.add(0x6c));
var r4 = jumpUrlFunc.add(0x18 + literal6c);
send({t: 'log', msg: 'R4 = ' + r4});

// R3_offset = literal[0x70] (signed)
var literal70 = readU32(jumpUrlFunc.add(0x70));
var signed70 = literal70 | 0; // treat as signed 32-bit
send({t: 'log', msg: 'R3_offset = ' + signed70 + ' (0x' + literal70.toString(16) + ')'});

// R3_ptr = R4 + R3_offset
var r3Ptr = r4.add(signed70);
send({t: 'log', msg: 'R3_ptr = ' + r3Ptr});

// Read R3 value = *R3_ptr (this is the global object)
var globalObj = r3Ptr.readPointer();
send({t: 'log', msg: 'Global object = ' + globalObj});

// Read *(globalObj + 0x10) — this is checked against 0
var handlerObj = globalObj.add(0x10).readPointer();
send({t: 'log', msg: 'handlerObj (global+0x10) = ' + handlerObj});

if (handlerObj.isNull()) {
    send({t: 'log', msg: 'BEO PATH: handlerObj is NULL, takes error path at +0x40'});
    send({t: 'log', msg: 'This means the error path code at +0x40 is crashing!'});

    // Let's read the error path code
    send({t: 'log', msg: '=== Error path code (+0x40 to +0x6b) ==='});
    var errCode = jumpUrlFunc.add(0x40).readByteArray(0x2c);
    var earr = new Uint8Array(errCode);
    var ehex = '';
    for (var i = 0; i < 0x2c; i++) {
        ehex += ('0' + earr[i].toString(16)).slice(-2) + ' ';
        if ((i + 1) % 16 === 0) ehex += '\n          ';
    }
    send({t: 'log', msg: ehex});
} else {
    send({t: 'log', msg: 'NON-ZERO PATH: handlerObj != 0, calls vtable method'});

    // Read vtable
    var vtable = handlerObj.readPointer();
    send({t: 'log', msg: 'vtable = ' + vtable});

    var vt6 = vtable.add(0x18).readPointer();
    send({t: 'log', msg: 'vtable[6] = ' + vt6});

    // Also read handlerObj data
    var hoData = handlerObj.readByteArray(64);
    var hoArr = new Uint8Array(hoData);
    var hoHex = '';
    for (var i = 0; i < 64; i++) {
        hoHex += ('0' + hoArr[i].toString(16)).slice(-2) + ' ';
        if ((i + 1) % 16 === 0) hoHex += '\n          ';
    }
    send({t: 'log', msg: 'handlerObj data:\n          ' + hoHex});
}

// Now call it
var testUrl = Memory.allocUtf8String('xqj://test');
send({t: 'log', msg: '=== CALLING ==='});
try {
    var fn = new NativeFunction(jumpUrlFunc, 'void', ['pointer']);
    fn(testUrl);
    send({t: 'log', msg: 'OK'});
} catch(e) {
    send({t: 'err', msg: 'CRASH: ' + e});
}

send({t: 'ready', msg: 'done'});
