var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");

var capturedPlain = null;
var captureDone = false;

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
            captureDone = true;
            var hex = '';
            for (var i = 0; i < 27; i++) hex += ('0' + plain[i].toString(16)).slice(-2);
            send({t: 'captured', hex: hex});
        }
    }
});

var sendFunc = new NativeFunction(libc.getExportByName("send"), 'int', ['int', 'pointer', 'int', 'int']);

function doReplay(mutatePos, mutateVal) {
    if (!capturedPlain) return 'NO_DATA';
    var newKey = Math.floor(Math.random() * 256);
    var buf = Memory.alloc(29);
    buf.writeU8(3);
    buf.add(1).writeU8(newKey);
    for (var i = 0; i < 27; i++) {
        var val = capturedPlain[i];
        if (i === mutatePos) val = mutateVal;
        buf.add(i + 2).writeU8(val ^ newKey);
    }
    var ret = sendFunc(GAME_FD, buf, 29, 0);
    return 'SENT ret=' + ret;
}

rpc.exports = {
    replayExact: function() { return doReplay(-1, 0); },
    replayMutate: function(pos, val) { return doReplay(pos, val); },
    hasPacket: function() { return capturedPlain !== null; }
};

send({t: 'ready', msg: 'Mutate replay ready.'});
