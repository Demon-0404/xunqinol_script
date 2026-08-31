// Correctly call the stub with 2 args to reach 0xC19181C
// Handler does: R0=handlerObj, R1=urlPtr
// Then: LDR R0,[R0,#4]=field4, LDR R1,[R1]=url, BL stub
// Stub does: MOV R0,R1 (uses R1=url, discards R0=field4), BL 0xC19181C
var base = ptr(0xc074000);
var handlerAddr = ptr(0xc14e0a2);
var stubAddr = ptr(0xc14e098);
var realFunc = ptr(0xc19181c);

Memory.protect(handlerAddr.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(stubAddr.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(realFunc.and(ptr(0xfffff000)), 4096, 'rwx');

// Hook 0xC19181C to read literal pool
Interceptor.attach(realFunc, {
    onEnter: function(args) {
        var ctx = this.context;
        send({t: 'log', msg: '>>> 0xC19181C HIT!'});
        var m0 = '  R0=' + args[0] + ' R1=' + args[1] + ' R2=' + args[2] + ' R3=' + args[3];
        send({t: 'log', msg: m0});
        var m1 = '  R4(in)=' + ctx.r4 + ' R5(in)=' + ctx.r5 + ' LR=' + ctx.lr + ' PC=' + ctx.pc;
        send({t: 'log', msg: m1});

        // LDR R4,[PC,#+4] loads from realFunc+8+4 = realFunc+12
        var litAddr = realFunc.add(12);
        try {
            var litVal = litAddr.readPointer();
            var m2 = '  Literal @' + litAddr + ' = ' + litVal;
            send({t: 'log', msg: m2});
            try {
                var gotVal = litVal.readPointer();
                var m3 = '  *literal = ' + gotVal;
                send({t: 'log', msg: m3});
            } catch(e) {
                var m4 = '  Cannot read *literal: ' + e;
                send({t: 'err', msg: m4});
            }
        } catch(e) {
            var m5 = '  Cannot read literal addr: ' + e;
            send({t: 'err', msg: m5});
        }

        try {
            if (args[0] && !args[0].isNull()) {
                var s = args[0].readUtf8String(128);
                send({t: 'log', msg: '  R0 string: ' + s});
            }
        } catch(e) {}
    }
});

// Call stub with TWO args: stub(field4, url) to match handler convention
// handler loads: R0=handlerObj->field4, R1=URL_string (from *urlPtr)
// stub does: MOV R0,R1 → R0=URL, then BL 0xC19181C
var handlerObj = ptr(0x0c4d8a18);
var field4 = handlerObj.add(4).readPointer();
var testUrl = Memory.allocUtf8String('xqj://test_final');
var m6 = 'handlerObj=' + handlerObj + ' field4=' + field4 + ' url=' + testUrl;
send({t: 'log', msg: m6});

send({t: 'log', msg: '=== Calling stub(field4, url) ==='});
try {
    var stubFn = new NativeFunction(stubAddr, 'void', ['pointer', 'pointer']);
    stubFn(field4, testUrl);
    send({t: 'log', msg: 'Stub(field4,url) returned OK!'});
} catch(e) {
    var m7 = 'Stub crashed: ' + e;
    send({t: 'err', msg: m7});
}

// Also try calling the handler directly (bypass jlapp_jumpUrl)
var urlPtrPtr = Memory.alloc(4);
urlPtrPtr.writePointer(testUrl);
var testUrl2 = Memory.allocUtf8String('xqj://test_handler');
var urlPtrPtr2 = Memory.alloc(4);
urlPtrPtr2.writePointer(testUrl2);

send({t: 'log', msg: '=== Calling handler(handlerObj, urlPtrPtr) ==='});
try {
    var handlerFn = new NativeFunction(handlerAddr, 'void', ['pointer', 'pointer']);
    handlerFn(handlerObj, urlPtrPtr2);
    send({t: 'log', msg: 'Handler returned OK!'});
} catch(e) {
    var m8 = 'Handler crashed: ' + e;
    send({t: 'err', msg: m8});
}

send({t: 'ready', msg: 'done'});
