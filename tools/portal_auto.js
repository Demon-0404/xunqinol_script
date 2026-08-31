// portal_auto.js - simplest possible, no key needed for detection
var libc = Process.getModuleByName("libc.so");
var gameFd = -1;
var captures = [];
var lastTime = 0;

// Find game socket
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
    } catch (e) {}
}

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();

        if (gameFd < 0 && len >= 10 && len <= 500) gameFd = fd;
        if (fd !== gameFd) return;

        // Portal packet: 29 bytes, byte0 = 0x03 (not XOR-encrypted!)
        if (len === 29 && (buf.readU8() === 0x03)) {
            var now = Date.now();
            if (now - lastTime < 2000) return; // debounce 2s
            lastTime = now;

            // Record raw encrypted hex
            var raw = "";
            for (var i = 0; i < len; i++) {
                raw += ("0" + buf.add(i).readU8().toString(16)).slice(-2);
            }
            captures.push({time: now, raw: raw});

            send({t: "portal", n: captures.length, raw: raw});
        }
    }
});

rpc.exports = {
    get: function() { return JSON.stringify(captures); },
    clear: function() { captures = []; return "ok"; }
};

send({t: "ready", fd: gameFd});
