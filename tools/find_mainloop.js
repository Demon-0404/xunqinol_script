var base = ptr(0xc074000);

function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

var dynstrAddr = 0x2f178;
var dynsymAddr = 0x148;

// Find main loop / update / render functions
send({t: 'log', msg: '=== mainLoop, update, render functions ==='});
var found = [];
for (var si = 0; si < 30000; si++) {
    var sym = base.add(dynsymAddr + si * 16);
    var st_name = readU32(sym);
    if (st_name === 0) continue;
    try {
        var sn = base.add(dynstrAddr + st_name).readUtf8String(128);
        if ((sn.indexOf('mainLoop') !== -1 ||
             sn.indexOf('update') !== -1 ||
             sn.indexOf('draw') !== -1 ||
             sn.indexOf('render') !== -1 ||
             sn.indexOf('visit') !== -1) && sn.length < 100) {
            var sv = readU32(sym.add(4));
            var sz = readU32(sym.add(8));
            var msg = sn + ' @ 0x' + sv.toString(16) + ' size=' + sz;
            send({t: 'log', msg: msg});
            found.push({name: sn, value: sv, size: sz});
        }
    } catch(e) {}
}

// Also search for dispatchEvent or handleMessage
send({t: 'log', msg: '=== event/message/notification functions ==='});
for (var si2 = 0; si2 < 30000; si2++) {
    var sym2 = base.add(dynsymAddr + si2 * 16);
    var st_name2 = readU32(sym2);
    if (st_name2 === 0) continue;
    try {
        var sn2 = base.add(dynstrAddr + st_name2).readUtf8String(128);
        if ((sn2.indexOf('dispatch') !== -1 ||
             sn2.indexOf('handle') !== -1 ||
             sn2.indexOf('notif') !== -1 ||
             sn2.indexOf('callback') !== -1 ||
             sn2.indexOf('message') !== -1) && sn2.length < 100) {
            var sv2 = readU32(sym2.add(4));
            var sz2 = readU32(sym2.add(8));
            var msg2 = sn2 + ' @ 0x' + sv2.toString(16) + ' size=' + sz2;
            send({t: 'log', msg: msg2});
            found.push({name: sn2, value: sv2, size: sz2});
        }
    } catch(e) {}
}

send({t: 'ready', msg: 'done, ' + found.length + ' candidates'});
