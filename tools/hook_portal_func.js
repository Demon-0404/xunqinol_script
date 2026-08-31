// Hook the C++ portal handler chain to trace and modify destination
// handler@0xc276018 (vtable[6], Thumb → actual 0xc276018)
// The handler constructs the portal packet - hook it to see arguments

var handlerAddr = ptr(0xc276018);  // Thumb mode
var func1Addr = ptr(0xc354228);    // Thumb mode
var func2Addr = ptr(0xc35442c);    // Thumb mode

var traceCount = 0;

// Hook the portal handler (vtable[6])
try {
    Interceptor.attach(handlerAddr, {
        onEnter: function(args) {
            traceCount++;
            send({
                t: 'handler_enter',
                count: traceCount,
                r0: args[0].toString(),
                r1: args[1].toString(),
                r2: args[2].toString(),
                r3: args[3].toString()
            });

            // Log stack args if any
            var sp = this.context.sp;
            if (sp) {
                var stack0 = sp.readPointer();
                var stack1 = sp.add(4).readPointer();
                send({
                    t: 'handler_stack',
                    count: traceCount,
                    stack0: stack0.toString(),
                    stack1: stack1.toString()
                });
            }

            // Try to read strings from args
            try {
                if (args[1] && !args[1].isNull()) {
                    var str = args[1].readCString();
                    if (str && str.length > 0 && str.length < 200) {
                        send({t: 'handler_str', count: traceCount, arg: 1, str: str});
                    }
                }
            } catch(e) {}
            try {
                if (args[2] && !args[2].isNull()) {
                    var str2 = args[2].readCString();
                    if (str2 && str2.length > 0 && str2.length < 200) {
                        send({t: 'handler_str', count: traceCount, arg: 2, str: str2});
                    }
                }
            } catch(e) {}
        },
        onLeave: function(ret) {
            send({t: 'handler_leave', count: traceCount, ret: ret.toString()});
        }
    });
    send({t: 'log', msg: 'Handler hook installed at ' + handlerAddr});
} catch(e) {
    send({t: 'error', msg: 'Handler hook failed: ' + e});
}

// Hook func1
try {
    Interceptor.attach(func1Addr, {
        onEnter: function(args) {
            send({
                t: 'func1_enter',
                r0: args[0].toString(),
                r1: args[1].toString(),
                r2: args[2].toString(),
                r3: args[3].toString()
            });
        }
    });
    send({t: 'log', msg: 'func1 hook installed at ' + func1Addr});
} catch(e) {
    send({t: 'error', msg: 'func1 hook failed: ' + e});
}

// Hook func2
try {
    Interceptor.attach(func2Addr, {
        onEnter: function(args) {
            send({
                t: 'func2_enter',
                r0: args[0].toString(),
                r1: args[1].toString(),
                r2: args[2].toString(),
                r3: args[3].toString()
            });
        }
    });
    send({t: 'log', msg: 'func2 hook installed at ' + func2Addr});
} catch(e) {
    send({t: 'error', msg: 'func2 hook failed: ' + e});
}

send({t: 'ready', msg: 'Hooks installed. Click a portal!'});
