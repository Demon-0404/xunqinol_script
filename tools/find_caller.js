// ============================================================
// 从 libtcb.so!send_wrapper 向上追溯到portal构建函数
// libtcb.so base: 0xd1a0000
// send wrapper: libtcb.so+0x20341 (from trace_portal.js)
// ============================================================

var libc = Process.getModuleByName("libc.so");
var libtcb = Process.getModuleByName("libtcb.so");
var tcbBase = libtcb.base;
var gameFd = -1;
var traceCount = 0;
var interestingFrames = [];

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
send({t: "info", msg: "gameFd=" + gameFd + " tcbBase=" + tcbBase});

// Hook send() wrapper in libtcb.so (the function that directly calls libc's send)
var sendWrapper = tcbBase.add(0x20341);
send({t: "info", msg: "sendWrapper=" + sendWrapper});

Interceptor.attach(sendWrapper, {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.len = args[2].toInt32();
        this.isPortal = (this.fd === gameFd && this.len === 29 && args[1].readU8() === 0x03);
    },
    onLeave: function(ret) {
        if (!this.isPortal) return;

        traceCount++;
        var bt = Thread.backtrace(this.context, Backtracer.ACCURATE);
        send({t: "trace", count: traceCount, frames: bt.length});

        var frames = [];
        for (var i = 0; i < bt.length; i++) {
            var addr = bt[i];
            var modName = "?";
            var modOffset = addr.toString();

            // 查找地址属于哪个模块
            Process.enumerateModules().forEach(function(m) {
                if (addr.compare(m.base) >= 0 && addr.compare(m.base.add(m.size)) < 0) {
                    modName = m.name;
                    modOffset = m.name + "+0x" + addr.sub(m.base).toString(16);
                }
            });

            // 也尝试解析符号
            var sym = DebugSymbol.fromAddress(addr);

            frames.push({idx: i, addr: addr.toString(), mod: modOffset, sym: sym.toString()});
            send({t: "frame", count: traceCount, idx: i, mod: modOffset, sym: sym.toString()});

            // 记录libtcb中的调用帧
            if (modName === "libtcb.so" && i > 0 && interestingFrames.length < 20) {
                var offset = addr.sub(tcbBase).toInt32();
                var found = false;
                for (var fi = 0; fi < interestingFrames.length; fi++) {
                    if (interestingFrames[fi].offset === offset) { found = true; break; }
                }
                if (!found) {
                    interestingFrames.push({
                        offset: offset,
                        addr: addr.toString(),
                        hexOffset: "0x" + offset.toString(16)
                    });
                    send({t: "interesting", offset: "0x" + offset.toString(16), addr: addr.toString()});
                }
            }
        }
    }
});

// 同时hook send来抓包本身
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (fd !== gameFd) return;
        var len = args[2].toInt32();
        if (len === 29 && args[1].readU8() === 0x03) {
            var raw = "";
            for (var i = 0; i < len; i++) {
                raw += ("0" + args[1].add(i).readU8().toString(16)).slice(-2);
            }
            send({t: "portal", raw: raw});
        }
    }
});

rpc.exports = {
    getInteresting: function() { return JSON.stringify(interestingFrames); },
    getCount: function() { return traceCount; },
    getGameFd: function() { return gameFd; },
    // 反汇编libtcb中的某个偏移
    disasmOffset: function(hexOffset) {
        var off = parseInt(hexOffset, 16);
        var addr = tcbBase.add(off);
        var result = [];
        var cursor = addr;
        for (var i = 0; i < 30; i++) {
            try {
                var insn = Instruction.parse(cursor);
                var bytes = "";
                var arr = new Uint8Array(cursor.readByteArray(insn.size));
                for (var j = 0; j < insn.size; j++) {
                    bytes += ("0" + arr[j].toString(16)).slice(-2);
                }
                result.push({
                    offset: cursor.sub(addr).toInt32(),
                    bytes: bytes,
                    asm: insn.mnemonic + " " + insn.operands
                });
                cursor = cursor.add(insn.size);
            } catch(e) {
                result.push({offset: cursor.sub(addr).toInt32(), err: e.toString()});
                cursor = cursor.add(1);
            }
        }
        return JSON.stringify(result);
    }
};

send({t: "ready", msg: "sendWrapper hook就绪，走传送门!"});
