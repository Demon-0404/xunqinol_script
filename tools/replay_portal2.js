var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");

var capturedPlain = null;
var capturedHex = '';
var captureDone = false;

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

        if (buf.readU8() === 3 && len === 29 && !captureDone) {
            var key = buf.add(1).readU8();
            var plain = [];
            for (var i = 0; i < 27; i++) {
                plain.push(buf.add(i + 2).readU8() ^ key);
            }
            capturedPlain = plain;
            capturedHex = arrToHex(plain);
            captureDone = true;
            send({t: 'captured', hex: capturedHex});
        }
    }
});

var sendFunc = new NativeFunction(libc.getExportByName("send"), 'int', ['int', 'pointer', 'int', 'int']);

rpc.exports = {
    replay: function() {
        if (!capturedPlain) {
            send({t: 'err', msg: 'No portal captured yet!'});
            return 'NO_DATA';
        }
        var newKey = Math.floor(Math.random() * 256);
        var buf = Memory.alloc(29);
        buf.writeU8(3);
        buf.add(1).writeU8(newKey);
        for (var i = 0; i < 27; i++) {
            buf.add(i + 2).writeU8(capturedPlain[i] ^ newKey);
        }
        var ret = sendFunc(GAME_FD, buf, 29, 0);
        send({t: 'replay', key: newKey, ret: ret});
        return 'SENT';
    },
    hasPacket: function() {
        return capturedPlain !== null;
    }
};

send({t: 'ready', msg: 'Replay script ready. 先走一次传送门捕获，然后走到别处重放！'});
