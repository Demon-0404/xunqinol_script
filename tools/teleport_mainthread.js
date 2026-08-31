// Call jlapp_jumpUrl from within a game main thread hook
var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0);

// Protect the page so we can call it
Memory.protect(jumpUrlFunc.and(ptr(0xfffff000)), 4096, 'rwx');
send({t: 'log', msg: 'Page protected for jlapp_jumpUrl'});

// Hook jlapp_jumpUrl to observe arguments
Interceptor.attach(jumpUrlFunc, {
    onEnter: function(args) {
        send({t: 'log', msg: '*** jlapp_jumpUrl CALLED ***'});
        send({t: 'log', msg: '  R0=' + args[0]});
        send({t: 'log', msg: '  R1=' + args[1]});
        send({t: 'log', msg: '  R2=' + args[2]});
        for (var ai = 0; ai < 3; ai++) {
            try {
                var s = args[ai].readUtf8String(128);
                if (s && s.length > 0) {
                    send({t: 'log', msg: '  arg' + ai + ' string: "' + s + '"'});
                }
            } catch(e) {}
        }
    },
    onLeave: function(ret) {
        send({t: 'log', msg: '  Return: ' + ret});
    }
});

// Find CCScheduler::update
function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

var dynstrAddr = 0x2f178;
var dynsymAddr = 0x148;
var schedulerUpdate = null;

for (var si = 0; si < 30000; si++) {
    var sym = base.add(dynsymAddr + si * 16);
    var st_name = readU32(sym);
    if (st_name === 0) continue;
    try {
        var sn = base.add(dynstrAddr + st_name).readUtf8String(128);
        if (sn.indexOf('CCScheduler') !== -1 && sn.indexOf('update') !== -1 && sn.length < 80) {
            var sv = readU32(sym.add(4));
            var sz = readU32(sym.add(8));
            schedulerUpdate = {name: sn, value: sv, size: sz};
            send({t: 'log', msg: 'Found: ' + sn + ' @ 0x' + sv.toString(16) + ' size=' + sz});
            break;
        }
    } catch(e) {}
}

if (!schedulerUpdate) {
    send({t: 'err', msg: 'CCScheduler::update not found'});
    send({t: 'ready', msg: 'Failed'});
} else {
    var schedAddr = base.add(schedulerUpdate.value);
    send({t: 'log', msg: 'Hooking scheduler @ ' + schedAddr});
    Memory.protect(schedAddr.and(ptr(0xfffff000)), 4096, 'rwx');

    var callCount = 0;
    var jumpArmed = false;
    var jumpUrl = null;
    var framesUntilCall = 0;
    var throttleCounter = 0;
    var THROTTLE = 30;

    Interceptor.attach(schedAddr, {
        onEnter: function(args) {
            callCount++;
            throttleCounter++;
            if (throttleCounter < THROTTLE) return;
            throttleCounter = 0;

            if (jumpArmed && jumpUrl) {
                if (framesUntilCall <= 0) {
                    send({t: 'log', msg: '>>> Calling jlapp_jumpUrl FROM MAIN THREAD'});
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

    send({t: 'log', msg: 'Scheduler hooked!'});

    rpc.exports = {
        armJump: function(urlStr) {
            jumpUrl = Memory.allocUtf8String(urlStr);
            jumpArmed = true;
            framesUntilCall = 5;
            return 'Armed: ' + urlStr;
        },
        getCallCount: function() { return callCount; },
        status: function() {
            return JSON.stringify({
                callCount: callCount,
                armed: jumpArmed,
                framesLeft: framesUntilCall,
                url: jumpUrl ? jumpUrl.readUtf8String() : null
            });
        }
    };

    send({t: 'log', msg: '=== READY - use armJump("url") to test ==='});
    send({t: 'ready', msg: 'Main thread jump system ready'});
}
