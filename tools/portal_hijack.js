var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var frozenPayload = null;
var frozen = false;

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD) return;
        if (buf.readU8() !== 3) return;
        var key = buf.add(1).readU8();

        if (len === 30) {
            if (frozen && frozenPayload) {
                for (var i = 0; i < 28; i++) {
                    buf.add(i + 2).writeU8(frozenPayload[i] ^ key);
                }
            } else {
                // Auto-capture first movement packet
                if (!frozenPayload) {
                    frozenPayload = [];
                    for (var i = 0; i < 28; i++) {
                        frozenPayload.push(buf.add(i + 2).readU8() ^ key);
                    }
                    var hex = '';
                    for (var i = 0; i < 28; i++) hex += ('0' + frozenPayload[i].toString(16)).slice(-2);
                    send({t: 'auto_capture', hex: hex});
                }
            }
        }
    }
});

rpc.exports = {
    freeze: function() { frozen = true; return 'OK'; },
    unfreeze: function() { frozen = false; return 'OK'; },
    captureNow: function() {
        frozenPayload = null;  // reset to force re-capture
        return 'RESET';
    }
};

send({t: 'ready', msg: 'Portal hijack ready.'});
