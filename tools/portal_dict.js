var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var portalCount = 0;

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD || len !== 29 || buf.readU8() !== 3) return;

        portalCount++;
        var key = buf.add(1).readU8();

        // Decrypt all 27 payload bytes
        var plain = [];
        for (var i = 0; i < 27; i++) {
            plain.push(buf.add(i + 1).readU8() ^ key);
        }

        // First 18 bytes = portal ID (fixed)
        var idHex = '';
        for (var i = 0; i < 18; i++) {
            idHex += ('0' + plain[i].toString(16)).slice(-2);
        }

        // Last 9 bytes = variable data
        var varHex = '';
        for (var i = 18; i < 27; i++) {
            varHex += ('0' + plain[i].toString(16)).slice(-2);
        }

        // Also capture raw encrypted for replay reference
        var rawHex = '';
        for (var i = 0; i < 29; i++) {
            rawHex += ('0' + buf.add(i).readU8().toString(16)).slice(-2);
        }

        send({t: 'portal', n: portalCount, id: idHex, vars: varHex, raw: rawHex, key: key});
    }
});

send({t: 'ready', msg: 'Portal dictionary recorder ready. Walk through portals!'});
