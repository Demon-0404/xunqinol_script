// Capture incoming R4 at 0xC19181C to understand the GOT setup
var realFunc = ptr(0xc19181c);

Memory.protect(realFunc.and(ptr(0xfffff000)), 4096, 'rwx');

// Hook 0xC19181C to capture ALL incoming registers
// First instruction: ldr r4, [pc, -r4] uses R4 to locate GOT
Interceptor.attach(realFunc, {
    onEnter: function(args) {
        var ctx = this.context;
        send({t: 'log', msg: '>>> 0xC19181C entry registers:'});
        var m0 = '  R0=' + args[0] + ' R1=' + args[1];
        send({t: 'log', msg: m0});
        var m1 = '  R2=' + args[2] + ' R3=' + args[3];
        send({t: 'log', msg: m1});
        var m2 = '  R4=' + ctx.r4 + ' R5=' + ctx.r5 + ' R6=' + ctx.r6;
        send({t: 'log', msg: m2});
        var m3 = '  SP=' + ctx.sp + ' LR=' + ctx.lr;
        send({t: 'log', msg: m3});

        // Compute what address ldr r4, [pc, -r4] would load from
        // PC at this instruction = realFunc + 8 (ARM pipeline)
        // Address = PC - R4
        var pc = realFunc.add(8);
        var loadAddr = pc.sub(ctx.r4);
        var m4 = '  PC=' + pc + '  PC-' + ctx.r4 + ' = ' + loadAddr;
        send({t: 'log', msg: m4});

        // Try to read from computed load address
        try {
            var gotPtr = loadAddr.readPointer();
            var m5 = '  *loadAddr (GOT ptr) = ' + gotPtr;
            send({t: 'log', msg: m5});
            // Also try to read what the GOT ptr points to
            try {
                var gotVal = gotPtr.readPointer();
                var m6 = '  **loadAddr (GOT[0]) = ' + gotVal;
                send({t: 'log', msg: m6});
            } catch(e2) {
                var m7 = '  GOT value unreadable: ' + e2;
                send({t: 'log', msg: m7});
            }
        } catch(e) {
            var m8 = '  Cannot read loadAddr: ' + e;
            send({t: 'log', msg: m8});
        }

        try {
            if (args[0] && !args[0].isNull()) {
                var s = args[0].readUtf8String(128);
                send({t: 'log', msg: '  R0 string: ' + s});
            }
        } catch(e) {}
    }
});

// Call 0xC19181C directly
var testUrl = Memory.allocUtf8String('xqj://capture_r4');
send({t: 'log', msg: '=== Calling 0xC19181C(' + testUrl + ') ==='});

try {
    var fn = new NativeFunction(realFunc, 'void', ['pointer']);
    fn(testUrl);
    send({t: 'log', msg: 'OK'});
} catch(e) {
    var m9 = 'Crash: ' + e;
    send({t: 'err', msg: m9});
}

send({t: 'ready', msg: 'done'});
