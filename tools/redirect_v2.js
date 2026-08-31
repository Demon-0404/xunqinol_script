// ============================================================
// 持续重定向 — 所有29B传送包都修改, 不自动disarm
// ============================================================

var libc = Process.getModuleByName("libc.so");
var gameFd = -1;
var redirectArmed = true; // 默认武装
var redirectCount = 0;

// 重定向XOR值
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
Interceptor.attach(libc.getExportByName("close"), {
    onEnter: function(args) {
        if (args[0].toInt32() === gameFd) {
            this.block = true;
            send({t: "block", msg: "close blocked"});
        }
    },
    onLeave: function(ret) {
        if (this.block) { ret.replace(0); this.block = false; }
    }
});

Interceptor.attach(libc.getExportByName("shutdown"), {
    onEnter: function(args) {
        if (args[0].toInt32() === gameFd) {
            this.block = true;
            send({t: "block", msg: "shutdown blocked"});
        }
    },
    onLeave: function(ret) {
        if (this.block) { ret.replace(0); this.block = false; }
    }
});

// Hook send
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
            for (var i = 20; i <= 23; i++) {
                buf.add(i).writeU8(buf.add(i).readU8() ^ XOR_PORTAL_ID);
            }
            buf.add(28).writeU8(buf.add(28).readU8() ^ XOR_CHECKSUM);
            redirectCount++;
        }

        var rawAfter = "";
        for (var i = 0; i < len; i++) {
            rawAfter += ("0" + buf.add(i).readU8().toString(16)).slice(-2);
        }

        var changed = rawBefore !== rawAfter;
        send({t: "portal", changed: changed, before: rawBefore, after: rawAfter,
              count: redirectCount});
    }
});

rpc.exports = {
    arm: function() { redirectArmed = true; return "ARMED"; },
    disarm: function() { redirectArmed = false; return "DISARMED"; },
    status: function() {
        return JSON.stringify({fd: gameFd, armed: redirectArmed, count: redirectCount});
    }
};

send({t: "ready", msg: "持续重定向已就绪! 所有29B传送包都会被修改"});
