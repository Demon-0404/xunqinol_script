var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;
var M1 = 0, M2 = 0;
var pktCount = 0;

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (fd === GAME_FD) {
            var len = args[2].toInt32();
            var first = args[1].readU8();
            if (len === 30 && first === 3) {
                pktCount++;
                var key = args[1].add(1).readU8();
                var p1 = args[1].add(2).readU8() ^ key;
                var p3 = args[1].add(4).readU8() ^ key;
                var sub = args[1].add(8).readU8() ^ key;
                var x = args[1].add(18).readU8() ^ key;
                var y = args[1].add(22).readU8() ^ key;

                if (!M1) { M1 = p1; M2 = p3; }

                if (lastX === null || x !== lastX || y !== lastY) {
                    send({t: 'move', n: pktCount, sub: sub, x: x, y: y, M1: M1, M2: M2});
                    lastX = x; lastY = y;
                }
            }
        }
    }
});

send({t: 'ready'});
