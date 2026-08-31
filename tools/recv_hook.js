var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var count = 0;

Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.len = args[2].toInt32();
    },
    onLeave: function(ret) {
        var n = ret.toInt32();
        if (this.fd === GAME_FD && n > 0) {
            count++;
            // Read first 48 bytes
            var maxRead = Math.min(n, 48);
            var bytes = [];
            try {
                var raw = this.buf.readByteArray(maxRead);
                var arr = new Uint8Array(raw);
                for (var i = 0; i < arr.length; i++) {
                    bytes.push(arr[i]);
                }
            } catch(e) {}

            var hex = '';
            for (var i = 0; i < bytes.length; i++) {
                hex += ('0' + bytes[i].toString(16)).slice(-2) + ' ';
            }

            var first = bytes.length > 0 ? bytes[0] : -1;
            send({t: 'recv', n: count, len: n, first: first, hex: hex});

            // Try to decrypt if first byte looks like a key
            if (bytes.length > 1 && first < 128) {
                var key = first;
                var dec = [];
                for (var i = 1; i < bytes.length; i++) {
                    dec.push(bytes[i] ^ key);
                }
                var decHex = '';
                for (var i = 0; i < dec.length; i++) {
                    decHex += ('0' + dec[i].toString(16)).slice(-2) + ' ';
                }
                send({t: 'recv_dec', n: count, len: n, key: key, hex: decHex});
            }
        }
    }
});

send({t: 'ready'});
