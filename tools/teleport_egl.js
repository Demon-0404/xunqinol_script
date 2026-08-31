// Call jlapp_jumpUrl from within eglSwapBuffers hook (main rendering thread)
var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0);

// Protect
Memory.protect(jumpUrlFunc.and(ptr(0xfffff000)), 4096, 'rwx');
send({t: 'log', msg: 'Page protected'});

// Hook jlapp_jumpUrl to observe
Interceptor.attach(jumpUrlFunc, {
    onEnter: function(args) {
        send({t: 'log', msg: '*** jlapp_jumpUrl HOOK FIRED ***'});
        send({t: 'log', msg: '  R0=' + args[0] + ' R1=' + args[1] + ' R2=' + args[2]});
        try {
            var s = args[0].readUtf8String(128);
            if (s && s.length > 0) send({t: 'log', msg: '  R0 str: ' + s});
        } catch(e) {}
    },
    onLeave: function(ret) {
        send({t: 'log', msg: '  return: ' + ret});
    }
});
send({t: 'log', msg: 'jlapp_jumpUrl hooked'});

// Find eglSwapBuffers in libEGL.so
var eglSwapBuffers = null;
try {
    var eglMod = Process.getModuleByName('libEGL.so');
    eglSwapBuffers = eglMod.getExportByName('eglSwapBuffers');
    send({t: 'log', msg: 'eglSwapBuffers @ ' + eglSwapBuffers + ' (via libEGL.so)'});
} catch(e) {
    send({t: 'err', msg: 'libEGL not found: ' + e});
    // Try to find it manually
    Process.enumerateModules().forEach(function(m) {
        if (m.name.indexOf('EGL') !== -1) {
            send({t: 'log', msg: 'Module: ' + m.name + ' base=' + m.base});
            try {
                m.enumerateExports().forEach(function(exp) {
                    if (exp.name === 'eglSwapBuffers') {
                        eglSwapBuffers = exp.address;
                        send({t: 'log', msg: 'Found eglSwapBuffers @ ' + exp.address});
                    }
                });
            } catch(e2) {}
        }
    });
}

if (!eglSwapBuffers) {
    send({t: 'err', msg: 'eglSwapBuffers not found'});
    send({t: 'ready', msg: 'Failed'});
} else {
    var callCount = 0;
    var jumpArmed = false;
    var jumpUrl = null;
    var framesUntilCall = 0;

    Interceptor.attach(eglSwapBuffers, {
        onEnter: function(args) {
            callCount++;
            // Check every 2 frames
            if ((callCount % 2) !== 0) return;

            if (jumpArmed && jumpUrl) {
                if (framesUntilCall <= 0) {
                    send({t: 'log', msg: '>>> Calling jlapp_jumpUrl from EGL thread (frame ' + callCount + ')'});
                    send({t: 'log', msg: '    URL: ' + jumpUrl.readUtf8String()});

                    try {
                        var fn = new NativeFunction(jumpUrlFunc, 'void', ['pointer']);
                        fn(jumpUrl);
                        send({t: 'log', msg: '    Call returned OK!'});
                    } catch(e) {
                        send({t: 'err', msg: '    Call failed: ' + e});
                    }

                    jumpArmed = false;
                    jumpUrl = null;
                } else {
                    framesUntilCall--;
                }
            }
        }
    });

    send({t: 'log', msg: 'eglSwapBuffers hooked! Frame count = ' + callCount});

    rpc.exports = {
        armJump: function(urlStr) {
            jumpUrl = Memory.allocUtf8String(urlStr);
            jumpArmed = true;
            framesUntilCall = 3;
            return 'Armed: ' + urlStr;
        },
        getCallCount: function() { return callCount; },
        status: function() {
            var s = 'frames=' + callCount + ' armed=' + jumpArmed;
            if (jumpUrl) s += ' url=' + jumpUrl.readUtf8String();
            return s;
        }
    };

    send({t: 'log', msg: '=== READY ==='});
    send({t: 'ready', msg: 'EGL thread jump system ready'});
}
