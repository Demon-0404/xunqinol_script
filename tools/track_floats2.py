# -*- coding: utf-8 -*-
"""Two-phase: scan before, signal user to walk, scan after, compare"""
import frida
import json
import time
import os

JS = """
var heapRanges = [];
Process.enumerateRanges('rw-').forEach(function(r) {
    if (r.size >= 0x10000 && r.size <= 0x2000000) {
        heapRanges.push(r);
    }
});

function readFloat(addr) {
    var b = addr.readByteArray(4);
    var arr = new Uint8Array(b);
    var bits = arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
    var sign = (bits >> 31) ? -1 : 1;
    var exp = ((bits >> 23) & 0xff) - 127;
    var mantissa = (bits & 0x7fffff) | 0x800000;
    return sign * mantissa * Math.pow(2, exp - 23);
}

rpc.exports = {
    scanFloats: function() {
        var found = [];
        for (var ri = 0; ri < Math.min(heapRanges.length, 50); ri++) {
            var r = heapRanges[ri];
            try {
                var end = r.base.add(r.size - 16);
                var seen = 0;
                for (var addr = r.base; addr.compare(end) < 0; addr = addr.add(4)) {
                    seen++;
                    if (seen > 300000) break;
                    try {
                        var v1 = readFloat(addr);
                        if (v1 > 10 && v1 < 100000 && Math.abs(v1 - Math.round(v1)) < 0.5) {
                            var v2 = readFloat(addr.add(4));
                            if (v2 > 10 && v2 < 100000 && Math.abs(v2 - Math.round(v2)) < 0.5) {
                                found.push({
                                    addr: addr.toString(),
                                    x: parseFloat(v1.toFixed(1)),
                                    y: parseFloat(v2.toFixed(1))
                                });
                                if (found.length >= 50) break;
                            }
                        }
                    } catch(e) { break; }
                }
            } catch(e) {}
            if (found.length >= 50) break;
        }
        return JSON.stringify(found);
    },

    readAddr: function(addrStr) {
        var p = ptr(addrStr);
        var x = readFloat(p);
        var y = readFloat(p.add(4));
        return JSON.stringify({x: parseFloat(x.toFixed(2)), y: parseFloat(y.toFixed(2))});
    },

    writeXY: function(addrStr, x, y) {
        var p = ptr(addrStr);
        var start = p.and(ptr(0xfffff000));
        Memory.protect(start, 4096, 'rwx');
        p.writeFloat(parseFloat(x));
        p.add(4).writeFloat(parseFloat(y));
        return "OK";
    },

    diff: function(beforeJson, afterJson) {
        var before = JSON.parse(beforeJson);
        var after = JSON.parse(afterJson);
        var afterMap = {};
        after.forEach(function(a) { afterMap[a.addr] = a; });
        var changes = [];
        before.forEach(function(b) {
            var a = afterMap[b.addr];
            if (a) {
                var dx = Math.abs(a.x - b.x);
                var dy = Math.abs(a.y - b.y);
                if (dx > 0.3 || dy > 0.3) {
                    changes.push({addr: b.addr, bx: b.x, by: b.y, ax: a.x, ay: a.y, dx: dx, dy: dy});
                }
            }
        });
        changes.sort(function(a, b) { return (b.dx+b.dy) - (a.dx+a.dy); });
        return JSON.stringify(changes);
    }
};
"""

def on_msg(msg, data):
    pass

print("Connecting...")
device = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = device.attach(5630)
script = session.create_script(JS)
script.on('message', on_msg)
script.load()
time.sleep(1)

# PHASE 1: BEFORE scan
print(">>> PHASE 1: Scanning memory BEFORE movement...")
before = script.exports.scan_floats()
before_list = json.loads(before)
print(f"    Found {len(before_list)} float pairs")

# PHASE 2: Signal user
print("\n>>> PHASE 2: 请现在在游戏里走一步！")
print("    (按 wasd 或点击移动一步即可)")
print("    等待 12 秒...")
for i in range(12, 0, -1):
    print(f"    {i}...")
    time.sleep(1)

# PHASE 3: AFTER scan
print("\n>>> PHASE 3: Scanning memory AFTER movement...")
after = script.exports.scan_floats()
after_list = json.loads(after)
print(f"    Found {len(after_list)} float pairs")

# PHASE 4: Compare
print("\n>>> PHASE 4: Comparing...")
changes = script.exports.diff(before, after)
change_list = json.loads(changes)

outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pos_scan_result.json")
with open(outpath, "w") as f:
    json.dump({"before": before_list, "after": after_list, "changes": change_list}, f, indent=2)

if len(change_list) == 0:
    print("\n*** STILL 0 CHANGES ***")
    print("The coordinates might be stored differently:")
    print("- Maybe as integers (not floats)")
    print("- Maybe in a memory region we're not scanning")
    print("- Maybe encrypted/scrambled in memory")
    print("\nLet's try an alternative: directly test writing")
    print("to candidate addresses to see which one works.")
else:
    print(f"\n*** FOUND {len(change_list)} CHANGES! ***")
    for i, c in enumerate(change_list[:10]):
        print(f"[{i}] {c['addr']}: ({c['bx']}, {c['by']}) -> ({c['ax']}, {c['ay']}) | d=({c['dx']:.1f}, {c['dy']:.1f})")

print(f"\nResults: {outpath}")
session.detach()
