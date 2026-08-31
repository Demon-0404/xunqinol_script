var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var portalSent = false;
var traceCnt = 0;

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 29 && buf.readU8() === 3) {
            portalSent = true;
            send({t: 'portal_detected'});
        }
    }
});

Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.doTrace = portalSent && this.fd === GAME_FD && traceCnt < 8;
    },
    onLeave: function(ret) {
        if (!this.doTrace) return;
        var len = ret.toInt32();
        if (len <= 0) return;
        traceCnt++;

        // Check first byte for type 0x15 (map data)
        var firstByte = this.buf.readU8();
        var tag = firstByte === 0x15 ? 'MAP_DATA' : 'OTHER';

        var bt = Thread.backtrace(this.context, Backtracer.FUZZY);
        var frames = [];
        for (var i = 0; i < Math.min(bt.length, 15); i++) {
            var addr = bt[i];
            var mod = Process.findModuleByAddress(addr);
            if (mod) {
                var off = addr.sub(mod.base);
                frames.push(mod.name + '+0x' + off.toString(16));
            } else {
                frames.push(addr.toString());
            }
        }
        send({t: 'trace', n: traceCnt, len: len, tag: tag, bt: frames.join(' <- ')});
    }
});

send({t: 'ready', msg: 'Trace ready. Walk through portal!'});
