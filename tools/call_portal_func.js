var GAME_FD = %d;
var libtcb = Process.getModuleByName("libtcb.so");
var libc = Process.getModuleByName("libc.so");
var base = libtcb.base;

// Hook send to detect portal and capture context
var lastPortalContext = null;

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 29 && buf.readU8() === 3) {
            // Save context when portal happens
            var ctx = this.context;
            send({t: 'portal_ctx',
                  x0: ctx.x0.toString(), x1: ctx.x1.toString(),
                  x2: ctx.x2.toString(), x3: ctx.x3.toString(),
                  lr: ctx.lr.toString(), sp: ctx.sp.toString()});
        }
    }
});

// Hook 0x20341 to trace its args during actual portal use
try {
    Interceptor.attach(base.add(0x20341), {
        onEnter: function(args) {
            send({t: 'c20341',
                  a0: args[0].toString(),
                  a1: args[1].toString(),
                  a2: args[2].toString(),
                  a3: args[3].toString()});
        }
    });
    send({t: 'info', msg: '0x20341 hooked'});
} catch(e) {
    send({t: 'err', msg: '0x20341: ' + e.toString()});
}

send({t: 'ready', msg: 'Call portal func ready. 走传送门看参数！'});
