// Analyze the true URL handler at 0xC19175E
// 0xC19181C is just a 4-byte trampoline: MOV R4,R0; B 0xC19175E
var base = ptr(0xc074000);
var trampoline = ptr(0xc19181c);
var realFunc = ptr(0xc19175e);

// Protect
Memory.protect(realFunc.and(ptr(0xfffff000)), 4096, 'rwx');
Memory.protect(trampoline.and(ptr(0xfffff000)), 4096, 'rwx');

// Read real function code (256 bytes)
try {
    var fcode = realFunc.readByteArray(256);
    var farr = new Uint8Array(fcode);
    send({t: 'log', msg: '=== Code at 0xC19175E (true handler, 256 bytes) ==='});
    var fhex = '';
    for (var i = 0; i < 256; i++) {
        fhex += ('0' + farr[i].toString(16)).slice(-2) + ' ';
        if ((i + 1) % 16 === 0) {
            send({t: 'log', msg: '  ' + fhex});
            fhex = '';
        }
    }
    if (fhex.length > 0) {
        send({t: 'log', msg: '  ' + fhex});
    }
} catch(e) {
    var m1 = 'Cannot read 0xC19175E: ' + e;
    send({t: 'err', msg: m1});
}

// Hook the real function
Interceptor.attach(realFunc, {
    onEnter: function(args) {
        send({t: 'log', msg: '>>> TRUE HANDLER 0xC19175E HIT!'});
        var m2 = '  R0=' + args[0] + ' R1=' + args[1] + ' R2=' + args[2] + ' R3=' + args[3];
        send({t: 'log', msg: m2});
        try {
            var sp = this.context.sp;
            var lr = this.context.lr;
            var m3 = '  SP=' + sp + ' LR=' + lr;
            send({t: 'log', msg: m3});
        } catch(e2) {}
        try {
            var s = args[0].readUtf8String(256);
            var m4 = '  R0 str: ' + s;
            send({t: 'log', msg: m4});
        } catch(e3) {}
    }
});

// Set up proper call chain simulation:
// jlapp_jumpUrl → handler → stub → trampoline → realFunc
// The stub does: MOV R0,R1 (discards field4, URL to R0) then BL 0xC19181C
// The trampoline does: MOV R4,R0 then B 0xC19175E
// So realFunc receives: R0 = URL string, R4 = URL string

var handlerObj = ptr(0x0c4d8a18);
var field4 = handlerObj.add(4).readPointer(); // 0xf41e47d0
var testUrl = Memory.allocUtf8String('xqj://test_75e');
var msg5 = 'field4 = ' + field4 + ' testUrl = ' + testUrl;
send({t: 'log', msg: msg5});

// Try calling realFunc directly with URL as R0
send({t: 'log', msg: '=== Calling 0xC19175E(URL) directly ==='});
try {
    var realFn = new NativeFunction(realFunc, 'void', ['pointer']);
    realFn(testUrl);
    send({t: 'log', msg: '0xC19175E call returned OK!'});
} catch(e) {
    var m6 = '0xC19175E crashed: ' + e;
    send({t: 'err', msg: m6});
}

// Try with URL AND field4 (in case it uses R1)
var testUrl2 = Memory.allocUtf8String('xqj://test_75e2');
send({t: 'log', msg: '=== Calling 0xC19175E(URL, field4) ==='});
try {
    var realFn2 = new NativeFunction(realFunc, 'void', ['pointer', 'pointer']);
    realFn2(testUrl2, field4);
    send({t: 'log', msg: '0xC19175E(url,field4) call returned OK!'});
} catch(e) {
    var m7 = '0xC19175E 2-arg crashed: ' + e;
    send({t: 'err', msg: m7});
}

send({t: 'ready', msg: 'done'});
