# -*- coding: utf-8 -*-
"""Direct write test: modify candidate coordinates and see if player moves"""
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
    scanPairs: function() {
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
                        var v2 = readFloat(addr.add(4));
                        if (v1 > 30 && v1 < 50000 && v2 > 10 && v2 < 50000) {
                            found.push({addr: addr.toString(), x: parseFloat(v1.toFixed(1)), y: parseFloat(v2.toFixed(1))});
                            if (found.length >= 60) break;
                        }
                    } catch(e) { break; }
                }
            } catch(e) {}
            if (found.length >= 60) break;
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

    writeXY: function(addrStr, x, y) {
        var p = ptr(addrStr);
        var start = p.and(ptr(0xfffff000));
        Memory.protect(start, 4096, 'rwx');
        p.writeFloat(parseFloat(x));
        p.add(4).writeFloat(parseFloat(y));
        return "OK";
    },

    writeAtOffset: function(addrStr, dx, dy) {
        var p = ptr(addrStr);
        var start = p.and(ptr(0xfffff000));
        Memory.protect(start, 4096, 'rwx');
        var origX = readFloat(p);
        var origY = readFloat(p.add(4));
        var newX = origX + parseFloat(dx);
        var newY = origY + parseFloat(dy);
        p.writeFloat(newX);
        p.add(4).writeFloat(newY);
        return JSON.stringify({origX: origX.toFixed(1), origY: origY.toFixed(1), newX: newX.toFixed(1), newY: newY.toFixed(1)});
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

# Scan
print("Scanning for float pairs (range 30-50000)...")
pairs = json.loads(script.exports.scan_pairs())
print(f"Found {len(pairs)} candidates\n")

# Filter likely game coords (not screen resolution 1080/1920)
filtered = [p for p in pairs if p['x'] < 1000 or p['x'] > 2000 or p['y'] < 400 or p['y'] > 2000]
# But also include reasonable game coords
filtered = [p for p in pairs if not (p['x'] == 1080 and p['y'] == 1920)]

print(f"Testing {len(filtered)} non-screen-resolution candidates")
print("For each, adding 50 to X and reverting immediately")
print("Watch the screen to see if the character jumps!\n")

time.sleep(1)

tested = 0
for i, p in enumerate(filtered):
    if tested >= 20:
        break
    try:
        # Read current values first
        info = json.loads(script.exports.read_addr(p['addr']))
        x = info['x']
        y = info['y']

        # Skip obviously non-game values
        if x > 20000 or y > 20000:
            continue

        # Modify: add 50 to X
        result = json.loads(script.exports.write_at_offset(p['addr'], 50, 0))
        print(f"[{tested:2d}] {p['addr']}: ({result['origX']}, {result['origY']}) -> ({result['newX']}, {result['newY']})", end="")

        # Wait a moment for the game to render
        time.sleep(0.3)

        # Revert
        script.exports.write_xy(p['addr'], float(result['origX']), float(result['origY']))
        print(" [reverted]")

        tested += 1
    except Exception as e:
        print(f"[{tested:2d}] {p['addr']}: ERROR {e}")
        tested += 1

print(f"\nTested {tested} addresses.")
print("Did you see the character jump or flicker?")
print("If so, tell me which number [N] you saw the movement at.")

session.detach()
