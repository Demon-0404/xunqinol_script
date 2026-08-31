var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var count = 0;
var lastTime = Date.now();

var toHex = function(buf, len) {
    var maxRead = Math.min(len, 64);
    var hex = '';
    for (var i = 0; i < maxRead; i++) {
        var b = buf.add(i).readU8();
        hex += ('0' + b.toString(16)).slice(-2);
        if (i < maxRead - 1) hex += ' ';
    }
    return hex;
};

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD || len > 200) return;

        count++;
        var now = Date.now();
        var dt = now - lastTime;
        lastTime = now;

        var hex = toHex(buf, len);
        send({t: 'SEND', n: count, len: len, dt: dt, hex: hex});
    }
});

Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.len = args[2].toInt32();
    },
    onLeave: function(ret) {
        var n = ret.toInt32();
        if (this.fd !== GAME_FD || n <= 0 || n > 200) return;

        count++;
        var now = Date.now();
        var dt = now - lastTime;
        lastTime = now;

        var hex = toHex(this.buf, n);
        send({t: 'RECV', n: count, len: n, dt: dt, hex: hex});
    }
});

send({t: 'ready', msg: 'SEND+RECV sniffer ready. Go through a portal!'});
