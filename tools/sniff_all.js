var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var count = 0;
var lastTime = Date.now();

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD) return;
        if (len > 200) return; // skip large packets (probably assets)

        count++;
        var now = Date.now();
        var elapsed = now - lastTime;
        lastTime = now;

        var raw = [];
        var maxRead = Math.min(len, 64);
        for (var i = 0; i < maxRead; i++) {
            raw.push(buf.add(i).readU8());
        }

        var hex = '';
        for (var i = 0; i < raw.length; i++) {
            hex += ('0' + raw[i].toString(16)).slice(-2);
            if (i < raw.length - 1) hex += ' ';
        }

        // Try to decrypt if type 3 (position packet)
        var decInfo = '';
        if (raw[0] === 3 && len === 30 && raw.length >= 29) {
            var key = raw[1];
            var dec = [];
            for (var i = 1; i < 29; i++) dec.push(raw[i] ^ key);
            var decHex = '';
            for (var i = 0; i < dec.length; i++) {
                decHex += ('0' + dec[i].toString(16)).slice(-2) + ' ';
            }
            decInfo = ' | dec: ' + decHex;
        }

        send({t: 'send', n: count, len: len, dt: elapsed, hex: hex, dec: decInfo});
    }
});

send({t: 'ready', msg: 'Sniffing all packets. Walk through a portal now!'});
