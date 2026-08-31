var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var pktIdx = 0;

var toHex = function(buf, len) {
    var s = '';
    for (var i = 0; i < len; i++) {
        var b = buf.add(i).readU8();
        s += ('0' + b.toString(16)).slice(-2);
    }
    return s;
};

Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.flags = args[3].toInt32();
    },
    onLeave: function(ret) {
        if (this.fd !== GAME_FD || ret.toInt32() <= 0) return;
        var len = ret.toInt32();
        pktIdx++;
        send({t: 'recv', n: pktIdx, len: len, hex: toHex(this.buf, Math.min(len, 128))});
    }
});

// Also hook send to know when portal packet is sent
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 29 && buf.readU8() === 3) {
            send({t: 'PORTAL_SENT', hex: toHex(buf, 29)});
        }
    }
});

send({t: 'ready', msg: 'RECV sniffer ready. 走传送门！'});
