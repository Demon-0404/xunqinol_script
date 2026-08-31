# -*- coding: utf-8 -*-
"""Broad scan: snapshot ALL heap regions, walk, compare ALL changes"""
import frida
import json
import time
import os

JS = """
var heapRanges = [];
var snapshots = [];

Process.enumerateRanges('rw-').forEach(function(r) {
    if (r.size >= 0x10000 && r.size <= 0x800000) {
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
    takeSnapshot: function(label) {
        var snap = {};
        var count = 0;
        var maxPerRegion = 50000;
        for (var ri = 0; ri < heapRanges.length; ri++) {
            var r = heapRanges[ri];
            try {
                var end = r.base.add(r.size - 4);
                var seen = 0;
                for (var addr = r.base; addr.compare(end) < 0 && seen < maxPerRegion; addr = addr.add(4)) {
                    try {
                        var val = addr.readU32();
                        snap[addr.toString()] = val;
                        count++;
                        seen++;
                    } catch(e) { break; }
                }
            } catch(e) {}
        }
        snapshots.push({label: label, data: snap, count: count});
        return count;
    },

    compareAndReport: function() {
        if (snapshots.length < 2) return "Need 2 snapshots";
        var s1 = snapshots[snapshots.length-2];
        var s2 = snapshots[snapshots.length-1];
        var changes = [];
        var keys = Object.keys(s1.data);

        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            var v1 = s1.data[k];
            var v2 = s2.data[k];
            if (v1 !== undefined && v2 !== undefined && v1 !== v2) {
                var diff = Math.abs(parseInt(v2) - parseInt(v1));
                if (diff > 0 && diff < 100000) {
                    var p = ptr(k);
                    var f = 0;
                    try { f = readFloat(p); } catch(e) {}
                    changes.push({
                        addr: k,
                        v1: v1,
                        v2: v2,
                        diff: diff,
                        fval: parseFloat(f.toFixed(2))
                    });
                }
            }
        }

        // Sort by diff magnitude
        changes.sort(function(a, b) { return b.diff - a.diff; });

        // Filter: keep only those where float value looks like game coord (30-50000)
        var gameLike = [];
        var other = [];
        for (var j = 0; j < changes.length; j++) {
            var c = changes[j];
            if (c.fval > 30 && c.fval < 50000) {
                gameLike.push(c);
            } else {
                other.push(c);
            }
        }

        return JSON.stringify({
            total: changes.length,
            gameLike: gameLike.slice(0, 30),
            otherTop: other.slice(0, 10)
        });
    },

    readXY: function(addrStr) {
        var p = ptr(addrStr);
        return JSON.stringify({
            x: parseFloat(readFloat(p).toFixed(2)),
            y: parseFloat(readFloat(p.add(4)).toFixed(2)),
            z: parseFloat(readFloat(p.add(8)).toFixed(2))
        });
    },

    writeXY: function(addrStr, x, y) {
        var p = ptr(addrStr);
        var start = p.and(ptr(0xfffff000));
        Memory.protect(start, 4096, 'rwx');
        p.writeFloat(parseFloat(x));
        p.add(4).writeFloat(parseFloat(y));
        return "OK";
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

# PHASE 1: Snapshot BEFORE
print("[1] Taking BEFORE snapshot (all heap regions)...")
count1 = script.exports.take_snapshot("before")
print(f"    Snapshot: {count1} values")

# PHASE 2: Signal user
print("\n[2] >>>>> 请在游戏里走一步！<<<<<")
print("    等待 10 秒...")
for i in range(10, 0, -1):
    print(f"    {i}...")
    time.sleep(1)

# PHASE 3: Snapshot AFTER
print("\n[3] Taking AFTER snapshot...")
count2 = script.exports.take_snapshot("after")
print(f"    Snapshot: {count2} values")

# PHASE 4: Compare
print("\n[4] Comparing... (this may take a while)")
result = script.exports.compare_and_report()
data = json.loads(result)

print(f"\n{'='*55}")
print(f"Total changed values: {data['total']}")
print(f"Game-like float changes: {len(data['gameLike'])}")
print(f"{'='*55}")

if len(data['gameLike']) > 0:
    print("\n>>> Game-like coordinate changes (float 30-50000):")
    for i, c in enumerate(data['gameLike'][:20]):
        print(f"  [{i:2d}] {c['addr']}: u32 {c['v1']}->{c['v2']} | float={c['fval']} | diff={c['diff']}")

if len(data['otherTop']) > 0:
    print("\n>>> Other top changes:")
    for i, c in enumerate(data['otherTop'][:10]):
        print(f"  [{i}] {c['addr']}: u32 {c['v1']}->{c['v2']} | float={c['fval']} | diff={c['diff']}")

# Save
outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "broad_scan_result.json")
with open(outpath, "w") as f:
    json.dump(data, f, indent=2)
print(f"\nResults: {outpath}")

session.detach()
