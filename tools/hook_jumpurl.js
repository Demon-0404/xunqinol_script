// Hook jlapp_jumpUrl and explore calling it directly
// ARM offset: 0x1375d0, absolute: 0xc1ab5d0
// g_jumpUrlCall global: ARM offset 0x464a18, absolute: 0xc4d8a18, value: 0xc4ba1e8

var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0); // jlapp_jumpUrl
var g_jumpUrlCall = base.add(0x464a18); // global variable

send({t: 'log', msg: 'jlapp_jumpUrl @ ' + jumpUrlFunc});
send({t: 'log', msg: 'g_jumpUrlCall @ ' + g_jumpUrlCall});

// Read the global variable value
try {
    var gValPtr = g_jumpUrlCall.readPointer();
    send({t: 'log', msg: 'g_jumpUrlCall value (pointer): ' + gValPtr});
    // Read what it points to
    try {
        var pointedData = gValPtr.readByteArray(64);
        var arr = new Uint8Array(pointedData);
        var hex = '';
        for (var i = 0; i < 64; i++) {
            hex += ('0' + arr[i].toString(16)).slice(-2) + ' ';
        }
        send({t: 'log', msg: 'Data at *g_jumpUrlCall: ' + hex});
    } catch(e) {
        send({t: 'log', msg: 'Cannot read *g_jumpUrlCall: ' + e});
    }
} catch(e) {
    send({t: 'err', msg: 'Cannot read g_jumpUrlCall: ' + e});
}

// Read the function prologue to understand its signature
try {
    var code = jumpUrlFunc.readByteArray(64);
    var arr = new Uint8Array(code);
    var hex = '';
    for (var i = 0; i < 64; i++) {
        hex += ('0' + arr[i].toString(16)).slice(-2) + ' ';
        if ((i + 1) % 16 === 0) hex += '\n          ';
    }
    send({t: 'log', msg: 'jlapp_jumpUrl code:\n          ' + hex});
} catch(e) {
    send({t: 'err', msg: 'Cannot read function code: ' + e});
}

// Try to hook the function
try {
    Interceptor.attach(jumpUrlFunc, {
        onEnter: function(args) {
            send({t: 'log', msg: '*** jlapp_jumpUrl CALLED ***'});
            send({t: 'log', msg: '  arg0: ' + args[0]});
            send({t: 'log', msg: '  arg1: ' + args[1]});
            send({t: 'log', msg: '  arg2: ' + args[2]});
            send({t: 'log', msg: '  arg3: ' + args[3]});

            // Try to read arg0 as string (likely a URL string)
            try {
                var str = args[0].readUtf8String(256);
                send({t: 'log', msg: '  arg0 as string: ' + str});
            } catch(e) {}

            try {
                var str2 = args[1].readUtf8String(256);
                send({t: 'log', msg: '  arg1 as string: ' + str2});
            } catch(e) {}

            // Stack trace
            send({t: 'log', msg: '  Stack trace:'});
            var bt = Thread.backtrace(this.context, Backtracer.ACCURATE);
            for (var i = 0; i < bt.length; i++) {
                var sym = DebugSymbol.fromAddress(bt[i]);
                send({t: 'log', msg: '    ' + bt[i] + ' ' + sym});
            }
        },
        onLeave: function(ret) {
            send({t: 'log', msg: '  Return value: ' + ret});
        }
    });
    send({t: 'log', msg: 'Interceptor attached to jlapp_jumpUrl'});
} catch(e) {
    send({t: 'err', msg: 'Cannot hook jlapp_jumpUrl: ' + e});
}

// Also hook nearby JNI functions to understand the pattern
var nearbyFuncs = {
    'jlapp_close': 0, // will find offset
};

// Search for jlapp_close in dynsym (we know it's near jlapp_jumpUrl string)
// Let's just try hooking at various offsets near jlapp_jumpUrl
// jlapp_jumpUrl is at 0x1375d0, size 128 bytes (0x80)
// So it spans 0x1375d0 - 0x137650
// Other jlapp_* functions should be nearby

send({t: 'log', msg: 'Scanning for nearby JNI functions...'});

// Read the dynsym to find all jlapp_* functions
function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

var dynstrAddr = 0x2f178;
var dynsymAddr = 0x148;
var dynsymEnt = 16;
// We know DT_STRSZ = 427554, so scan a reasonable number of symbols
// Actually we know from investigate_jumpurl.js that there are ~20000+ symbols

// Scan dynsym for all jlapp_* and g_* symbols
send({t: 'log', msg: '=== All jlapp_* and g_* symbols ==='});
var symOff = dynsymAddr;
var si = 0;
while (si < 30000) {
    var sym = base.add(symOff + si * dynsymEnt);
    var st_name = readU32(sym);
    if (st_name === 0) { si++; continue; }

    var nameAddr = base.add(dynstrAddr + st_name);
    try {
        var symName = nameAddr.readUtf8String(64);
        if (symName.indexOf('jlapp_') === 0 || symName.indexOf('g_') === 0) {
            var st_value = readU32(sym.add(4));
            var st_size = readU32(sym.add(8));
            send({t: 'log', msg: '  ' + symName + ' @ 0x' + st_value.toString(16) + ' size=' + st_size});
        }
    } catch(e) {}
    si++;
}

send({t: 'ready', msg: 'jlapp_jumpUrl hook exploration done'});
