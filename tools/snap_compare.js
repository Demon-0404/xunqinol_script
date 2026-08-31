// 加载 find_pos.js 的核心逻辑 + 立即做两次快照比较
// 首次注入时自动 snapshot('initial')，然后我们等 0.5s 再 snapshot('after') + compare()

var libc = Process.getModuleByName("libc.so");
var libtcb = Process.getModuleByName("libtcb.so");
var snapshots = [];
var POOL_SIZE = 500000;
var candidates = [];

var scanBase = libtcb.base;
var scanEnd = scanBase.add(libtcb.size);

function takeSnapshot(label) {
    var snap = {};
    var count = 0;
    var addr = scanBase;
    while (addr.compare(scanEnd) < 0 && count < POOL_SIZE) {
        try {
            var val = addr.readU32();
            snap[addr.toString()] = val;
            count++;
        } catch(e) { break; }
        addr = addr.add(4);
    }
    snapshots.push({label: label, data: snap, count: count});
    send({t: "snap", label: label, count: count});
}

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
                var addr = ptr(k);
                // 读float看看
                var f1 = addr.readFloat();
                changes.push({
                    addr: k,
                    v1_u32: v1,
                    v2_u32: v2,
                    v1_float: f1.toFixed(2),
                    diff: diff
                });
            }
        }
    }
    changes.sort(function(a, b) { return b.diff - a.diff; });
    return changes;
}

// 读取float
function readFloat(addr) {
    var b = addr.readByteArray(4);
    var arr = new Uint8Array(b);
    var bits = arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
    var sign = (bits >> 31) ? -1 : 1;
    var exp = ((bits >> 23) & 0xff) - 127;
    var mantissa = (bits & 0x7fffff) | 0x800000;
    return sign * mantissa * Math.pow(2, exp - 23);
}

// Step 1: 初始快照
takeSnapshot("initial");

// Step 2: 等待0.5s后做第二次快照然后比较
setTimeout(function() {
    takeSnapshot("after");
    var s1 = snapshots[0];
    var s2 = snapshots[1];
    var changes = compareSnaps(s1, s2, 1);
    candidates = changes.slice(0, 50);

    send({t: "result", total: changes.length, shown: Math.min(30, changes.length)});
    for (var i = 0; i < Math.min(30, changes.length); i++) {
        var c = changes[i];
        // 也读取相邻float
        var p = ptr(c.addr);
        var f_next = "N/A";
        var f_prev = "N/A";
        try { f_next = p.add(4).readFloat().toFixed(2); } catch(e) {}
        try { f_prev = p.sub(4).readFloat().toFixed(2); } catch(e) {}

        send({
            t: "change",
            idx: i,
            addr: c.addr,
            v1: c.v1_u32,
            v2: c.v2_u32,
            v1f: c.v1_float,
            diff: c.diff,
            nextFloat: f_next,
            prevFloat: f_prev
        });
    }

    send({t: "done", msg: "Comparison complete. Walk again and re-run to narrow down."});
}, 500);
