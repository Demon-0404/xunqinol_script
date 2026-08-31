// Check the GOT/literal pool setup for the function at 0xC19181C
// and trace what values R4/R5 should have
var base = ptr(0xc074000);
var handlerAddr = ptr(0xc14e0a2);
var stubAddr = ptr(0xc14e098);
var realFunc = ptr(0xc19181c);

// Protect all relevant pages
Memory.protect(handlerAddr.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(stubAddr.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(realFunc.and(ptr(0xfffff000)), 4096, 'rwx');

// Read the literal pool around 0xC19181C
// The function's literal pool should be accessible
send({t: 'log', msg: '=== Reading literal pool region ==='});

// Read memory at and after the function to find the literal pool
for (var off = 0x20; off < 0x100; off += 16) {
    var addr = realFunc.add(off);
    try {
        var bytes = addr.readByteArray(16);
        var arr = new Uint8Array(bytes);
        var hex = '';
        for (var i = 0; i < 16; i++) hex += ('0' + arr[i].toString(16)).slice(-2) + ' ';
        var m = '  +0x' + off.toString(16) + ': ' + hex;
        send({t: 'log', msg: m});
    } catch(e) {}
}

// Read the handlerObj's vtable pointer and field4 in detail
var handlerObj = ptr(0x0c4d8a18);
var vtable = handlerObj.readPointer(); // offset 0
var field4 = handlerObj.add(4).readPointer(); // offset 4
var field8 = handlerObj.add(8).readPointer();
var field12 = handlerObj.add(12).readPointer();
var m2 = 'handlerObj vtable=' + vtable + ' field4=' + field4 + ' field8=' + field8 + ' field12=' + field12;
send({t: 'log', msg: m2});

// Read what field4 points to
try {
    var f4bytes = field4.readByteArray(64);
    var f4arr = new Uint8Array(f4bytes);
    var f4h = '';
    for (var i = 0; i < 64; i++) {
        f4h += ('0' + f4arr[i].toString(16)).slice(-2) + ' ';
        if ((i + 1) % 16 === 0) {
            send({t: 'log', msg: '  field4[' + (i-15) + ']: ' + f4h});
            f4h = '';
        }
    }
} catch(e) {
    var m3 = 'Cannot read field4: ' + e;
    send({t: 'err', msg: m3});
}

// Try to read the jlapp_jumpUrl global base (R4 value)
// From trace_jumpurl.js: R4 = 0xc4d0af8
var r4base = ptr(0xc4d0af8);
try {
    var r4bytes = r4base.readByteArray(128);
    var r4arr = new Uint8Array(r4bytes);
    send({t: 'log', msg: '=== R4 base (0xc4d0af8) data ==='});
    var r4h = '';
    for (var i = 0; i < 128; i++) {
        r4h += ('0' + r4arr[i].toString(16)).slice(-2) + ' ';
        if ((i + 1) % 16 === 0) {
            send({t: 'log', msg: '  ' + r4h});
            r4h = '';
        }
    }
} catch(e) {
    var m4 = 'Cannot read R4 base: ' + e;
    send({t: 'err', msg: m4});
}

// Now hook 0xC19181C and read the LITERAL that LDR R4, [PC, #4] loads
Interceptor.attach(realFunc, {
    onEnter: function(args) {
        send({t: 'log', msg: '>>> 0xC19181C: reading literal at PC+4'});

        // PC = realFunc + 8 (ARM pipeline)
        // LDR R4, [PC, #+4] loads from PC + 4 = realFunc + 12 = 0xC191828
        var litAddr = realFunc.add(12);
        try {
            var lit = litAddr.readPointer();
            var m5 = '  Literal at 0xC191828 = ' + lit;
            send({t: 'log', msg: m5});

            // Also try to read what the literal points to
            try {
                var gotVal = lit.readPointer();
                var m6 = '  *literal = ' + gotVal;
                send({t: 'log', msg: m6});
            } catch(e2) {
                var m7 = '  *literal unreadable: ' + e2;
                send({t: 'err', msg: m7});
            }
        } catch(e) {
            var m8 = '  Cannot read literal: ' + e;
            send({t: 'err', msg: m8});
        }

        // Also dump all regs
        var ctx = this.context;
        var m9 = '  R0=' + args[0] + ' R4=' + ctx.r4 + ' R5=' + ctx.r5;
        send({t: 'log', msg: m9});

        try {
            if (args[0]) {
                var s = args[0].readUtf8String(128);
                send({t: 'log', msg: '  R0 str=' + s});
            }
        } catch(e) {}
    }
});

// Call via stub (which we know reaches 0xC19181C)
var testUrl = Memory.allocUtf8String('xqj://test_got');
send({t: 'log', msg: '=== Calling stub(URL) directly ==='});

try {
    var stubFn = new NativeFunction(stubAddr, 'void', ['pointer']);
    stubFn(testUrl);
    send({t: 'log', msg: 'Stub returned OK'});
} catch(e) {
    var m10 = 'Stub crashed: ' + e;
    send({t: 'err', msg: m10});
}

send({t: 'ready', msg: 'done'});
