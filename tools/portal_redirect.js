var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");

// 两个传送门的目的地坐标（VAR 后4字节）
var DEST_A = [0xd9, 0xcf, 0xd9, 0xcf];  // 传送门A的目的地
var DEST_B = [0xcb, 0xdd, 0xcb, 0xdd];  // 传送门B的目的地

function bytesMatch(arr, idx, target) {
    for (var i = 0; i < target.length; i++) {
        if (arr[idx + i] !== target[i]) return false;
    }
    return true;
}

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD || len !== 29 || buf.readU8() !== 3) return;

        var key = buf.add(1).readU8();

        // 解密全部27字节payload
        var plain = [];
        for (var i = 0; i < 27; i++) {
            plain.push(buf.add(i + 2).readU8() ^ key);
        }

        // plain[23..26] = VAR后4字节（目的地坐标）
        var targetDest = null;
        var label = '';

        if (bytesMatch(plain, 23, DEST_A)) {
            targetDest = DEST_B;
            label = 'A->B';
        } else if (bytesMatch(plain, 23, DEST_B)) {
            targetDest = DEST_A;
            label = 'B->A';
        }

        if (targetDest) {
            // 直接修改加密缓冲区（buf[25..28]）
            for (var i = 0; i < 4; i++) {
                buf.add(25 + i).writeU8(targetDest[i] ^ key);
            }
            send({t: 'ok', msg: 'REDIRECT ' + label});
        }
    }
});

send({t: 'ready', msg: 'Portal redirect hook ready! 走传送门A会被传到B的目的地，反之亦然。'});
