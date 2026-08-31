// ============================================================
// 找玩家坐标 — 步进对比法
// 读内存 → 走一步 → 再读 → 找变化值
// ============================================================

var libc = Process.getModuleByName("libc.so");
var libtcb = Process.getModuleByName("libtcb.so");
var snapshots = [];
var POOL_SIZE = 500000;
var candidates = [];

// 从libtcb的data段分配扫描范围
var scanBase = libtcb.base;
var scanEnd = scanBase.add(libtcb.size);

// 也扫描堆区域
var heapRanges = [];
Process.enumerateRanges('rw-').forEach(function(r) {
    if (r.size >= 0x10000 && r.size <= 0x2000000) { // 64KB ~ 32MB
        heapRanges.push(r);
    }
});

send({t: "info", msg: "libtcb: " + scanBase + " - " + scanEnd + " (" + libtcb.size + "B)"});
send({t: "info", msg: "heap regions: " + heapRanges.length});

// 读4字节快照
function takeSnapshot(label) {
    var snap = {};
    var count = 0;

    // 读libtcb的data段
    var addr = scanBase;
    while (addr.compare(scanEnd) < 0 && count < POOL_SIZE) {
        try {
            var val = addr.readU32();
            var key = addr.toString();
            snap[key] = val;
            count++;
        } catch(e) { break; }
        addr = addr.add(4);
    }

    snapshots.push({label: label, data: snap, count: count});
    send({t: "snap", label: label, count: count});
}

// 比较两个快照，找变化>阈值的地址
function compareSnaps(s1, s2, minChange) {
    var changes = [];
    var keys = Object.keys(s1.data);
    for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        var v1 = s1.data[k];
        var v2 = s2.data[k];
        if (v1 !== undefined && v2 !== undefined && v1 !== v2) {
            var diff = Math.abs(v2 - v1);
            if (diff >= minChange && diff < 500000) {
                changes.push({addr: k, v1: v1, v2: v2, diff: diff});
            }
        }
    }
    // 按变化量排序
    changes.sort(function(a, b) { return b.diff - a.diff; });
    return changes;
}

// 也监控特定float地址
var watchAddrs = [];
function readFloat(addr) {
    var b = addr.readByteArray(4);
    var arr = new Uint8Array(b);
    var bits = arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
    var sign = (bits >> 31) ? -1 : 1;
    var exp = ((bits >> 23) & 0xff) - 127;
    var mantissa = (bits & 0x7fffff) | 0x800000;
    return sign * mantissa * Math.pow(2, exp - 23);
}

// 快速扫描heap中看起来像坐标的float pairs
function scanHeapForFloats() {
    var found = [];
    for (var ri = 0; ri < Math.min(heapRanges.length, 30); ri++) {
        var r = heapRanges[ri];
        try {
            var end = r.base.add(r.size - 16);
            var seen = 0;
            for (var addr = r.base; addr.compare(end) < 0; addr = addr.add(4)) {
                seen++;
                if (seen > 200000) break;
                try {
                    var v1 = readFloat(addr);
                    // 合理的游戏坐标范围
                    if (v1 > 10 && v1 < 100000 && Math.abs(v1 - Math.round(v1)) < 0.5) {
                        var v2 = readFloat(addr.add(4));
                        if (v2 > 10 && v2 < 100000 && Math.abs(v2 - Math.round(v2)) < 0.5) {
                            var v3 = readFloat(addr.add(8));
                            if (v3 > 10 && v3 < 100000 && Math.abs(v3 - Math.round(v3)) < 0.5) {
                                found.push({
                                    addr: addr.toString(),
                                    x: v1.toFixed(1),
                                    y: v2.toFixed(1),
                                    z: v3.toFixed(1),
                                    region: r.base.toString()
                                });
                                if (found.length >= 15) break;
                            }
                        }
                    }
                } catch(e) { break; }
            }
        } catch(e) {}
        if (found.length >= 15) break;
    }
    return found;
}

// === RPC API ===
rpc.exports = {
    snapshot: function(label) {
        takeSnapshot(label || "snap");
        return "Snapshot taken: " + snapshots[snapshots.length-1].count + " values";
    },
    compare: function() {
        if (snapshots.length < 2) return "Need 2 snapshots";
        var s1 = snapshots[snapshots.length - 2];
        var s2 = snapshots[snapshots.length - 1];
        var changes = compareSnaps(s1, s2, 1);
        candidates = changes.slice(0, 50);
        return JSON.stringify(changes.slice(0, 30));
    },
    getCandidates: function() {
        return JSON.stringify(candidates.slice(0, 20));
    },
    scanFloats: function() {
        var found = scanHeapForFloats();
        return JSON.stringify(found);
    },
    // 读指定地址
    readAddr: function(addrStr) {
        try {
            var p = ptr(addrStr);
            var u32 = p.readU32();
            var f = readFloat(p);
            return JSON.stringify({addr: addrStr, u32: u32, float: f.toFixed(2)});
        } catch(e) {
            return "Error: " + e;
        }
    },
    // 读周围内存 (16字节范围)
    readAround: function(addrStr) {
        try {
            var p = ptr(addrStr);
            var bytes = "";
            for (var i = 0; i < 32; i++) {
                bytes += ("0" + p.add(i).readU8().toString(16)).slice(-2);
            }
            return bytes;
        } catch(e) {
            return "Error: " + e;
        }
    },
    // 写float到指定地址
    writeFloat: function(addrStr, val) {
        try {
            var p = ptr(addrStr);
            Memory.protect(p.and(ptr(0xfffff000)), 4096, 'rwx');
            p.writeFloat(parseFloat(val));
            return "Written " + val + " to " + addrStr;
        } catch(e) {
            return "Error: " + e;
        }
    },
    // 写两个float (x,y)
    writePosition: function(addrStr, x, y) {
        try {
            var p = ptr(addrStr);
            Memory.protect(p.and(ptr(0xfffff000)), 4096, 'rwx');
            p.writeFloat(parseFloat(x));
            p.add(4).writeFloat(parseFloat(y));
            return "Written (" + x + ", " + y + ") to " + addrStr;
        } catch(e) {
            return "Error: " + e;
        }
    },
    // 持续监控某个地址
    watchAddr: function(addrStr) {
        try {
            var p = ptr(addrStr);
            var f = readFloat(p);
            var u32 = p.readU32();
            return JSON.stringify({addr: addrStr, float: f.toFixed(2), u32: u32, hex: "0x" + u32.toString(16)});
        } catch(e) {
            return "Error: " + e;
        }
    }
};

// 初始扫描
var initFloats = scanHeapForFloats();
send({t: "init_floats", data: JSON.stringify(initFloats)});
takeSnapshot("initial");
send({t: "ready", msg: "就绪!", msg2: "步骤: 走一步 → snapshot('after') → compare()", initCandidates: initFloats.length});
