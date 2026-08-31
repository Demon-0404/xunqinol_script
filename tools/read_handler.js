// Read the handler vtable entry that jlapp_jumpUrl calls
var base = ptr(0xc074000);

function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

// From analysis: handler object at 0xc4d8a18
// vtable at *(0xc4d8a18) = 0x0c4ba1e8
// vtable[6] at *(0x0c4ba1e8 + 0x18) = *(0x0c4ba200)

var vtableAddr = ptr(0xc4ba1e8);
send({t: 'log', msg: 'vtable base: ' + vtableAddr});

// Read vtable entries
send({t: 'log', msg: '=== Vtable entries ==='});
for (var vi = 0; vi < 12; vi++) {
    var off = vi * 4;
    var val = readU32(vtableAddr.add(off));
    if (val >= 0x0c074000 && val <= 0x0c4f4000) {
        // Read code at handler
        try {
            // Clear bit 0 for Thumb addresses
            var codeAddr = ptr(val);
            if (val & 1) {
                codeAddr = ptr(val - 1);
            }
            var hcode = codeAddr.readByteArray(32);
            var harr = new Uint8Array(hcode);
            var hhex = '';
            for (var hi = 0; hi < 32; hi++) {
                hhex += ('0' + harr[hi].toString(16)).slice(-2) + ' ';
            }
            var thumb = (val & 1) ? 'T' : 'A';
            send({t: 'log', msg: '  [' + vi + '] 0x' + val.toString(16) + '(' + thumb + '): ' + hhex});
        } catch(e) {
            send({t: 'log', msg: '  [' + vi + '] 0x' + val.toString(16) + ' -> error: ' + e});
        }
    } else {
        send({t: 'log', msg: '  [' + vi + '] 0x' + val.toString(16) + ' (outside range)'});
    }
}

// Read the handler at vtable[6] in detail
var handlerVal = readU32(ptr(0xc4ba200));
send({t: 'log', msg: '=== Handler at vtable[6] = 0x' + handlerVal.toString(16) + ' ==='});

var handlerCodeAddr;
if (handlerVal & 1) {
    handlerCodeAddr = ptr(handlerVal - 1);
} else {
    handlerCodeAddr = ptr(handlerVal);
}
var isThumb = (handlerVal & 1) === 1;
send({t: 'log', msg: 'Code addr: ' + handlerCodeAddr + ' (Thumb=' + isThumb + ')');

try {
    var hcode = handlerCodeAddr.readByteArray(64);
    var harr = new Uint8Array(hcode);
    var hhex = '';
    for (var hi = 0; hi < 64; hi++) {
        hhex += ('0' + harr[hi].toString(16)).slice(-2) + ' ';
        if ((hi + 1) % 16 === 0) {
            hhex += '\n          ';
        }
    }
    send({t: 'log', msg: 'Handler code:\n          ' + hhex});
} catch(e) {
    send({t: 'err', msg: 'Cannot read handler code: ' + e});
}

// Find CCScheduler::update via direct string offset
var dynstrAddr = 0x2f178;
var dynsymAddr = 0x148;
var targetStrOff = 0x323c6; // _ZN7cocos2d11CCScheduler6updateEf
var targetNameIdx = targetStrOff - dynstrAddr;

send({t: 'log', msg: '=== Looking for CCScheduler::update (st_name=' + targetNameIdx + ') ==='});

for (var si = 0; si < 40000; si++) {
    var sym = base.add(dynsymAddr + si * 16);
    var st_name = readU32(sym);
    if (st_name === targetNameIdx) {
        var sv = readU32(sym.add(4));
        var sz = readU32(sym.add(8));
        send({t: 'log', msg: 'FOUND CCScheduler::update: st_value=0x' + sv.toString(16) + ' size=' + sz});
        send({t: 'log', msg: '  Absolute: ' + base.add(sv)});
        break;
    }
}

// List all "shared" functions
send({t: 'log', msg: '=== All "shared" functions in dynsym ==='});
for (var si2 = 0; si2 < 30000; si2++) {
    var sym2 = base.add(dynsymAddr + si2 * 16);
    var st_name2 = readU32(sym2);
    if (st_name2 === 0) continue;
    try {
        var sn2 = base.add(dynstrAddr + st_name2).readUtf8String(128);
        if (sn2.indexOf('shared') !== -1 && sn2.length < 100) {
            var sv2 = readU32(sym2.add(4));
            send({t: 'log', msg: '  ' + sn2 + ' @ 0x' + sv2.toString(16)});
        }
    } catch(e) {}
}

send({t: 'ready', msg: 'Handler analysis done'});
