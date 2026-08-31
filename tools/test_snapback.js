var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var frozenPayload = null;
var frozen = false;
var moveCount = 0;
var posList = [];  // record recent positions

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
                moveCount++;
                if (moveCount %% 10 === 1) send({t: 'fr', n: moveCount});
            }
            // Always record
            if (!frozen) {
                var hex = '';
                for (var i = 0; i < 28; i++) hex += ('0' + (buf.add(i + 2).readU8() ^ key).toString(16)).slice(-2);
                posList.push(hex);
                if (posList.length > 5) posList.shift();
            }
        }
    }
});

rpc.exports = {
    freeze: function() {
        // Use latest recorded position
        if (posList.length > 0) {
            var hex = posList[posList.length - 1];
            frozenPayload = [];
            for (var i = 0; i < hex.length; i += 2) {
                frozenPayload.push(parseInt(hex.substring(i, i + 2), 16));
            }
            send({t: 'frz', hex: hex});
        }
        frozen = true;
        moveCount = 0;
        return 'OK';
    },
    unfreeze: function() {
        frozen = false;
        send({t: 'ufr', frozenCount: moveCount});
        return 'OK';
    }
};

send({t: 'ready', msg: 'Snapback test ready.'});
