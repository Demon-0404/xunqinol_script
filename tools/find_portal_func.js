var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var sendPtr = libc.getExportByName("send");

Interceptor.attach(sendPtr, {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD || len !== 29) return;
        if (buf.readU8() !== 3) return;

        send({t: 'portal', len: len});

        var bt = Thread.backtrace(this.context, Backtracer.FUZZY);
        for (var i = 0; i < bt.length && i < 25; i++) {
            var addr = bt[i];
            var mod = Process.findModuleByAddress(addr);
            var modName = mod ? mod.name : '???';
            var offset = '?';
            if (mod) {
                offset = '0x' + addr.sub(mod.base).toString(16);
            }
            var addrStr = addr.toString();
            send({t: 'frame', n: i, mod: modName, off: offset, addr: addrStr});
        }
        send({t: 'stack_end'});
    }
});

send({t: 'ready', msg: 'Walk through a portal...'});
