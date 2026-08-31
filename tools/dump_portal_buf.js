var GAME_FD = %d;
var libtcb = Process.getModuleByName("libtcb.so");
var base = libtcb.base;

// Hook 0x20341 - dump buffer when a1=29 (portal) or a1=30 (movement)
Interceptor.attach(base.add(0x20341), {
    onEnter: function(args) {
        var buf = args[0];
        var len = args[1].toInt32();
        // 只需要 portal (29) 和 movement (30)
        if (len !== 29 && len !== 30) return;

        var hex = '';
        for (var i = 0; i < Math.min(len, 64); i++) {
            hex += ('0' + buf.add(i).readU8().toString(16)).slice(-2);
        }
        send({t: 'buf', len: len, hex: hex, addr: buf.toString()});
    }
});

send({t: 'ready', msg: 'Dump portal buf ready. 走传送门！'});
