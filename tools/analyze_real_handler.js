// Analyze the real URL handler at 0xC19181C
var base = ptr(0xc074000);
var handlerAddr = ptr(0xc14e0a2);
var stubAddr = ptr(0xc14e098);
var realHandler = ptr(0xc19181c);

// Protect all pages
Memory.protect(handlerAddr.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(stubAddr.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(realHandler.and(ptr(0xfffff000)), 4096, 'rwx');

// Read and dump the real handler code (more bytes)
try {
    var rcode = realHandler.readByteArray(128);
    var rarr = new Uint8Array(rcode);
    var msg = 'Code at 0xC19181C (128 bytes):';
    send({t: 'log', msg: msg});
    var rhex = '';
    for (var i = 0; i < 128; i++) {
        rhex += ('0' + rarr[i].toString(16)).slice(-2) + ' ';
        if ((i + 1) % 16 === 0) {
            send({t: 'log', msg: '  ' + rhex});
            rhex = '';
        }
    }
    if (rhex.length > 0) {
        send({t: 'log', msg: '  ' + rhex});
    }
} catch(e) {
    var msg2 = 'Cannot read 0xC19181C: ' + e;
    send({t: 'err', msg: msg2});
}

// Read the vtable region to understand the handler objects better
var handlerObj = ptr(0x0c4d8a18);
try {
    var hdata = handlerObj.readByteArray(64);
    var harr = new Uint8Array(hdata);
    var hhex = '';
    for (var i = 0; i < 64; i++) {
        hhex += ('0' + harr[i].toString(16)).slice(-2) + ' ';
        if ((i + 1) % 16 === 0) {
            send({t: 'log', msg: 'handlerObj[' + (i-15) + '..' + i + ']: ' + hhex});
            hhex = '';
        }
    }
} catch(e) {
    var msg3 = 'Cannot read handlerObj: ' + e;
    send({t: 'err', msg: msg3});
}

// Hook the real handler at 0xC19181C
Interceptor.attach(realHandler, {
    onEnter: function(args) {
        send({t: 'log', msg: '>>> REAL HANDLER 0xC19181C HIT!'});
        var m0 = '  R0=' + args[0] + ' R1=' + args[1] + ' R2=' + args[2] + ' R3=' + args[3];
        send({t: 'log', msg: m0});
        try {
            var s = args[0].readUtf8String(128);
            var m1 = '  R0 string: ' + s;
            send({t: 'log', msg: m1});
        } catch(e2) {}
        // Read stack
        try {
            var sp = this.context.sp;
            var m2 = '  SP=' + sp + ' LR=' + this.context.lr;
            send({t: 'log', msg: m2});
        } catch(e3) {}
    }
});

// Also hook the stub
Interceptor.attach(stubAddr, {
    onEnter: function(args) {
        send({t: 'log', msg: '>>> STUB 0xc14e098 HIT!'});
        var m = '  R0=' + args[0] + ' R1=' + args[1];
        send({t: 'log', msg: m});
        try {
            var s = args[0].readUtf8String(128);
            if (s && s.length > 0) {
                var m2 = '  R0 string: ' + s;
                send({t: 'log', msg: m2});
            }
        } catch(e2) {}
    }
});

// Try to call via stub directly (skip handler, go: stub(URL))
var testUrl = Memory.allocUtf8String('xqj://test_ana');
send({t: 'log', msg: '=== Calling stub(0xc14e098) directly with URL ==='});
try {
    var stubFn = new NativeFunction(stubAddr, 'void', ['pointer']);
    stubFn(testUrl);
    send({t: 'log', msg: 'Stub call returned OK!'});
} catch(e) {
    var msg4 = 'Stub call crashed: ' + e;
    send({t: 'err', msg: msg4});
}

// Also try calling real handler directly
var testUrl2 = Memory.allocUtf8String('xqj://test_ana2');
send({t: 'log', msg: '=== Calling 0xC19181C directly with URL ==='});
try {
    var realFn = new NativeFunction(realHandler, 'void', ['pointer']);
    realFn(testUrl2);
    send({t: 'log', msg: 'Real handler call returned OK!'});
} catch(e2) {
    var msg5 = 'Real handler call crashed: ' + e2;
    send({t: 'err', msg: msg5});
}

send({t: 'ready', msg: 'done'});
