// Probe multiple BL target candidates to find the real one
var base = ptr(0xc074000);
var handlerAddr = ptr(0xc14e0a2);

// Protect pages
Memory.protect(handlerAddr.and(ptr(0xfffff000)), 4096, 'rwx');

// Read handler code
var hcode = handlerAddr.readByteArray(16);
var harr = new Uint8Array(hcode);
var hhex = '';
for (var i = 0; i < 16; i++) {
    hhex += ('0' + harr[i].toString(16)).slice(-2) + ' ';
}
send({t: 'log', msg: 'Handler code: ' + hhex});

// BL instruction at handler+6: ff f7 f6 ff
// H1=0xf7ff, H2=0xfff6
//
// ARMv7-AR manual BL (T1):
// H1: 1111 0 S imm10H[9:0]
// H2: 11  J1 1  J2 imm11[10:0]
// imm32 = SignExtend(S:J2:J1:imm10H:imm11:'0', 32)
//
// OR equivalently: I1=NOT(J1^S), I2=NOT(J2^S)
// imm32 = SignExtend(S:I1:I2:imm10H:imm11:'0', 32)

var S = 1;
var J1 = 1;
var J2 = 1;
var imm10H = 0x3FF;
var imm11 = 0xFFF6 & 0x7FF; // bits[10:0] = 0x7F6

// Method 1: Standard ARM manual decode
// imm25 = S:J2:J1:imm10H:imm11:'0'
var offset_m1 = (S << 24) | (J2 << 23) | (J1 << 22) | (imm10H << 12) | (imm11 << 1);
// Sign extend from 25 bits
if (offset_m1 & (1 << 24)) {
    offset_m1 = offset_m1 - (1 << 25);
}
var pc = handlerAddr.add(10); // handlerAddr + 6 + 4
var target_m1 = pc.add(offset_m1);
var msg1 = 'Method1 (ARM manual): offset=' + offset_m1 + ' target=' + target_m1;
send({t: 'log', msg: msg1});

// Method 2: Script's earlier compute (imm10_L 10-bit)
var I1 = (~(J1 ^ S)) & 1;
var I2 = (~(J2 ^ S)) & 1;
var imm10_L = 0x3F6;
var imm24_m2 = (S << 23) | (I1 << 22) | (I2 << 21) | (imm10H << 11) | imm10_L;
var offset_m2 = imm24_m2;
if (imm24_m2 & (1 << 23)) {
    offset_m2 = imm24_m2 - (1 << 24);
}
var target_m2 = pc.add(offset_m2);
var msg2 = 'Method2 (10-bit lo): offset=' + offset_m2 + ' target=' + target_m2;
send({t: 'log', msg: msg2});

// Read code at all candidate targets
var candidates = [target_m1, target_m2];
for (var ci = 0; ci < candidates.length; ci++) {
    var t = candidates[ci];
    try {
        Memory.protect(t.and(ptr(0xfffff000)), 4096, 'rwx');
        var tc = t.readByteArray(32);
        var ta = new Uint8Array(tc);
        var th = '';
        for (var j = 0; j < 32; j++) {
            th += ('0' + ta[j].toString(16)).slice(-2) + ' ';
        }
        var msg3 = 'Code at ' + t + ': ' + th;
        send({t: 'log', msg: msg3});
    } catch(e) {
        var msg4 = 'Cannot read ' + t + ': ' + e;
        send({t: 'err', msg: msg4});
    }
}

// Hook ALL candidate targets + also try the address at target_m2+4 (0xc14dca6) which
// looks like the real function start (after the NOP+BX LR padding)
var target_m2_plus4 = target_m2.add(4); // 0xc14dca6
Memory.protect(target_m2_plus4.and(ptr(0xfffff000)), 4096, 'rwx');

var hookTargets = [target_m1, target_m2, target_m2_plus4];
for (var hi = 0; hi < hookTargets.length; hi++) {
    var ht = hookTargets[hi];
    (function(theAddr, idx) {
        try {
            Interceptor.attach(theAddr, {
                onEnter: function(args) {
                    var m = '[TARGET' + idx + '] HIT! addr=' + theAddr + ' R0=' + args[0] + ' R1=' + args[1];
                    send({t: 'log', msg: m});
                }
            });
            var msg5 = 'Hooked target[' + idx + '] at ' + theAddr;
            send({t: 'log', msg: msg5});
        } catch(e) {
            var msg6 = 'Failed to hook target[' + idx + '] at ' + theAddr + ': ' + e;
            send({t: 'err', msg: msg6});
        }
    })(ht, hi);
}

// Now call handler
var handlerObj = ptr(0x0c4d8a18);
var testUrl = Memory.allocUtf8String('xqj://test_probe');
var urlPtrPtr = Memory.alloc(4);
urlPtrPtr.writePointer(testUrl);

send({t: 'log', msg: '=== Calling handler ==='});

try {
    var handlerFn = new NativeFunction(handlerAddr, 'void', ['pointer', 'pointer']);
    handlerFn(handlerObj, urlPtrPtr);
    send({t: 'log', msg: 'Handler returned OK!'});
} catch(e) {
    var msg7 = 'Handler crashed: ' + e;
    send({t: 'err', msg: msg7});
}

send({t: 'ready', msg: 'done'});
