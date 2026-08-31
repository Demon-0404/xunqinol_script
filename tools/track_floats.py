# -*- coding: utf-8 -*-
"""监控堆中float坐标候选，走路前后对比"""
import frida
import json
import time
import os

SCRIPT = """
var libc = Process.getModuleByName("libc.so");
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
        for (var ri = 0; ri < Math.min(heapRanges.length, 40); ri++) {
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
                                var v3 = readFloat(addr.add(8));
                                if (v3 > 10 && v3 < 100000 && Math.abs(v3 - Math.round(v3)) < 0.5) {
                                    found.push({
                                        addr: addr.toString(),
                                        x: parseFloat(v1.toFixed(1)),
                                        y: parseFloat(v2.toFixed(1)),
                                        z: parseFloat(v3.toFixed(1))
                                    });
                                    if (found.length >= 30) break;
                                }
                            }
                        }
                    } catch(e) { break; }
                }
            } catch(e) {}
            if (found.length >= 30) break;
        }
        return JSON.stringify(found);
    },

    readAddr: function(addrStr) {
        var p = ptr(addrStr);
        var x = readFloat(p);
        var y = readFloat(p.add(4));
        var z = readFloat(p.add(8));
        return JSON.stringify({x: parseFloat(x.toFixed(2)), y: parseFloat(y.toFixed(2)), z: parseFloat(z.toFixed(2))});
    },

    writePosition: function(addrStr, x, y) {
        var p = ptr(addrStr);
        var start = p.and(ptr(0xfffff000));
        Memory.protect(start, 4096, 'rwx');
        p.writeFloat(parseFloat(x));
        p.add(4).writeFloat(parseFloat(y));
        return "Written (" + x + ", " + y + ") to " + addrStr;
    },

    diffScans: function(beforeJson, afterJson) {
        var before = JSON.parse(beforeJson);
        var after = JSON.parse(afterJson);
        var changes = [];
        var afterMap = {};
        after.forEach(function(a) { afterMap[a.addr] = a; });

        before.forEach(function(b) {
            var a = afterMap[b.addr];
            if (a) {
                var dx = Math.abs(a.x - b.x);
                var dy = Math.abs(a.y - b.y);
                var dz = Math.abs(a.z - b.z);
                if (dx > 0.5 || dy > 0.5 || dz > 0.5) {
                    changes.push({addr: b.addr, bx: b.x, by: b.y, bz: b.z, ax: a.x, ay: a.y, az: a.z, dx: dx, dy: dy, dz: dz});
                }
            } else {
                changes.push({addr: b.addr, bx: b.x, by: b.y, bz: b.z, disappeared: true});
            }
        });
        changes.sort(function(a, b) { return (b.dx+b.dy) - (a.dx+a.dy); });
        return JSON.stringify(changes);
    }
};
"""

def on_msg(msg, data):
    pass  # Suppress frida messages

print("Connecting...")
device = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = device.attach(5630)

script = session.create_script(SCRIPT)
script.on('message', on_msg)
script.load()
time.sleep(1)

# Step 1: Initial scan
print("[1] Scanning for float coordinates...")
before = script.exports.scan_floats()
before_list = json.loads(before)
print(f"    Found {len(before_list)} candidates")
for i, f in enumerate(before_list[:12]):
    print(f"    [{i:2d}] {f['addr']}: ({f['x']}, {f['y']}, {f['z']})")

# Step 2: Wait for user to walk
print("\n[2] ======================================")
print("    NOW walk ONE STEP in the game!")
print("    Waiting 8 seconds...")
print("    ======================================")
for i in range(8, 0, -1):
    print(f"    {i}...")
    time.sleep(1)

# Step 3: After scan
print("\n[3] Scanning again...")
after = script.exports.scan_floats()
after_list = json.loads(after)
print(f"    Found {len(after_list)} candidates")

# Step 4: Compare
print("\n[4] Comparing...")
changes = script.exports.diff_scans(before, after)
change_list = json.loads(changes)
print(f"    {len(change_list)} addresses changed!")
print()

# Save to file
output = {
    "before": before_list,
    "after": after_list,
    "changes": change_list
}
# Use current dir
outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pos_scan_result.json")
with open(outpath, "w") as f:
    json.dump(output, f, indent=2)

if len(change_list) == 0:
    print("    NO CHANGES detected!")
    print("    Possible reasons:")
    print("    - Player didn't move during the wait window")
    print("    - Coordinates use different encoding (int, double, etc.)")
    print("    - Scan range too small (only scanning first 40 heap regions)")
else:
    print("    TOP CHANGED ADDRESSES (likely player position):")
    print("    " + "-"*55)
    for i, c in enumerate(change_list[:10]):
        print(f"    [{i}] {c['addr']}")
        print(f"        BEFORE: ({c['bx']}, {c['by']}, {c['bz']})")
        print(f"        AFTER:  ({c['ax']}, {c['ay']}, {c['az']})")
        print(f"        delta: dx={c['dx']:.1f} dy={c['dy']:.1f} dz={c['dz']:.1f}")
        print()
    print(f"\n    Results saved to: {outpath}")
    print(f"\n    To test teleport, run:")
    print(f"    python tools/write_pos.py <addr> <x> <y>")

session.detach()
print("\nDone.")
