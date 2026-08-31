// Portal packet comparison tool
// Captures multiple portal packets and compares them to find destination bytes

var libc = Process.getModuleByName("libc.so");
var sessionKey = 0;
var gameFd = -1;
var captures = [];
var currentLabel = null;
var captureArmed = false;

// === Step 1: Find game socket fd ===
function findGameFd() {
    var getpeernamePtr = libc.getExportByName("getpeername");
    if (!getpeernamePtr) return -1;
    var getpeername = new NativeFunction(getpeernamePtr, "int", ["int", "pointer", "pointer"]);

    for (var fd = 30; fd <= 200; fd++) {
        try {
            var addr = Memory.alloc(128);
            var addrLen = Memory.alloc(4);
            addrLen.writeInt(128);
            if (getpeername(fd, addr, addrLen) === 0) {
                var family = addr.readU16();
                if (family === 2) { // AF_INET
                    var port = ((addr.add(2).readU8() << 8) | addr.add(3).readU8());
                    var ip = addr.add(4).readU8() + "." + addr.add(5).readU8() + "." +
                             addr.add(6).readU8() + "." + addr.add(7).readU8();
                    send({t: "info", msg: "fd=" + fd + " -> " + ip + ":" + port});
                    if (port === 30002) {
                        send({t: "fd_found", fd: fd, ip: ip, port: port});
                        return fd;
                    }
                }
            }
        } catch (e) {}
    }
    return -1;
}

gameFd = findGameFd();
if (gameFd < 0) {
    // Fallback: hook send to detect on first activity
    send({t: "error", msg: "Game socket not found. Walk in game to trigger detection."});
}

function isGameFd(fd) { return fd === gameFd; }

// === Step 2: Send hook — detect key and capture portal packets ===
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();

        // Auto-detect game fd from first send
        if (gameFd < 0 && len >= 10 && len <= 500) {
            gameFd = fd;
            send({t: "fd_found", fd: fd, msg: "Detected from send()"});
        }

        if (!isGameFd(fd)) return;

        // Auto-detect key from heartbeat (17-byte packet)
        if (sessionKey === 0 && len === 17) {
            var b0 = buf.readU8();
            // Heartbeat type byte is 0x01 in plain
            var tryKey = b0 ^ 0x01;
            if (tryKey > 0 && tryKey < 256) {
                sessionKey = tryKey;
                send({t: "key_found", key: sessionKey});
            }
        }

        if (sessionKey === 0) return;

        var ptype = buf.readU8() ^ sessionKey;

        // Portal packet: 29 bytes, type 0x03
        if (len === 29 && ptype === 0x03 && captureArmed && currentLabel) {
            var plain = "";
            for (var i = 0; i < len; i++) {
                plain += ("0" + (buf.add(i).readU8() ^ sessionKey).toString(16)).slice(-2);
            }
            captures.push({label: currentLabel, plain: plain, len: len, key: sessionKey});
            captureArmed = false;
            send({
                t: "captured",
                label: currentLabel,
                plain: plain,
                count: captures.length
            });

            // Also show byte-by-byte breakdown
            var breakdown = "";
            for (var j = 0; j < len; j++) {
                var b = parseInt(plain.substring(j * 2, j * 2 + 2), 16);
                breakdown += " [" + j + "]=" + ("0" + b.toString(16)).slice(-2);
            }
            send({t: "breakdown", label: currentLabel, detail: breakdown});

            // Show each byte as decimal too for easier reading
            var decVals = [];
            for (var k = 0; k < len; k++) {
                var db = parseInt(plain.substring(k * 2, k * 2 + 2), 16);
                decVals.push(k + ":" + db);
            }
            send({t: "dec_vals", label: currentLabel, vals: decVals.join(" ")});
        }

        // Log other sends for debugging
        if (len > 10 && len !== 17) {
            var plain2 = "";
            for (var pi = 0; pi < Math.min(len, 32); pi++) {
                plain2 += ("0" + (buf.add(pi).readU8() ^ sessionKey).toString(16)).slice(-2);
            }
            send({t: "send", type: ptype, len: len, plain: plain2.substring(0, 64)});
        }
    }
});

// === Recv hook — detect key from recv side ===
Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.doProcess = isGameFd(this.fd);
    },
    onLeave: function(ret) {
        if (!this.doProcess) return;
        var realLen = ret.toInt32();
        if (realLen <= 4) return;

        if (sessionKey === 0) {
            var b0 = this.buf.readU8();
            var b1 = this.buf.add(1).readU8();
            var b2 = this.buf.add(2).readU8();
            var b3 = this.buf.add(3).readU8();
            if (b1 === b2 && b2 === b3) {
                var tryKey = b0 ^ 0x02;
                if (tryKey > 0 && tryKey < 256) {
                    sessionKey = tryKey;
                    send({t: "key_found", key: sessionKey, side: "recv"});
                }
            }
        }
    }
});

// === RPC commands ===
rpc.exports = {
    getKey: function() { return sessionKey; },
    getStatus: function() {
        return JSON.stringify({
            fd: gameFd,
            key: sessionKey,
            captures: captures.length,
            armed: captureArmed,
            label: currentLabel
        });
    },
    armCapture: function(label) {
        captureArmed = true;
        currentLabel = label + "";
        return "Armed: " + currentLabel;
    },
    getCaptures: function() {
        return JSON.stringify(captures.map(function(c) {
            return {label: c.label, plain: c.plain, key: c.key};
        }));
    },
    compare: function(idx1, idx2) {
        if (idx1 >= captures.length || idx2 >= captures.length) return "Invalid indices";
        var c1 = captures[idx1];
        var c2 = captures[idx2];
        var result = "Comparing [" + c1.label + "] vs [" + c2.label + "]:\n";
        for (var i = 0; i < 29; i++) {
            var b1 = parseInt(c1.plain.substring(i * 2, i * 2 + 2), 16);
            var b2 = parseInt(c2.plain.substring(i * 2, i * 2 + 2), 16);
            if (b1 !== b2) {
                result += "  Byte[" + i + "]: " + ("0" + b1.toString(16)).slice(-2) +
                          " -> " + ("0" + b2.toString(16)).slice(-2) +
                          " (DEC: " + b1 + "->" + b2 + ")\n";
            }
        }
        return result;
    },
    compareAll: function() {
        if (captures.length < 2) return JSON.stringify({error: "Need at least 2 captures"});
        // Find bytes that differ across ALL captures
        var diffBytes = {};
        for (var i = 0; i < captures.length - 1; i++) {
            var p1 = captures[i].plain;
            var p2 = captures[i + 1].plain;
            for (var j = 0; j < 58; j += 2) {
                var b1 = p1.substring(j, j + 2);
                var b2 = p2.substring(j, j + 2);
                if (b1 !== b2) {
                    var idx = j / 2;
                    if (!diffBytes[idx]) diffBytes[idx] = [];
                    diffBytes[idx].push({from: b1, to: b2, label: captures[i].label + "->" + captures[i + 1].label});
                }
            }
        }
        return JSON.stringify(diffBytes);
    },
    // Build a test packet from template + modifications
    buildPacket: function(templateIdx, modifications) {
        // modifications: "5:aabb,12:ccdd"
        if (templateIdx >= captures.length) return "Bad template";
        var plain = captures[templateIdx].plain;
        var chars = plain.split("");
        var mods = modifications.split(",");
        for (var m = 0; m < mods.length; m++) {
            var parts = mods[m].trim().split(":");
            if (parts.length !== 2) continue;
            var pos = parseInt(parts[0]);
            var val = parts[1];
            for (var v = 0; v < val.length && (pos * 2 + v) < chars.length; v++) {
                chars[pos * 2 + v] = val[v];
            }
        }
        return chars.join("");
    },
    // Send raw data to game socket
    sendRaw: function(plainHex, xorkey) {
        if (gameFd < 0) return "No game fd";
        if (!xorkey) xorkey = sessionKey;
        if (!xorkey) return "No key";

        var len = plainHex.length / 2;
        var buf = Memory.alloc(len);
        for (var i = 0; i < len; i++) {
            var b = parseInt(plainHex.substring(i * 2, i * 2 + 2), 16);
            buf.add(i).writeU8(b ^ xorkey);
        }

        var sendPtr = libc.getExportByName("send");
        var sendFn = new NativeFunction(sendPtr, "int", ["int", "pointer", "int", "int"]);
        var ret = sendFn(gameFd, buf, len, 0);
        return "Sent " + len + "B to fd=" + gameFd + " ret=" + ret;
    },
    clearCaptures: function() {
        captures = [];
        return "Cleared";
    },
    setLabel: function(label) {
        currentLabel = label + "";
        return "Label: " + currentLabel;
    }
};

send({t: "ready", fd: gameFd, key: sessionKey, msg: "Portal compare ready. fd=" + gameFd + " key=" + sessionKey});
