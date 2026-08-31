var base = ptr(0xc074000);

function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

// Read vtable entries
var vtableAddr = ptr(0xc4ba1e8);
var entries = [];
for (var vi = 0; vi < 12; vi++) {
    var val = readU32(vtableAddr.add(vi * 4));
    entries.push(val);
    var msg = 'vtable[' + vi + '] = 0x' + val.toString(16);
    send({t: 'log', msg: msg});
}

// Read handler code at vtable[6] = 0xc4ba200
var handlerVal = readU32(ptr(0xc4ba200));
var msg2 = 'Handler vtable[6] = 0x' + handlerVal.toString(16);
send({t: 'log', msg: msg2});

// Read code
var codeAddr;
if (handlerVal & 1) {
    codeAddr = ptr(handlerVal - 1);
} else {
    codeAddr = ptr(handlerVal);
}
var msg3 = 'Code at ' + codeAddr;
send({t: 'log', msg: msg3});

try {
    var hcode = codeAddr.readByteArray(32);
    var harr = new Uint8Array(hcode);
    var hhex = '';
    for (var hi = 0; hi < 32; hi++) {
        hhex += ('0' + harr[hi].toString(16)).slice(-2);
        hhex += ' ';
    }
    send({t: 'log', msg: hhex});
} catch(e) {
    send({t: 'err', msg: 'read error'});
}

// Find CCScheduler::update
var dynstrAddr = 0x2f178;
var dynsymAddr = 0x148;
var targetNameIdx = 0x323c6 - dynstrAddr;

send({t: 'log', msg: 'Searching CCScheduler with name_idx=' + targetNameIdx});

var foundSched = false;
for (var si = 0; si < 40000; si++) {
    var sym = base.add(dynsymAddr + si * 16);
    var st_name = readU32(sym);
    if (st_name === targetNameIdx) {
        var sv = readU32(sym.add(4));
        var sz = readU32(sym.add(8));
        var msg4 = 'FOUND @ 0x' + sv.toString(16) + ' size=' + sz;
        send({t: 'log', msg: msg4});
        foundSched = true;
        break;
    }
}
if (!foundSched) {
    send({t: 'log', msg: 'CCScheduler::update NOT FOUND in dynsym'});
}

// List shared functions
send({t: 'log', msg: '=== shared functions ==='});
var count = 0;
for (var si2 = 0; si2 < 30000; si2++) {
    var sym2 = base.add(dynsymAddr + si2 * 16);
    var st_name2 = readU32(sym2);
    if (st_name2 === 0) continue;
    try {
        var sn2 = base.add(dynstrAddr + st_name2).readUtf8String(128);
        if (sn2.indexOf('shared') !== -1 && sn2.length < 100) {
            var sv2 = readU32(sym2.add(4));
            var msg5 = sn2 + ' @ 0x' + sv2.toString(16);
            send({t: 'log', msg: msg5});
            count++;
            if (count > 20) break;
        }
    } catch(e) {}
}

send({t: 'ready', msg: 'done'});
