// Call jlapp_jumpUrl from EGL thread and trace register context
var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0);
var handlerAddr = ptr(0xc14e0a2);
var stubAddr = ptr(0xc14e098);
var realFunc = ptr(0xc19181c);

// Protect
Memory.protect(jumpUrlFunc.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(handlerAddr.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(stubAddr.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(realFunc.and(ptr(0xfffff000)), 4096, 'rwx');

// Hook jlapp_jumpUrl entry - capture R4,R5
Interceptor.attach(jumpUrlFunc, {
    onEnter: function(args) {
        this.url = args[0];
        this.r4 = this.context.r4;
        this.r5 = this.context.r5;
        send({t: 'log', msg: '>>> jlapp_jumpUrl ENTER'});
        var m0 = '  R0=' + args[0] + ' R4=' + this.r4 + ' R5=' + this.r5;
        send({t: 'log', msg: m0});
        try {
            var s = args[0].readUtf8String(128);
            var m1 = '  URL: ' + s;
            send({t: 'log', msg: m1});
        } catch(e) {}
    },
    onLeave: function(ret) {
        var m2 = '<<< jlapp_jumpUrl RETURN: ' + ret;
        send({t: 'log', msg: m2});
    }
});

// Hook handler
Interceptor.attach(handlerAddr, {
    onEnter: function(args) {
        this.r0 = args[0];
        this.r1 = args[1];
        var m3 = '[handler] R0=' + args[0] + ' R1=' + args[1];
        send({t: 'log', msg: m3});
    }
});

// Hook stub
Interceptor.attach(stubAddr, {
    onEnter: function(args) {
        var m4 = '[stub] R0=' + args[0] + ' R1=' + args[1];
        send({t: 'log', msg: m4});
        try {
            if (args[0]) {
                var s = args[0].readUtf8String(128);
                send({t: 'log', msg: '[stub] R0 str=' + s});
            }
        } catch(e) {}
        try {
            if (args[1]) {
                var s2 = args[1].readUtf8String(128);
                send({t: 'log', msg: '[stub] R1 str=' + s2});
            }
        } catch(e) {}
    }
});

// Hook real function - capture all regs
Interceptor.attach(realFunc, {
    onEnter: function(args) {
        var ctx = this.context;
        send({t: 'log', msg: '>>> REAL 0xC19181C HIT!'});
        var m5 = '  R0=' + args[0] + ' R1=' + args[1] + ' R2=' + args[2] + ' R3=' + args[3];
        send({t: 'log', msg: m5});
        var m6 = '  R4=' + ctx.r4 + ' R5=' + ctx.r5 + ' R6=' + ctx.r6;
        send({t: 'log', msg: m6});
        var m7 = '  SP=' + ctx.sp + ' LR=' + ctx.lr + ' PC=' + ctx.pc;
        send({t: 'log', msg: m7});
        try {
            if (args[0] && !args[0].isNull()) {
                var s = args[0].readUtf8String(256);
                send({t: 'log', msg: '  R0 str: ' + s});
            }
        } catch(e) {}
    }
});

// Find eglSwapBuffers
var eglSwapBuffers;
try {
    var eglMod = Process.getModuleByName('libEGL.so');
    eglSwapBuffers = eglMod.getExportByName('eglSwapBuffers');
    send({t: 'log', msg: 'eglSwapBuffers @ ' + eglSwapBuffers});
} catch(e) {
    send({t: 'err', msg: 'libEGL not found: ' + e});
}

if (eglSwapBuffers) {
    var callCount = 0;
    var jumpArmed = false;
    var jumpUrl = null;
    var framesUntilCall = 0;

    Interceptor.attach(eglSwapBuffers, {
        onEnter: function(args) {
            callCount++;
            if ((callCount % 2) !== 0) return;

            if (jumpArmed && jumpUrl) {
                if (framesUntilCall <= 0) {
                    send({t: 'log', msg: '>>> Calling jlapp_jumpUrl from EGL (frame ' + callCount + ')'});
                    try {
                        var fn = new NativeFunction(jumpUrlFunc, 'void', ['pointer']);
                        fn(jumpUrl);
                        send({t: 'log', msg: '    jlapp_jumpUrl returned OK!'});
                    } catch(e) {
                        var m8 = '    CRASH: ' + e;
                        send({t: 'err', msg: m8});
                    }
                    jumpArmed = false;
                    jumpUrl = null;
                } else {
                    framesUntilCall--;
                }
            }
        }
    });

    send({t: 'log', msg: 'All hooks ready, eglSwapBuffers active'});

    rpc.exports = {
        armJump: function(urlStr) {
            jumpUrl = Memory.allocUtf8String(urlStr);
            jumpArmed = true;
            framesUntilCall = 3;
            var m9 = 'Armed: ' + urlStr;
            send({t: 'log', msg: m9});
            return m9;
        },
        getCallCount: function() { return callCount; },
        status: function() {
            var st = 'frames=' + callCount + ' armed=' + jumpArmed;
            if (jumpUrl) st += ' url=' + jumpUrl.readUtf8String();
            return st;
        }
    };
}

send({t: 'ready', msg: 'ready'});
