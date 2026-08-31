# -*- coding: utf-8 -*-
"""Revert all modified addresses from test_write"""
import frida
import json
import time

JS = """
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
    writeXY: function(addrStr, x, y) {
        var p = ptr(addrStr);
        var start = p.and(ptr(0xfffff000));
        Memory.protect(start, 4096, 'rwx');
        p.writeFloat(parseFloat(x));
        p.add(4).writeFloat(parseFloat(y));
        return "OK";
    },
    readAddr: function(addrStr) {
        var p = ptr(addrStr);
        var x = readFloat(p);
        var y = readFloat(p.add(4));
        return JSON.stringify({x: parseFloat(x.toFixed(2)), y: parseFloat(y.toFixed(2))});
    }
};
"""

# List of addresses that were modified (subtract 50 from x)
addrs = [
    "0xc601688", "0xc60168c", "0xc601698", "0xc60169c", "0xd2490c0",
    "0x6fe42660", "0x6fe44358", "0x6fe4435c", "0x6fe49db8", "0x6fe49dd8",
    "0x6fe49e40", "0x6fe4aac0", "0x6fe4aad0", "0x6fe4ac04", "0x6fe4ac68",
    "0x6fe4ace0", "0x6fe4b820", "0x6fe4b888", "0x6fe4b978", "0x6fe4b990"
]

device = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = device.attach(5630)
script = session.create_script(JS)
script.load()
time.sleep(0.5)

for addr in addrs:
    try:
        info = json.loads(script.exports.read_addr(addr))
        orig_x = info['x'] - 50  # subtract what we added
        orig_y = info['y']
        script.exports.write_xy(addr, orig_x, info['y'])
        print(f"[OK] {addr}: reverted X from {info['x']} to {orig_x}")
    except Exception as e:
        print(f"[ERR] {addr}: {e}")

session.detach()
print("Done.")
