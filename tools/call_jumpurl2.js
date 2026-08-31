// Try calling jlapp_jumpUrl with different argument combinations
var base = ptr(0xc074000);
var jumpUrlFunc = base.add(0x1375d0);

send({t: 'log', msg: 'jlapp_jumpUrl @ ' + jumpUrlFunc});

// Hook to observe
Interceptor.attach(jumpUrlFunc, {
    onEnter: function(args) {
        send({t: 'log', msg: '=== jlapp_jumpUrl CALLED ==='});
        send({t: 'log', msg: '  arg0: ' + args[0] + ' (R0)');
        send({t: 'log', msg: '  arg1: ' + args[1] + ' (R1)');
        send({t: 'log', msg: '  arg2: ' + args[2] + ' (R2)');
        send({t: 'log', msg: '  arg3: ' + args[3] + ' (R3)');

        // Try to read each arg as string
        for (var ai = 0; ai < 4; ai++) {
            try {
                var s = args[ai].readUtf8String(128);
                if (s && s.length > 0 && s.length < 128) {
                    send({t: 'log', msg: '  arg' + ai + ' as string: "' + s + '"'});
                }
            } catch(e) {}
        }

        // Save args for post-call analysis
        this.a0 = args[0];
        this.a1 = args[1];
        this.a2 = args[2];
        this.a3 = args[3];

        // Stack trace (libhoudini addresses may be useful)
        send({t: 'log', msg: '  Stack trace:'});
        var bt = Thread.backtrace(this.context, Backtracer.ACCURATE);
        for (var i = 0; i < Math.min(bt.length, 8); i++) {
            send({t: 'log', msg: '    ' + bt[i] + ' ' + DebugSymbol.fromAddress(bt[i])});
        }
    },
    onLeave: function(ret) {
        send({t: 'log', msg: '  Return value: ' + ret});
    }
});

// Protect the page
var pageAddr = jumpUrlFunc.and(ptr(0xfffff000));
Memory.protect(pageAddr, 4096, 'rwx');
send({t: 'log', msg: 'Page protected: rwx'});

// Allocate some pointers to pass as JNIEnv* and jobject
var fakeEnv = Memory.alloc(256);  // dummy JNIEnv*
var fakeThiz = Memory.alloc(64);  // dummy jobject

// Try 1: Pass 3 args (JNI style: env, thiz, url)
send({t: 'log', msg: '=== Test 1: 3 args (env, thiz, url) ==='});
try {
    var url1 = Memory.allocUtf8String('jump_to_map_1');
    var fn3 = new NativeFunction(jumpUrlFunc, 'void', ['pointer', 'pointer', 'pointer']);
    send({t: 'log', msg: 'Calling with 3 args...'});
    fn3(fakeEnv, fakeThiz, url1);
    send({t: 'log', msg: 'Call returned successfully!'});
} catch(e) {
    send({t: 'err', msg: 'Test 1 failed: ' + e});
}

// Try 2: Pass 1 arg (just URL, original approach)
send({t: 'log', msg: '=== Test 2: 1 arg (url only) ==='});
try {
    var url2 = Memory.allocUtf8String('jump_to_map_2');
    var fn1 = new NativeFunction(jumpUrlFunc, 'void', ['pointer']);
    send({t: 'log', msg: 'Calling with 1 arg...'});
    fn1(url2);
    send({t: 'log', msg: 'Call returned successfully!'});
} catch(e) {
    send({t: 'err', msg: 'Test 2 failed: ' + e});
}

// Try 3: Pass 2 args (url, context)
send({t: 'log', msg: '=== Test 3: 2 args (url, context) ==='});
try {
    var url3 = Memory.allocUtf8String('jump_to_map_3');
    var ctx = Memory.alloc(64);
    var fn2 = new NativeFunction(jumpUrlFunc, 'void', ['pointer', 'pointer']);
    send({t: 'log', msg: 'Calling with 2 args...'});
    fn2(url3, ctx);
    send({t: 'log', msg: 'Call returned successfully!'});
} catch(e) {
    send({t: 'err', msg: 'Test 3 failed: ' + e});
}

// Try 4: Try to find the Java class by searching memory for class name strings
send({t: 'log', msg: '=== Searching for MainActivity string in memory ==='});
var searchPatterns = ['MainActivity', 'xqj', 'jumpUrl', 'com/xqj'];
for (var spi = 0; spi < searchPatterns.length; spi++) {
    try {
        var results = Memory.scanSync(base, 0x480000, searchPatterns[spi]);
        send({t: 'log', msg: '  "' + searchPatterns[spi] + '": ' + results.length + ' matches'});
        for (var ri = 0; ri < Math.min(results.length, 5); ri++) {
            var matchAddr = results[ri].address;
            try {
                var contextStr = matchAddr.sub(32).readUtf8String(128);
                send({t: 'log', msg: '    @ ' + matchAddr + ': ...' + contextStr + '...'});
            } catch(e2) {}
        }
    } catch(e3) {
        send({t: 'err', msg: '  Scan error for "' + searchPatterns[spi] + '": ' + e3});
    }
}

send({t: 'ready', msg: 'All tests done. Check hook logs for results.'});
