var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");

var lastMove = null;
var lastMoveTime = 0;

var arrToHex = function(arr) {
    var s = '';
    for (var i = 0; i < arr.length; i++) {
        s += ('0' + arr[i].toString(16)).slice(-2);
    }
    return s;
};

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD) return;
        if (buf.readU8() !== 3) return;

        var key = buf.add(1).readU8();
        var payloadLen = len - 2;

        var plain = [];
        for (var i = 0; i < payloadLen; i++) {
            plain.push(buf.add(i + 2).readU8() ^ key);
        }
        var plainHex = arrToHex(plain);

        // 记录所有 len=30 (movement) 和 len=29 (portal)
        if (len === 30) {
            lastMove = plainHex;
            lastMoveTime = Date.now();
        }

        if (len === 29) {
            send({t: 'portal', plain: plainHex});
            if (lastMove) {
                send({t: 'move', plain: lastMove});
            } else {
                send({t: 'move', plain: 'NONE'});
            }
        }
    }
});

send({t: 'ready', msg: 'Tracker v2 ready. 先走几步，再走传送门！'});
