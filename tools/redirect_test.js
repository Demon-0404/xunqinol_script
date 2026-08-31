// ============================================================
// 实时传送门重定向 — XOR bytes 20-23 (门ID) + byte 28 (校验)
// Portal 1 → Portal 2: XOR[20..23]=0x01, XOR[28]=0x1d
// ============================================================

var libc = Process.getModuleByName("libc.so");
var gameFd = -1;
var redirectArmed = false;
var redirectCount = 0;

// 重定向参数 (XOR values)
var XOR_PORTAL_ID = 0x01;  // bytes 20-23
var XOR_CHECKSUM  = 0x1d;  // byte 28

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
send({t: "info", msg: "fd=" + gameFd});

// 阻止断网
var closeBlocked = 0;
Interceptor.attach(libc.getExportByName("close"), {
    onEnter: function(args) {
        if (args[0].toInt32() === gameFd) {
            closeBlocked++;
            this.block = true;
            send({t: "close_blocked", total: closeBlocked});
        }
    },
    onLeave: function(ret) {
        if (this.block) { ret.replace(0); this.block = false; }
    }
});

var shutdownBlocked = 0;
Interceptor.attach(libc.getExportByName("shutdown"), {
    onEnter: function(args) {
        if (args[0].toInt32() === gameFd) {
            shutdownBlocked++;
            this.block = true;
            send({t: "shutdown_blocked", total: shutdownBlocked});
        }
    },
    onLeave: function(ret) {
        if (this.block) { ret.replace(0); this.block = false; }
    }
});

// Hook send — 实时重定向传送包
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== gameFd) return;
        if (len !== 29 || buf.readU8() !== 0x03) return;

        var rawBefore = "";
        for (var i = 0; i < len; i++) {
            rawBefore += ("0" + buf.add(i).readU8().toString(16)).slice(-2);
        }

        if (redirectArmed) {
            // XOR bytes 20-23 (门ID)
            for (var i = 20; i <= 23; i++) {
                buf.add(i).writeU8(buf.add(i).readU8() ^ XOR_PORTAL_ID);
            }
            // XOR byte 28 (校验和)
            buf.add(28).writeU8(buf.add(28).readU8() ^ XOR_CHECKSUM);
            redirectCount++;
            redirectArmed = false; // 只重定向一次
        }

        var rawAfter = "";
        for (var i = 0; i < len; i++) {
            rawAfter += ("0" + buf.add(i).readU8().toString(16)).slice(-2);
        }

        send({t: "portal", before: rawBefore, after: rawAfter, redirected: redirectCount,
              msg: redirectCount > 0 ? "!!! REDIRECTED !!!" : "normal portal"});
    }
});

rpc.exports = {
    arm: function() { redirectArmed = true; return "ARMED: next portal will be redirected"; },
    disarm: function() { redirectArmed = false; return "DISARMED"; },
    status: function() {
        return JSON.stringify({
            fd: gameFd,
            armed: redirectArmed,
            redirectCount: redirectCount,
            closeBlocked: closeBlocked,
            shutdownBlocked: shutdownBlocked
        });
    },
    setXor: function(portalXor, checksumXor) {
        XOR_PORTAL_ID = parseInt(portalXor) || 0x01;
        XOR_CHECKSUM = parseInt(checksumXor) || 0x1d;
        return "XOR set: portal=0x" + XOR_PORTAL_ID.toString(16) + " checksum=0x" + XOR_CHECKSUM.toString(16);
    }
};

send({t: "ready", msg: "重定向就绪!", msg2: "用 arm() 武装, 然后走传送门", fd: gameFd});
