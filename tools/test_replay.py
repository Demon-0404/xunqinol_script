"""Test: replay captured portal packet to redirect"""
import frida, time, sys, json

DEV = "127.0.0.1:27056"
PID = 5630
PORTAL_1 = "03136f136e126e166e126e127e027e027e027e0dd7abd7abdba7dba7ce"
PORTAL_2 = "030478047905790179057905691569156915691ac1bdc1bdc3bfc3bfc4"

js = """
var libc = Process.getModuleByName("libc.so");
var gameFd = -1;
var replayArmed = false;
var replayData = null;
var sessionKey = 0;

// Find game fd
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

// Hook send to detect portal and optionally replays
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== gameFd) return;

        if (len === 29 && buf.readU8() === 0x03) {
            var raw = "";
            for (var i = 0; i < len; i++) {
                raw += ("0" + buf.add(i).readU8().toString(16)).slice(-2);
            }
            send({t: "portal", raw: raw});

            // If replay armed, replace packet content
            if (replayArmed && replayData) {
                for (var i = 0; i < 29; i++) {
                    var b = parseInt(replayData.substring(i*2, i*2+2), 16);
                    buf.add(i).writeU8(b);
                }
                replayArmed = false;
                send({t: "replay", msg: "Portal packet REPLACED!"});
            }
        }
    }
});

// Hook recv for key detection
Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.doProcess = (this.fd === gameFd);
    },
    onLeave: function(ret) {
        if (!this.doProcess) return;
        var realLen = ret.toInt32();
        if (realLen <= 0) return;
        if (sessionKey === 0 && realLen >= 4) {
            var b0 = this.buf.readU8();
            var b1 = this.buf.add(1).readU8();
            var b2 = this.buf.add(2).readU8();
            var b3 = this.buf.add(3).readU8();
            if (b1 === b2 && b2 === b3) {
                sessionKey = b0 ^ 0x02;
                send({t: "key", key: sessionKey});
            }
        }
    }
});

// Block close/shutdown
Interceptor.attach(libc.getExportByName("close"), {
    onEnter: function(args) {
        if (args[0].toInt32() === gameFd) {
            this.block = true;
            send({t: "warn", msg: "close() BLOCKED"});
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
            send({t: "warn", msg: "shutdown() BLOCKED"});
        }
    },
    onLeave: function(ret) {
        if (this.block) { ret.replace(0); this.block = false; }
    }
});

rpc.exports = {
    armReplay: function(hex) {
        replayData = hex;
        replayArmed = true;
        return "ARMED: next portal will be replaced with " + hex.substring(0, 8) + "...";
    },
    disarm: function() { replayArmed = false; return "DISARMED"; },
    getKey: function() { return sessionKey; },
    getStatus: function() { return JSON.stringify({fd: gameFd, key: sessionKey, armed: replayArmed}); },
    // Direct send via game socket
    sendRaw: function(hex) {
        if (gameFd < 0) return "no fd";
        var len = hex.length / 2;
        var buf = Memory.alloc(len);
        for (var i = 0; i < len; i++) {
            buf.add(i).writeU8(parseInt(hex.substring(i*2, i*2+2), 16));
        }
        var sendPtr = libc.getExportByName("send");
        var sendFn = new NativeFunction(sendPtr, "int", ["int", "pointer", "int", "int"]);
        var ret = sendFn(gameFd, buf, len, 0);
        return "sent " + len + "B, ret=" + ret;
    }
};

send({t: "ready", msg: "Replay test ready. fd=" + gameFd});
"""

dev = frida.get_device_manager().add_remote_device(DEV)
session = dev.attach(PID)
script = session.create_script(js)

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict): return
    t = p.get("t", "")
    if t == "ready": print(f"[READY] {p['msg']}")
    elif t == "info": print(f"[INFO] {p['msg']}")
    elif t == "warn": print(f"[WARN] {p['msg']}")
    elif t == "key": print(f"[KEY] 0x{p['key']:02x}")
    elif t == "portal": print(f"[PORTAL] {p['raw']}")
    elif t == "replay": print(f"[REPLAY] {p['msg']}")
    else: print(f"[{t}]")
    sys.stdout.flush()

script.on("message", on_msg)
script.load()
time.sleep(1)
print("\n=== 回放测试就绪 ===")
print("PORTAL_1 (原始):", PORTAL_1)
print("PORTAL_2 (目标):", PORTAL_2)
print()

stat = json.loads(script.exports_sync.get_status())
print(f"fd={stat['fd']} key={stat['key']} armed={stat['armed']}")
print()

# Step 1: Arm replay with Portal 2
print("武装回放: 下次走传送门时替换为 Portal #2")
script.exports_sync.arm_replay(PORTAL_2)
print()

print("现在去游戏里点任意传送门，我会把包替换成 Portal #2")
print("观察: 是否被传送到不同的目的地?")
print()

try:
    time.sleep(120)
except KeyboardInterrupt:
    pass

try:
    script.exports_sync.disarm()
except: pass
try:
    session.detach()
except: pass
print("Done")
