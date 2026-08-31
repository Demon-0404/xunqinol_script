// Call the handler directly instead of going through jlapp_jumpUrl
// This bypasses the vtable lookup and lets us control the arguments
var base = ptr(0xc074000);

// Read handler code and compute BL target
var handlerAddr = ptr(0xc14e0a2);
Memory.protect(handlerAddr.and(ptr(0xfffff000)), 4096, 'rwx');

var hcode = handlerAddr.readByteArray(16);
var harr = new Uint8Array(hcode);

send({t: 'log', msg: 'Handler code:'});
var hhex = '';
for (var i = 0; i < 16; i++) {
    hhex += ('0' + harr[i].toString(16)).slice(-2) + ' ';
}
send({t: 'log', msg: hhex});

// Decode Thumb-2 BL instruction: bytes at handler+6 = ff f7 f6 ff
// H1=0xf7ff, H2=0xfff6
// ARMv8: imm32 = SignExtend({S, I1, I2, imm10_H, imm10_L, '0'}, 32)
// I1 = NOT(J1 XOR S), I2 = NOT(J2 XOR S)
var S = 1;
var J1 = 1;
var J2 = 1;
var imm10_H = 0x3FF;
var imm10_L = 0x3F6;

var I1 = (~(J1 ^ S)) & 1;
var I2 = (~(J2 ^ S)) & 1;

var imm24 = (S << 23) | (I1 << 22) | (I2 << 21) | (imm10_H << 11) | imm10_L;
var msg1 = 'imm24 = 0x' + imm24.toString(16);
send({t: 'log', msg: msg1});

// Sign extend from 24 bits
var signBit = 1 << 23;
var offset;
if (imm24 & signBit) {
    offset = imm24 - (1 << 24);
} else {
    offset = imm24;
}

var msg2 = 'offset (bytes) = ' + offset + ' (0x' + (offset & 0xFFFFFFFF).toString(16) + ')';
send({t: 'log', msg: msg2});

// Target = PC + offset
// PC for BL = address of H1 + 4 = handlerAddr + 6 + 4 = handlerAddr + 10 = 0xc14e0ac
var pc = handlerAddr.add(10);
var target = pc.add(offset);
var msg3 = 'BL target = ' + target;
send({t: 'log', msg: msg3});

// Read code at target
try {
    var tcode = target.readByteArray(32);
    var tarr = new Uint8Array(tcode);
    var thex = '';
    for (var ti = 0; ti < 32; ti++) {
        thex += ('0' + tarr[ti].toString(16)).slice(-2) + ' ';
    }
    var msg4 = 'Target code: ' + thex;
    send({t: 'log', msg: msg4});
} catch(e) {
    var msg5 = 'Cannot read target code: ' + e;
    send({t: 'err', msg: msg5});
}

// Now try calling the handler directly with known arguments
// R0 = handlerObj = 0x0c4d8a18
// R1 = pointer to URL string on stack
var handlerObj = ptr(0x0c4d8a18);
var testUrl = Memory.allocUtf8String('xqj://test_direct');
var urlPtrPtr = Memory.alloc(4);
urlPtrPtr.writePointer(testUrl);

send({t: 'log', msg: '=== Calling handler directly ==='});
var msg6 = 'handlerObj=' + handlerObj;
send({t: 'log', msg: msg6});
var msg7 = 'urlPtrPtr=' + urlPtrPtr + ' -> ' + testUrl;
send({t: 'log', msg: msg7});

// Hook the handler
Interceptor.attach(handlerAddr, {
    onEnter: function(args) {
        var m1 = '[HANDLER] ENTER! R0=' + args[0] + ' R1=' + args[1];
        send({t: 'log', msg: m1});
        try {
            var m2 = '[HANDLER] *R1=' + args[1].readPointer();
            send({t: 'log', msg: m2});
            var m3 = '[HANDLER] url=' + args[1].readPointer().readUtf8String();
            send({t: 'log', msg: m3});
        } catch(e2) {}
    }
});

// Call handler as void handler(void* obj, const char** urlPtr)
try {
    var handlerFn = new NativeFunction(handlerAddr, 'void', ['pointer', 'pointer']);
    handlerFn(handlerObj, urlPtrPtr);
    send({t: 'log', msg: 'Handler call returned OK'});
} catch(e) {
    var msg8 = 'Handler call crashed: ' + e;
    send({t: 'err', msg: msg8});
}

// Also try calling the BL target directly
if (target) {
    Memory.protect(target.and(ptr(0xfffff000)), 4096, 'rwx');
    send({t: 'log', msg: '=== Calling BL target directly ==='});
    var msg9 = 'Target @ ' + target;
    send({t: 'log', msg: msg9});

    // Read handler field4
    var field4 = handlerObj.add(4).readPointer();
    var msg10 = 'field4 = ' + field4;
    send({t: 'log', msg: msg10});

    try {
        var targetFn = new NativeFunction(target, 'void', ['pointer', 'pointer']);
        targetFn(field4, testUrl);
        send({t: 'log', msg: 'Target call returned OK'});
    } catch(e2) {
        var msg11 = 'Target call crashed: ' + e2;
        send({t: 'err', msg: msg11});
    }
}

send({t: 'ready', msg: 'done'});
