var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var count = 0;

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && count < 30) {
            count++;
            var first = buf.readU8();
            var bytes = [];
            var maxRead = Math.min(len, 32);
            for (var i = 0; i < maxRead; i++) {
                bytes.push(buf.add(i).readU8());
            }
            var hex = '';
            for (var i = 0; i < bytes.length; i++) {
                hex += ('0' + bytes[i].toString(16)).slice(-2) + ' ';
            }
            send({t: 'send', n: count, len: len, first: first, hex: hex});
        }
    }
});

send({t: 'ready'});
