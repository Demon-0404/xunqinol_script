// ============================================================
// 天音 — 传送包嗅探脚本 (无需handler地址，仅hook send/recv)
// 目的: 抓取传送包明文 + 尝试修改bytes 24-27重定向目的地
// ============================================================

var libc = Process.getModuleByName("libc.so");
var gameFd = -1;
var sessionKey = 0;
var sendCounter = 0;
var portalHistory = [];   // 所有抓到的传送包
var lastPortalTime = 0;

// === Step 1: 找游戏socket fd ===
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
                if (family === 2) {
                    var port = ((addr.add(2).readU8() << 8) | addr.add(3).readU8());
                    if (port === 30002) {
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
    send({t: 'warn', msg: '未找到fd=30002，将在第一个send时自动检测'});
} else {
    send({t: 'info', msg: '游戏fd=' + gameFd});
}

function isGameFd(fd) {
    if (fd === gameFd) return true;
    // 自动检测
    if (gameFd < 0) {
        gameFd = fd;
        send({t: 'info', msg: '自动检测fd=' + fd});
        return true;
    }
    return false;
}

// === Step 2: Hook send — 抓传送包 (byte0不参与XOR!) ===
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (!isGameFd(fd)) return;
        if (len < 10) return;

        sendCounter++;

        // 传送包检测: 29B, byte0 === 0x03 (不参与XOR!)
        if (len === 29 && buf.readU8() === 0x03) {
            var now = Date.now();
            if (now - lastPortalTime < 2000) return; // 2秒消抖
            lastPortalTime = now;

            // 读加密原始字节
            var raw = '';
            for (var i = 0; i < len; i++) {
                raw += ('0' + buf.add(i).readU8().toString(16)).slice(-2);
            }

            portalHistory.push({
                time: now,
                raw: raw,
                index: portalHistory.length + 1
            });

            send({t: 'portal',
                index: portalHistory.length,
                raw: raw,
                msg: '=== 传送包 #' + portalHistory.length + ' ==='
            });

            // 如果有key，尝试解密bytes 1-28
            if (sessionKey > 0) {
                var plain = raw.substring(0, 2); // byte0保持原样
                for (var i = 1; i < len; i++) {
                    var b = buf.add(i).readU8();
                    // send包: byte0不加密, bytes 1-N用send计数器XOR
                    // 计数器值未知，先显示原值
                    plain += ('0' + b.toString(16)).slice(-2);
                }
                send({t: 'portal_raw', raw: raw, msg: '原始加密数据'});
            }

            // 字节分解
            var breakdown = 'Byte分解:\n';
            for (var j = 0; j < len; j++) {
                var b = buf.add(j).readU8();
                breakdown += '  [' + j + ']=0x' + ('0' + b.toString(16)).slice(-2) + ' (' + b + ')\n';
            }
            send({t: 'portal_detail', detail: breakdown});
        }

        // 心跳包: 17B
        if (len === 17 && buf.readU8() === 0x01) {
            send({t: 'heartbeat', count: sendCounter});
        }

        // 移动包: 30B (可能)
        if (len === 30 && buf.readU8() !== 0x03 && buf.readU8() !== 0x01) {
            var mraw = '';
            for (var mi = 0; mi < Math.min(len, 30); mi++) {
                mraw += ('0' + buf.add(mi).readU8().toString(16)).slice(-2);
            }
            send({t: 'move', len: len, raw: mraw, byte0: '0x' + buf.readU8().toString(16)});
        }
    }
});

// === Step 3: Hook recv — 检测session key + 抓地图数据 ===
var recvType3Count = 0;
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

        // 检测session key
        if (sessionKey === 0) {
            var b0 = this.buf.readU8();
            var b1 = this.buf.add(1).readU8();
            var b2 = this.buf.add(2).readU8();
            var b3 = this.buf.add(3).readU8();
            if (b1 === b2 && b2 === b3) {
                var tryKey = b0 ^ 0x02;
                if (tryKey > 0 && tryKey < 256) {
                    sessionKey = tryKey;
                    send({t: 'key_found', key: tryKey, hex: '0x' + tryKey.toString(16)});
                }
            }
        }

        // 解密recv包type
        if (sessionKey > 0) {
            var ptype = this.buf.readU8() ^ sessionKey;

            // Type 3 (大包) = 地图数据
            if (ptype === 0x03 && realLen > 100) {
                recvType3Count++;
                var raw = '';
                var dumpLen = Math.min(realLen, 80);
                for (var ri = 0; ri < dumpLen; ri++) {
                    raw += ('0' + this.buf.add(ri).readU8().toString(16)).slice(-2);
                }
                send({t: 'map_data',
                    count: recvType3Count,
                    len: realLen,
                    head: raw,
                    msg: '地图数据 #' + recvType3Count + ' (' + realLen + 'B)'
                });
            }

            // Type 4 (中等包)
            if (ptype === 0x04 && realLen > 40) {
                var raw4 = '';
                var dump4 = Math.min(realLen, 40);
                for (var ri4 = 0; ri4 < dump4; ri4++) {
                    raw4 += ('0' + this.buf.add(ri4).readU8().toString(16)).slice(-2);
                }
                send({t: 'recv_type4', len: realLen, head: raw4});
            }

            // Type 5 (移动/位置相关)
            if (ptype === 0x05 && realLen > 15) {
                var raw5 = '';
                for (var ri5 = 0; ri5 < realLen; ri5++) {
                    raw5 += ('0' + this.buf.add(ri5).readU8().toString(16)).slice(-2);
                }
                send({t: 'recv_type5', len: realLen, raw: raw5, msg: 'Type5 recv (' + realLen + 'B)'});
            }
        }
    }
});

// === RPC ===
rpc.exports = {
    getKey: function() { return sessionKey; },
    getPortals: function() {
        return JSON.stringify(portalHistory.map(function(p) {
            return {index: p.index, time: p.time, raw: p.raw};
        }));
    },
    getLastPortal: function() {
        if (portalHistory.length === 0) return '{}';
        var p = portalHistory[portalHistory.length - 1];
        return JSON.stringify({index: p.index, raw: p.raw});
    },
    clearPortals: function() {
        portalHistory = [];
        return 'OK';
    },
    getGameFd: function() { return gameFd; },
    getStatus: function() {
        return JSON.stringify({
            fd: gameFd,
            key: sessionKey,
            sendCount: sendCounter,
            portalCount: portalHistory.length,
            mapDataCount: recvType3Count
        });
    }
};

send({t: 'ready',
    msg: '传送包嗅探就绪!',
    msg2: '【操作】走一次传送门，观察PORTAL输出',
    msg3: '走完后用 getPortals() 查看所有抓到的包',
    fd: gameFd,
    key: sessionKey
});
