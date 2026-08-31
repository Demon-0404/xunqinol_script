var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var portalPlaintext = null;  // decrypted portal packet payload
var portalLen = 0;

var send_func = new NativeFunction(libc.getExportByName("send"), 'int', ['int', 'pointer', 'int', 'int']);

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD || len > 200) return;

        var first = buf.readU8();

        // Log unusual packets
        if (len !== 30 && len !== 17) {
            var raw = [];
            for (var i = 0; i < Math.min(len, 40); i++) {
                raw.push(buf.add(i).readU8());
            }
            var hex = '';
            for (var i = 0; i < raw.length; i++) {
                hex += ('0' + raw[i].toString(16)).slice(-2) + ' ';
            }
            send({t: 'unusual', len: len, first: first, hex: hex.trim()});
        }

        // Capture len=29 portal packet - store DECRYPTED plaintext
        if (len === 29 && first === 3) {
            var key = buf.add(1).readU8();
            portalLen = len;
            // Store plaintext (without the 0x03 type byte, but with key slot)
            portalPlaintext = [];
            for (var i = 0; i < len; i++) {
                if (i === 0) {
                    portalPlaintext.push(0x03); // type stays
                } else if (i === 1) {
                    portalPlaintext.push(0x00); // placeholder for new key
                } else {
                    portalPlaintext.push(buf.add(i).readU8() ^ key);
                }
            }
            send({t: 'captured', len: len, key: key});
        }
    }
});

rpc.exports = {
    replay: function(newKey) {
        if (portalPlaintext === null) {
            send({t: 'error', msg: 'No portal packet captured!'});
            return 'no_packet';
        }
        // Construct packet with new key
        var buf = Memory.alloc(portalLen);
        for (var i = 0; i < portalLen; i++) {
            if (i === 1) {
                buf.add(i).writeU8(newKey & 0xFF);
            } else if (i === 0) {
                buf.add(i).writeU8(portalPlaintext[i]);
            } else {
                buf.add(i).writeU8(portalPlaintext[i] ^ newKey);
            }
        }
        var ret = send_func(GAME_FD, buf, portalLen, 0);
        send({t: 'replayed', len: portalLen, ret: ret, newKey: newKey});
        return 'sent';
    },
    hasPacket: function() {
        return portalPlaintext !== null;
    }
};

send({t: 'ready', msg: 'Waiting... walk through a portal and back!'});
