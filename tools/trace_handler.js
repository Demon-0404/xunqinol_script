// Hook the entire jlapp_jumpUrl call chain to trace the crash
var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0);

// Protect
Memory.protect(jumpUrlFunc.and(ptr(0xfffff000)), 4096, 'rwx');
send({t: 'log', msg: 'jlapp_jumpUrl page rwx'});

// Hook jlapp_jumpUrl
Interceptor.attach(jumpUrlFunc, {
    onEnter: function(args) {
        send({t: 'log', msg: '[0] jlapp_jumpUrl ENTER. R0=' + args[0]});
        this.url = args[0];
    },
    onLeave: function(ret) {
        send({t: 'log', msg: '[0] jlapp_jumpUrl RETURN: ' + ret});
    }
});

// Hook handler at vtable[6] = 0xc14e0a3 (odd=Thumb, actual addr 0xc14e0a2)
var handlerAddr = ptr(0xc14e0a2);
Memory.protect(handlerAddr.and(ptr(0xfffff000)), 4096, 'rwx');

Interceptor.attach(handlerAddr, {
    onEnter: function(args) {
        send({t: 'log', msg: '[1] HANDLER ENTER'});
        send({t: 'log', msg: '    R0=' + args[0] + ' R1=' + args[1] + ' R2=' + args[2]});

        // R0 = handler_obj, R1 = &url_string
        // R1 points to stack where URL string pointer is saved
        try {
            var urlPtr = args[1].readPointer();
            send({t: 'log', msg: '    *R1 (url ptr) = ' + urlPtr});
            try {
                var urlStr = urlPtr.readUtf8String(128);
                send({t: 'log', msg: '    URL string: ' + urlStr});
            } catch(e2) {}
        } catch(e) {}

        // Read handler_obj data
        try {
            var field4 = args[0].add(4).readPointer();
            send({t: 'log', msg: '    handler->field4 = ' + field4});
        } catch(e3) {}

        // PC for BL instruction calculation
        // The handler code at 0xc14e0a2:
        // PUSH, LDR R0,[R0,#4], LDR R1,[R1], BL <target>, POP
        var pc = handlerAddr.add(8); // PC for BL instruction
        send({t: 'log', msg: '    PC at BL = ' + pc});

        // Read the BL instruction bytes
        try {
            var bli = handlerAddr.add(6).readByteArray(4);
            var bla = new Uint8Array(bli);
            var blHex = '';
            for (var i = 0; i < 4; i++) {
                blHex += ('0' + bla[i].toString(16)).slice(-2);
            }
            send({t: 'log', msg: '    BL bytes: ' + blHex});
        } catch(e4) {}

        this.handlerObj = args[0];
    }
});

// Also hook the BL target (we'll compute it or try to catch it via return address)
// For now, let's just read the handler code and compute the BL target
var handlerCode = handlerAddr.readByteArray(16);
var harr = new Uint8Array(handlerCode);
send({t: 'log', msg: 'Handler code at ' + handlerAddr + ':'});
var hhex = '';
for (var i = 0; i < 16; i++) {
    hhex += ('0' + harr[i].toString(16)).slice(-2) + ' ';
}
send({t: 'log', msg: '  ' + hhex});

// Decode BL: bytes at offset 6-9 are ff f7 f6 ff
// Using an online decoder approach
// H1=0xf7ff at offset 6, H2=0xfff6 at offset 8
// Let me try computing by hand based on ARM ref
// BL offset = S:I1:I2:imm10hi:imm10lo:0
// S=1, J1=1, J2=1? Let me re-parse

// Actually let me try all possible Thumb BL decoding formulas
// For ARM Thumb-2 BL:
//   imm32 = SignExtend(S:I1:I2:imm10:imm11:0, 32)
// Alternative split:
//   H1 = 0xf7ff = 1111 0 1 1111111111
//   H2 = 0xfff6 = 1111 1 1 1 1 0110

// Second halfword bit assignment:
// 11 1 1 1 1 0110
// J1=1 at bit 13, J2=1 at bit 11

// Wait J1 is actually bit 13: (0xfff6 >> 13) & 1 = 1
// J2 is bit 11: (0xfff6 >> 11) & 1 = 1

// imm10_H = 0x3FF (bits[9:0] of first halfword = 1111111111)
// imm10_L = bits[10:1] of second halfword

// bits[10:1] of 0xfff6:
// 0xfff6 = 1111 1111 1111 0110
// bits[10:1] = 1111110110 = 0x3F6

// Actually wait, let me use the other layout:
// Some references say the layout is:
// H2: 11 J1 1 J2 imm10_L
// where imm10_L = bits[9:0]
// bits[9:0] of 0xfff6 = 1101110110? No...

// Let me just write it out: 0xfff6
// binary: 1111 1111 1111 0110
// bits numbered 15 to 0: 1 1 1 1  1 1 1 1  1 1 1 1  0 1 1 0

// Actually there are two common layouts for BL:
// Layout A: 11 J1 1 J2 imm10
// Layout B: 11 1 J1 J2 imm10 (or similar)

// Let me try both and see which gives a reasonable target

// Layout A: bits[15:14]=11, bit[13]=J1, bit[12]=1, bit[11]=J2, bits[10:0]=imm11
// J1=1, J2=1, imm11 = 1111 0110 0? No, 11 bits from 10:0

// bits 10..0 of 0xfff6:
// 0xfff6: 1111 1111 1111 0110
// bits 10:0: 111 1111 0110 = 0x7F6

// Wait I keep going back and forth. Let me just try to read the BL target
// from the return address when the handler is called by hooking the frame

// Actually, let me try to directly hook the function at 0xf41e47d0
// (the field4 value from handler) since that's where the call goes

var field4Addr = ptr(0xf41e47d0);
send({t: 'log', msg: 'Trying to read at 0xf41e47d0...'});
try {
    var f4data = field4Addr.readByteArray(32);
    var f4arr = new Uint8Array(f4data);
    var f4hex = '';
    for (var i = 0; i < 32; i++) {
        f4hex += ('0' + f4arr[i].toString(16)).slice(-2) + ' ';
    }
    send({t: 'log', msg: 'Data at 0xf41e47d0: ' + f4hex});
} catch(e) {
    send({t: 'err', msg: 'Cannot read 0xf41e47d0: ' + e});
}

// Now test: arm and call
var testUrl = Memory.allocUtf8String('xqj://test_trace');
send({t: 'log', msg: '=== TRIGGERING CALL ==='});
try {
    var fn = new NativeFunction(jumpUrlFunc, 'void', ['pointer']);
    fn(testUrl);
    send({t: 'log', msg: 'Call returned OK'});
} catch(e) {
    send({t: 'err', msg: 'Call crashed: ' + e});
}

send({t: 'ready', msg: 'Trace done'});
