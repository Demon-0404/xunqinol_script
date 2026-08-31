// Analyze jlapp_jumpUrl function in detail
// Decode the literal pool to find what globals it references
var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0); // jlapp_jumpUrl, size=128 bytes

// Read the entire function code
var funcCode = jumpUrlFunc.readByteArray(128);
var arr = new Uint8Array(funcCode);

send({t: 'log', msg: '=== jlapp_jumpUrl full function (128 bytes) ==='});
for (var i = 0; i < 128; i += 16) {
    var hex = '';
    var ascii = '';
    for (var j = 0; j < 16 && (i+j) < 128; j++) {
        hex += ('0' + arr[i+j].toString(16)).slice(-2) + ' ';
        var c = arr[i+j];
        ascii += (c >= 32 && c < 127) ? String.fromCharCode(c) : '.';
    }
    send({t: 'log', msg: '  +0x' + i.toString(16) + ': ' + hex + ' ' + ascii});
}

// Decode the first few instructions to find literal pool references
// Instructions are ARM (not Thumb) based on 4-byte pattern

function readU32At(arr, off) {
    return arr[off] | (arr[off+1] << 8) | (arr[off+2] << 16) | (arr[off+3] << 24);
}

send({t: 'log', msg: '=== Instruction decode ==='});

// 0x00: e9 2d 40 10 → 0xe92d4010
var ins0 = readU32At(arr, 0);
send({t: 'log', msg: '  +0x00: 0x' + ins0.toString(16) + ' → STMFD SP!, {R4, LR}'});

// 0x04: e5 9f 40 60 → 0xe59f4060 → LDR R4, [PC, #0x60]
// This loads from PC+8+0x60 = func_addr+0x04+8+0x60 = func_addr+0x6c
var ldr1Off = 0x04 + 8 + 0x60; // 0x6c
var ldr1Addr = jumpUrlFunc.add(ldr1Off);
var ldr1Val = readU32At(arr, ldr1Off);
send({t: 'log', msg: '  +0x04: LDR R4, [PC, #0x60] → loads from +0x' + ldr1Off.toString(16) + ' = ' + ldr1Addr + ' → value at literal: 0x' + ldr1Val.toString(16)});

// 0x08: e5 9f 30 60 → 0xe59f3060 → LDR R3, [PC, #0x60]
var ldr2Off = 0x08 + 8 + 0x60; // 0x70
var ldr2Addr = jumpUrlFunc.add(ldr2Off);
var ldr2Val = readU32At(arr, ldr2Off);
send({t: 'log', msg: '  +0x08: LDR R3, [PC, #0x60] → loads from +0x' + ldr2Off.toString(16) + ' = ' + ldr2Addr + ' → value at literal: 0x' + ldr2Val.toString(16)});

// 0x0c: e2 4d d0 08 → SUB SP, SP, #8
// 0x10: e0 8f 40 04 → ADD R4, PC, R4
// At this point, PC = func+0x10+8 = func+0x18
// R4 = func+0x18 + ldr1Val
var r4Final = jumpUrlFunc.add(0x18 + ldr1Val);
send({t: 'log', msg: '  +0x10: ADD R4, PC, R4 → R4 = PC + ' + ldr1Val.toString(16) + ' = ' + r4Final});

// 0x14: e7 94 30 03 → LDR R3, [R4, R3] → R3 = *(R4 + ldr2Val)
var r3Target = r4Final.add(ldr2Val);
send({t: 'log', msg: '  +0x14: LDR R3, [R4, R3] → loads from ' + r3Target});

// Read the actual value at that target
try {
    var r3Actual = r3Target.readPointer();
    send({t: 'log', msg: '    R3 actual value (pointer): ' + r3Actual});

    // Read what R3 points to (offset 0x10)
    try {
        var r3p10 = r3Actual.add(0x10).readPointer();
        send({t: 'log', msg: '    *(R3 + 0x10) = ' + r3p10});

        // Read what R3 points to (offset 0x00) - the object itself
        var r3p0Data = r3Actual.readByteArray(64);
        var r3arr = new Uint8Array(r3p0Data);
        var r3Hex = '';
        for (var ri = 0; ri < 64; ri++) {
            r3Hex += ('0' + r3arr[ri].toString(16)).slice(-2) + ' ';
        }
        send({t: 'log', msg: '    Data at R3: ' + r3Hex});
    } catch(e) {
        send({t: 'err', msg: '    Error reading R3+0x10: ' + e});
    }
} catch(e) {
    send({t: 'err', msg: '  Error reading R3 target: ' + e});
}

// Also read all the literal pool values (from offset 0x6c to 0x7f)
send({t: 'log', msg: '=== Literal pool (offsets 0x60-0x7f) ==='});
for (var lp = 0x60; lp < 0x80; lp += 4) {
    var lpVal = readU32At(arr, lp);
    send({t: 'log', msg: '  +0x' + lp.toString(16) + ': 0x' + lpVal.toString(16) + ' (' + lpVal + ')'});

    // If value is in libtestcpp.so range, try to read as pointer
    if (lpVal >= 0x0c074000 && lpVal <= 0x0c4f4000) {
        try {
            var pointed = ptr(lpVal).readPointer();
            send({t: 'log', msg: '    → points to: ' + pointed});
        } catch(e) {}
        try {
            var pointedStr = ptr(lpVal).readUtf8String(64);
            send({t: 'log', msg: '    → string: "' + pointedStr + '"'});
        } catch(e) {}
    }
}

// Also try to find JNI_OnLoad which registers the native methods
// and may give us the Java class context
send({t: 'log', msg: '=== Searching for JNI_OnLoad in dynsym ==='});
var dynstrAddr = 0x2f178;
var dynsymAddr = 0x148;

function readU32Raw(addr) {
    var bytes = addr.readByteArray(4);
    var a = new Uint8Array(bytes);
    return a[0] | (a[1] << 8) | (a[2] << 16) | (a[3] << 24);
}

for (var si = 0; si < 30000; si++) {
    var sym = base.add(dynsymAddr + si * 16);
    var st_name = readU32Raw(sym);
    if (st_name === 0) continue;
    try {
        var sn = base.add(dynstrAddr + st_name).readUtf8String(128);
        if (sn.indexOf('JNI_OnLoad') !== -1) {
            var sv = readU32Raw(sym.add(4));
            send({t: 'log', msg: 'FOUND: ' + sn + ' @ 0x' + sv.toString(16)});
        }
    } catch(e) {}
}

send({t: 'ready', msg: 'jlapp_jumpUrl analysis complete'});
