var GAME_FD = %d;
var libtcb = Process.getModuleByName("libtcb.so");
var libc = Process.getModuleByName("libc.so");
var base = libtcb.base;
var callIdx = 0;

send({t: 'info', msg: 'libtcb base=' + base.toString()});

// Hook send() for portal detection
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 29 && buf.readU8() === 3) {
            send({t: 'PORTAL'});
        }
    }
});

// Minimal hook on 0x6d289
try {
    var target = base.add(0x6d289);
    send({t: 'info', msg: 'hooking 0x6d289 at ' + target.toString()});
    Interceptor.attach(target, {
        onEnter: function(args) {
            callIdx++;
            send({t: 'c6d', n: callIdx, a0: args[0].toString(), a1: args[1].toString(), a2: args[2].toString()});
        }
    });
    send({t: 'info', msg: '0x6d289 hooked OK'});
} catch(e) {
    send({t: 'err', msg: '0x6d289 hook failed: ' + e.toString()});
}

// Also hook 0x653eb
try {
    var t2 = base.add(0x653eb);
    Interceptor.attach(t2, {
        onEnter: function(args) {
            send({t: 'c65', a0: args[0].toString()});
        }
    });
    send({t: 'info', msg: '0x653eb hooked OK'});
} catch(e) {
    send({t: 'err', msg: '0x653eb hook failed: ' + e.toString()});
}

// Also hook 0x20341
try {
    var t3 = base.add(0x20341);
    Interceptor.attach(t3, {
        onEnter: function(args) {
            send({t: 'c20', a0: args[0].toString(), a1: args[1].toString(), a2: args[2].toString()});
        }
    });
    send({t: 'info', msg: '0x20341 hooked OK'});
} catch(e) {
    send({t: 'err', msg: '0x20341 hook failed: ' + e.toString()});
}

send({t: 'ready', msg: 'All hooks set. Walk through portal!'});
