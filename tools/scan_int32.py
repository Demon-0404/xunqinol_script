# -*- coding: utf-8 -*-
"""Scan for int32 coordinate pairs (many games use fixed-point ints)"""
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

rpc.exports = {
    // Scan for int32 pairs that look like game coordinates (100-100000)
    scanIntPairs: function() {
        var found = [];
        for (var ri = 0; ri < Math.min(heapRanges.length, 100); ri++) {
            var r = heapRanges[ri];
            try {
                var end = r.base.add(r.size - 16);
                var seen = 0;
                for (var addr = r.base; addr.compare(end) < 0; addr = addr.add(4)) {
                    seen++;
                    if (seen > 200000) break;
                    try {
                        var v1 = addr.readU32();
                        var v2 = addr.add(4).readU32();
                        // Game coordinates as int (100-100000 range)
                        if (v1 > 100 && v1 < 100000 && v2 > 100 && v2 < 100000) {
                            // Check v3 too for stronger signal
                            var v3 = addr.add(8).readU32();
                            if (v3 > 10 && v3 < 100000) {
                                found.push({
                                    addr: addr.toString(),
                                    x: v1,
                                    y: v2,
                                    z: v3,
                                    xf: (v1/10).toFixed(1),
                                    yf: (v2/10).toFixed(1),
                                    zf: (v3/10).toFixed(1)
                                });
                                if (found.length >= 60) break;
                            }
                        }
                    } catch(e) { break; }
                }
            } catch(e) {}
            if (found.length >= 60) break;
        }
        return JSON.stringify(found);
    },

    readU32: function(addrStr) {
        var p = ptr(addrStr);
        return JSON.stringify({
            u32_0: p.readU32(),
            u32_4: p.add(4).readU32(),
            u32_8: p.add(8).readU32(),
            u32_12: p.add(12).readU32()
        });
    },

    writeU32: function(addrStr, val) {
        var p = ptr(addrStr);
        var start = p.and(ptr(0xfffff000));
        Memory.protect(start, 4096, 'rwx');
        p.writeU32(parseInt(val));
        return "OK";
    },

    writeU32Pair: function(addrStr, x, y) {
        var p = ptr(addrStr);
        var start = p.and(ptr(0xfffff000));
        Memory.protect(start, 4096, 'rwx');
        p.writeU32(parseInt(x));
        p.add(4).writeU32(parseInt(y));
        return "OK";
    },

    diffIntPairs: function(beforeJson, afterJson) {
        var before = JSON.parse(beforeJson);
        var after = JSON.parse(afterJson);
        var afterMap = {};
        after.forEach(function(a) { afterMap[a.addr] = a; });
        var changes = [];
        before.forEach(function(b) {
            var a = afterMap[b.addr];
            if (a) {
                var dx = Math.abs(parseInt(a.x) - parseInt(b.x));
                var dy = Math.abs(parseInt(a.y) - parseInt(b.y));
                var dz = Math.abs(parseInt(a.z) - parseInt(b.z));
                if (dx > 0 || dy > 0 || dz > 0) {
                    changes.push({
                        addr: b.addr,
                        bx: b.x, by: b.y, bz: b.z,
                        ax: a.x, ay: a.y, az: a.z,
                        dx: dx, dy: dy, dz: dz
                    });
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

# PHASE 1: Scan BEFORE
print("[1] Scanning int32 pairs BEFORE movement...")
before = script.exports.scan_int_pairs()
before_list = json.loads(before)
print(f"    Found {len(before_list)} candidates")
for i, p in enumerate(before_list[:15]):
    print(f"    [{i:2d}] {p['addr']}: int=({p['x']}, {p['y']}, {p['z']}) ~float=({p['xf']}, {p['yf']}, {p['zf']})")

# PHASE 2: Wait for user
print("\n[2] >>>>> 请在游戏里走一步！<<<<<")
print("    等待 10 秒...")
for i in range(10, 0, -1):
    print(f"    {i}...")
    time.sleep(1)

# PHASE 3: Scan AFTER
print("\n[3] Scanning int32 pairs AFTER movement...")
after = script.exports.scan_int_pairs()
after_list = json.loads(after)
print(f"    Found {len(after_list)} candidates")

# PHASE 4: Compare
print("\n[4] Comparing...")
changes = script.exports.diff_int_pairs(before, after)
change_list = json.loads(changes)

outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "int32_scan_result.json")
with open(outpath, "w") as f:
    json.dump({"before": before_list, "after": after_list, "changes": change_list}, f, indent=2)

print(f"\n{'='*55}")
print(f"Changed addresses: {len(change_list)}")
print(f"{'='*55}")

if len(change_list) > 0:
    for i, c in enumerate(change_list[:15]):
        print(f"[{i:2d}] {c['addr']}: ({c['bx']},{c['by']},{c['bz']}) -> ({c['ax']},{c['ay']},{c['az']})")
        print(f"     delta: dx={c['dx']} dy={c['dy']} dz={c['dz']}")
else:
    print("\n*** STILL NO CHANGES ***")
    print("Let's try: direct write test on int32 candidates")

    # Try writing to each candidate
    print("\n[5] Testing int32 write (x+100) on candidates...")
    for i, p in enumerate(before_list[:15]):
        try:
            orig = json.loads(script.exports.read_u32(p['addr']))
            ox = orig['u32_0']
            oy = orig['u32_4']
            script.exports.write_u32_pair(p['addr'], ox + 100, oy)
            time.sleep(0.2)
            script.exports.write_u32_pair(p['addr'], ox, oy)
            print(f"    [{i:2d}] {p['addr']}: int ({ox},{oy}) -> ({ox+100},{oy}) [reverted]")
        except Exception as e:
            print(f"    [{i:2d}] {p['addr']}: ERROR {e}")

    print("\nDid you see any character movement?")

print(f"\nResults: {outpath}")
session.detach()
