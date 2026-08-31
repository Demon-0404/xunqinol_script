// Analyze handler functions in detail
var base = ptr(0xc19c000);

function readU32(a) {
    var b = a.readByteArray(4);
    var arr = new Uint8Array(b);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

// func2 at corrected address (BL2 target)
var func2 = ptr(0xc35442c);
var code = func2.readByteArray(128);
var arr = new Uint8Array(code);
send({t: 'log', msg: '=== func2 (corrected) @ ' + func2 + ' ==='});
for (var i = 0; i < 128; i += 16) {
    var hex = '';
    for (var j = 0; j < 16 && (i+j) < 128; j++) {
        hex += ('0' + arr[i+j].toString(16)).slice(-2) + ' ';
    }
    send({t: 'log', msg: '  +0x' + i.toString(16) + ': ' + hex});
}

// Try calling func1 (0xc354228) directly with handlerObj and urlPtr
// func1 seems to be an init function that allocates a struct
// Let's hook it and see what happens
Memory.protect(ptr(0xc354228).and(ptr(0xfffff000)), 4096, 'rwx');
Interceptor.attach(ptr(0xc354228), {
    onEnter: function(args) {
        send({t: 'log', msg: '[func1] ENTER R0=' + args[0] + ' R1=' + args[1] + ' R2=' + args[2]});
        send({t: 'log', msg: '  LR=' + this.context.lr + ' SP=' + this.context.sp});
    },
    onLeave: function(ret) {
        send({t: 'log', msg: '[func1] LEAVE ret=' + ret});
    }
});

// Call handler again to see func1 in action
var handlerObj = ptr(0xc600a30);
var url = Memory.allocUtf8String('xqj://map?name=test');
var urlPtr = Memory.alloc(4);
urlPtr.writePointer(url);
var handlerFn = ptr(0xc276018);
Memory.protect(handlerFn.and(ptr(0xfffff000)), 4096, 'rwx');

send({t: 'log', msg: '=== Calling handler with func1 hook ==='});
try {
    var fn = new NativeFunction(handlerFn, 'void', ['pointer', 'pointer']);
    fn(handlerObj, urlPtr);
    send({t: 'log', msg: 'SUCCESS'});
} catch(e) {
    send({t: 'err', msg: 'CRASH: ' + e});
}

send({t: 'ready', msg: 'done'});
