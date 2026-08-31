// Use Stalker to trace execution of 0xC19181C instruction by instruction
var realFunc = ptr(0xc19181c);
var stubAddr = ptr(0xc14e098);

Memory.protect(realFunc.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(stubAddr.and(ptr(0xfffff000)), 4096, 'rwx');

var testUrl = Memory.allocUtf8String('xqj://stalk');
var traceData = [];
var insnCount = 0;
var maxInsns = 200;

// Use Stalker to trace the real function
// First, hook the function entry to start stalking
Interceptor.attach(realFunc, {
    onEnter: function(args) {
        send({t: 'log', msg: '>>> 0xC19181C entered, starting Stalker'});
        var ctx = this.context;
        var m0 = '  R0=' + args[0] + ' R4=' + ctx.r4 + ' R5=' + ctx.r5 + ' SP=' + ctx.sp;
        send({t: 'log', msg: m0});

        insnCount = 0;
        traceData = [];

        // Start stalking this thread
        Stalker.follow(this.threadId, {
            transform: function(iterator) {
                var instruction = iterator.next();
                while (instruction) {
                    // Record every instruction
                    if (insnCount < maxInsns) {
                        var addr = instruction.address;
                        var m1 = '  [' + insnCount + '] ' + addr;
                        traceData.push(m1);
                    }
                    insnCount++;
                    iterator.keep();
                    instruction = iterator.next();
                }
            }
        });
    },
    onLeave: function(ret) {
        Stalker.unfollow(this.threadId);
        send({t: 'log', msg: '<<< 0xC19181C returned, insns: ' + insnCount});
        for (var i = 0; i < traceData.length; i++) {
            send({t: 'log', msg: traceData[i]});
        }
    }
});

// Call 0xC19181C directly
send({t: 'log', msg: '=== Calling 0xC19181C(URL) for Stalker trace ==='});
try {
    var fn = new NativeFunction(realFunc, 'void', ['pointer']);
    fn(testUrl);
    send({t: 'log', msg: 'Call returned OK'});
} catch(e) {
    var m2 = 'Call crashed: ' + e;
    send({t: 'err', msg: m2});
    // Still show what we captured
    send({t: 'log', msg: 'Captured ' + traceData.length + ' instructions:'});
    for (var j = 0; j < traceData.length; j++) {
        send({t: 'log', msg: traceData[j]});
    }
}

send({t: 'ready', msg: 'done'});
