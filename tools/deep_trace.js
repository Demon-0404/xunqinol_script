// ============================================================
// 深度调用栈追踪 — 在send() onLeave回溯到游戏逻辑层
// ============================================================

var libc = Process.getModuleByName("libc.so");
var libtcb = Process.getModuleByName("libtcb.so");
var tcbBase = libtcb.base;
var gameFd = -1;
var traceCount = 0;
var allTraces = [];

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
send({t: "info", msg: "fd=" + gameFd + " tcbBase=" + tcbBase});

// 枚举所有模块用于地址解析
var modulesList = [];
Process.enumerateModules().forEach(function(m) {
    modulesList.push({name: m.name, base: m.base, size: m.size});
});

function resolveAddr(ptrAddr) {
    for (var mi = 0; mi < modulesList.length; mi++) {
        var m = modulesList[mi];
        if (ptrAddr.compare(m.base) >= 0 && ptrAddr.compare(m.base.add(m.size)) < 0) {
            return m.name + "+0x" + ptrAddr.sub(m.base).toString(16);
        }
    }
    return ptrAddr.toString();
}

// Hook send — 在onLeave时做深度回溯
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.len = args[2].toInt32();
    },
    onLeave: function(ret) {
        if (this.fd !== gameFd) return;
        if (this.len !== 29) return;
        if (this.buf.readU8() !== 0x03) return;

        traceCount++;
        var raw = "";
        for (var i = 0; i < 29; i++) {
            raw += ("0" + this.buf.add(i).readU8().toString(16)).slice(-2);
        }
        send({t: "portal", count: traceCount, raw: raw});

        // 用FUZZY模式回溯更多帧
        var bt = Thread.backtrace(this.context, Backtracer.ACCURATE);
        send({t: "trace", count: traceCount, totalFrames: bt.length});

        // 先收集所有帧
        var frames = [];
        for (var i = 0; i < bt.length; i++) {
            var mod = resolveAddr(bt[i]);
            frames.push({idx: i, addr: bt[i].toString(), mod: mod});
        }

        // 找到libtcb中的帧
        send({t: "trace_detail", msg: "=== Portal #" + traceCount + " backtrace ==="});
        var shownLibtcb = 0;
        for (var j = 0; j < frames.length; j++) {
            var f = frames[j];
            if (f.mod.indexOf("libtcb") >= 0) {
                send({t: "libtcb_frame", idx: j, mod: f.mod, addr: f.addr});
                shownLibtcb++;

                // 反汇编前5条指令
                try {
                    var funcAddr = ptr(f.addr);
                    send({t: "disasm", idx: j, addr: f.addr, mod: f.mod});
                    var cursor = funcAddr;
                    for (var k = 0; k < 8; k++) {
                        try {
                            var insn = Instruction.parse(cursor);
                            var bytes = "";
                            var arr = new Uint8Array(cursor.readByteArray(insn.size));
                            for (var b = 0; b < insn.size; b++) {
                                bytes += ("0" + arr[b].toString(16)).slice(-2);
                            }
                            send({t: "insn", offset: cursor.sub(funcAddr).toInt32(),
                                  bytes: bytes, asm: insn.mnemonic + " " + insn.operands});
                            cursor = cursor.add(insn.size);
                        } catch(e) {
                            cursor = cursor.add(1);
                        }
                    }
                } catch(e) {}
            }
            // 也打印非libtcb的帧(前10帧)
            if (j < 10 && f.mod.indexOf("libtcb") < 0) {
                send({t: "other_frame", idx: j, mod: f.mod, addr: f.addr});
            }
        }

        // 保存完整trace
        allTraces.push({count: traceCount, raw: raw, frames: frames});
        send({t: "libtcb_count", count: shownLibtcb, msg: "libtcb frames: " + shownLibtcb});

        // 如果找到libtcb帧，尝试读取帧1(上层调用者)附近的函数
        // 找第一个非libtcb+0x20341的libtcb帧
        for (var fj = 0; fj < frames.length; fj++) {
            if (frames[fj].mod.indexOf("libtcb") >= 0 && frames[fj].mod.indexOf("0x20341") < 0) {
                var upperAddr = ptr(frames[fj].addr);
                send({t: "candidate", idx: fj, addr: frames[fj].addr, mod: frames[fj].mod,
                      msg: "!!! 候选portal函数 !!!"});
                break;
            }
        }
    }
});

rpc.exports = {
    getTraces: function() { return JSON.stringify(allTraces); },
    getCount: function() { return traceCount; },
    getGameFd: function() { return gameFd; }
};

send({t: "ready", msg: "深度追踪就绪，走传送门"});
