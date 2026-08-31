var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var captureUntil = 0;
var capturedPackets = [];

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 29 && buf.readU8() === 3) {
            captureUntil = Date.now() + 5000;
            capturedPackets = [];
            send({t: 'portal_detected'});
        }
    }
});

Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        var now = Date.now();
        if (this.fd === GAME_FD && now < captureUntil && captureUntil > 0) {
            this.doSave = true;
        }
    },
    onLeave: function(ret) {
        if (!this.doSave) return;
        var len = ret.toInt32();
        if (len <= 0) return;

        var hex = '';
        var maxRead = Math.min(len, 4096);
        for (var i = 0; i < maxRead; i++) {
            hex += ('0' + this.buf.add(i).readU8().toString(16)).slice(-2);
        }
        capturedPackets.push({len: len, hex: hex});
        send({t: 'recv', n: capturedPackets.length, len: len, hex: hex.substring(0, 80)});
    }
});

rpc.exports = {
    getPackets: function() { return capturedPackets; }
};

send({t: 'ready', msg: 'Capture v2 ready. Walk portal!'});
