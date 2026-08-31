// Try to call jlapp_jumpUrl by protecting the page and using NativeFunction
var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0); // jlapp_jumpUrl

send({t: 'log', msg: 'jlapp_jumpUrl @ ' + jumpUrlFunc});

// First, hook the function so we can observe when it's called
var hookCalled = false;
Interceptor.attach(jumpUrlFunc, {
    onEnter: function(args) {
        hookCalled = true;
        send({t: 'log', msg: '*** jlapp_jumpUrl HOOK FIRED ***'});
        send({t: 'log', msg: '  arg0: ' + args[0]});
        send({t: 'log', msg: '  arg1: ' + args[1]});
        send({t: 'log', msg: '  arg2: ' + args[2]});

        // Try to read arg0 as string
        try {
            // JNI functions take JNIEnv* as arg0, jobject as arg1, then actual args follow
            // For jlapp_jumpUrl, it might be: (JNIEnv* env, jobject thiz, jstring url)
            var str = args[2].readUtf8String(256);
            send({t: 'log', msg: '  arg2 as string: ' + str});
        } catch(e) {
            try {
                var str2 = args[0].readUtf8String(256);
                send({t: 'log', msg: '  arg0 as string: ' + str2});
            } catch(e2) {
                try {
                    var str3 = args[1].readUtf8String(256);
                    send({t: 'log', msg: '  arg1 as string: ' + str3});
                } catch(e3) {}
            }
        }

        // Print stack trace
        send({t: 'log', msg: '  Stack:'});
        var bt = Thread.backtrace(this.context, Backtracer.ACCURATE);
        for (var i = 0; i < Math.min(bt.length, 10); i++) {
            send({t: 'log', msg: '    ' + bt[i] + ' ' + DebugSymbol.fromAddress(bt[i])});
        }
    },
    onLeave: function(ret) {
        send({t: 'log', msg: '  Return: ' + ret});
    }
});
send({t: 'log', msg: 'Hook attached successfully'});

// Now try to make the page executable and call via NativeFunction
// The page at 0xc1ab000 needs to be 4096-aligned
var pageAddr = jumpUrlFunc.and(ptr(0xfffff000));
send({t: 'log', msg: 'Page address: ' + pageAddr});

try {
    // Change page protection to rwx
    Memory.protect(pageAddr, 4096, 'rwx');
    send({t: 'log', msg: 'Page protection changed to rwx'});

    // Try NativeFunction
    var jumpUrlNative = new NativeFunction(jumpUrlFunc, 'void', ['pointer']);
    send({t: 'log', msg: 'NativeFunction created, calling with test string...'});

    // Prepare a test string
    var testStr = Memory.allocUtf8String('test_url_scheme');

    jumpUrlNative(testStr);
    send({t: 'log', msg: 'Call returned! hookCalled=' + hookCalled});
} catch(e) {
    send({t: 'err', msg: 'NativeFunction error: ' + e});

    // Alternative: try to call through the global variable table
    // g_jumpUrlCall contains thunk stubs, let's try to find and call one
    send({t: 'log', msg: 'Trying alternative approach...'});
}

// Also: search for JNI_OnLoad which registers this native method
send({t: 'log', msg: '=== Searching for JNI_OnLoad ==='});

function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

var dynstrAddr = 0x2f178;
var dynsymAddr = 0x148;
var symEnt = 16;

for (var si = 0; si < 30000; si++) {
    var sym = base.add(dynsymAddr + si * symEnt);
    var st_name = readU32(sym);
    if (st_name === 0) continue;
    try {
        var sn = base.add(dynstrAddr + st_name).readUtf8String(128);
        if (sn.indexOf('JNI_OnLoad') !== -1 || sn.indexOf('RegisterNatives') !== -1 ||
            sn.indexOf('jni') !== -1 || sn.indexOf('JNI') !== -1) {
            var sv = readU32(sym.add(4));
            send({t: 'log', msg: '  ' + sn + ' @ 0x' + sv.toString(16)});
        }
    } catch(e) {}
}

// Hook send/recv briefly to detect game activity
// When the user does something in game, we want to know if jlapp_jumpUrl is called

send({t: 'ready', msg: 'jlapp_jumpUrl calling test ready. Hook is active - interact with the game to trigger it.'});
