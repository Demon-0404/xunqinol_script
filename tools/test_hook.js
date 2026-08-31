var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var count = 0;

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var len = args[2].toInt32();
        if (fd === GAME_FD && len < 200) {
            count++;
            send({t: 'send', n: count, len: len, first: args[1].readU8()});
        }
    }
});

send({t: 'ok'});
