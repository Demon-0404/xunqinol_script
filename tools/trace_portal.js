// ============================================================
// 天音 — 传送包调用栈追踪
// 在send()检测到29B传送包时，回溯调用栈找到上层C++函数
// ============================================================

var libc = Process.getModuleByName("libc.so");
var gameFd = -1;
var backtraces = [];

// 找游戏fd
var gpn = libc.getExportByName("getpeername");
var getpeername = new NativeFunction(gpn, "int", ["int", "pointer", "pointer"]);
for (var fd = 30; fd <= 200; fd++) {
    try {
        var addr = Memory.alloc(128);
        var alen = Memory.alloc(4);
        alen.writeInt(128);
        if (getpeername(fd, addr, alen) === 0) {
            var port = ((addr.add(2).readU8() << 8) | addr.add(3).readU8());
            if (port === 30002) { gameFd = fd; break; }
        }
    } catch(e) {}
}
send({t: "info", msg: "gameFd=" + gameFd});

// 枚举所有模块，用于地址→模块名+偏移的转换
var modules = {};
Process.enumerateModules().forEach(function(m) {
    modules[m.name] = {base: m.base, size: m.size};
});

function addrToModule(addr) {
    var best = null;
    for (var name in modules) {
        var m = modules[name];
        if (addr.compare(m.base) >= 0 && addr.compare(m.base.add(m.size)) < 0) {
            if (!best || m.base.compare(best.base) > 0) {
                best = {name: name, base: m.base};
            }
        }
    }
    if (best) {
        return best.name + "+0x" + addr.sub(best.base).toString(16);
    }
    return addr.toString();
}

// Hook send — 检测传送包+回溯调用栈
var traceCount = 0;
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== gameFd) return;

        // 检测29B传送包
        if (len === 29 && buf.readU8() === 0x03) {
            traceCount++;

            // 读取包内容
            var raw = "";
            for (var i = 0; i < len; i++) {
                raw += ("0" + buf.add(i).readU8().toString(16)).slice(-2);
            }

            // 回溯调用栈
            var bt = Thread.backtrace(this.context, Backtracer.ACCURATE);
            var frames = [];
            for (var i = 0; i < bt.length; i++) {
                var sym = DebugSymbol.fromAddress(bt[i]);
                frames.push({
                    addr: bt[i].toString(),
                    module: addrToModule(bt[i]),
                    symbol: sym.toString()
                });
            }

            backtraces.push({
                count: traceCount,
                raw: raw,
                frames: frames
            });

            send({t: "portal_trace", count: traceCount, raw: raw, frames: frames});

            // 详细打印调用栈
            send({t: "trace_detail", msg: "=== Backtrace #" + traceCount + " ==="});
            for (var j = 0; j < frames.length; j++) {
                var f = frames[j];
                send({t: "trace_frame", idx: j, module: f.module, symbol: f.symbol});
            }

            // 如果找到libtestcpp中的函数，反汇编前几条指令
            for (var k = 0; k < Math.min(frames.length, 10); k++) {
                if (frames[k].module.indexOf("libtestcpp") >= 0 || frames[k].module.indexOf("libgame") >= 0) {
                    var funcAddr = ptr(frames[k].addr);
                    send({t: "found_func", idx: k, module: frames[k].module, addr: frames[k].addr});
                }
            }
        }
    }
});

rpc.exports = {
    getTraces: function() { return JSON.stringify(backtraces); },
    getLastTrace: function() {
        if (backtraces.length === 0) return "{}";
        return JSON.stringify(backtraces[backtraces.length - 1]);
    },
    getCount: function() { return backtraces.length; },
    clear: function() { backtraces = []; return "OK"; },
    getGameFd: function() { return gameFd; }
};

send({t: "ready", msg: "调用栈追踪就绪", msg2: "走传送门，我会抓取上层C++函数调用链", fd: gameFd});
