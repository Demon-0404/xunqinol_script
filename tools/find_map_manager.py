"""Find map manager object to call jlmap_createMapForID properly"""
import sys, os, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16544"

r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"],
                   capture_output=True, text=True, timeout=15)
pid = None
for line in r.stdout.split("\n"):
    if "proj.xqj" in line:
        parts = line.split()
        if len(parts) >= 2:
            pid = int(parts[1])
            break
print(f"PID={pid}", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)
print("Attached!", flush=True)

JS = """
var base = null;
Process.enumerateRanges('r--').forEach(function(r) {
    if (r.file && r.file.path && r.file.path.indexOf('libtestcpp.so') !== -1) {
        if (base === null || r.base.compare(base) < 0) base = r.base;
    }
});
if (!base) { send({t:'err', m:'no base'}); } else {
    send({t:'info', m:'Base=' + base});

    // Read jlmap_getMapID to understand what it accesses
    // At 0x12e760:
    // 300c e59f  -> LDR r3, [pc, #12] ; load a global pointer
    // 3003 e79f  -> LDR r3, [pc, r3]  ; dereference
    // 3000 e593  -> LDR r3, [r3]      ; dereference again
    // 00d0 e1c3  -> ???
    // ff1e e12f  -> BX lr
    // d084 0032  -> the literal pool value

    // The function loads a global pointer, dereferences it twice, then returns
    // Let's read the global pointer at pc+12 to find the map manager

    var getMapID_addr = base.add(0x12e760);
    send({t:'info', m:'jlmap_getMapID @ ' + getMapID_addr});

    // Read the literal pool value (at offset 0x12e774 = 0x12e760 + 0x14)
    var pool_addr = base.add(0x12e774);
    var pool_val = pool_addr.readU32();
    send({t:'info', m:'Literal pool @ ' + pool_addr + ' = ' + pool_val});

    // The actual global address = address_of_instruction + 4 + pool_val
    // For LDR r3, [pc, #12]: pc = current_addr + 4 (Thumb), so target = (addr+4) & ~3 + 12 + addr = addr + 4 + 12
    // Actually, PC-relative LDR: address = (PC & 0xFFFFFFFC) + offset
    // In Thumb: PC = current_instruction_addr + 4
    // So: target = (getMapID_addr + 4) & ~3 + pool_val
    // Wait, pool_val = 0x0032d084 in little-endian. Let me check.

    // The instructions at 0x12e760:
    // 300c -> the instruction bytes read earlier: 0c 30
    // e59f -> 9f e5

    // Actually in memory the bytes are: 0c 30 9f e5 = LDR r3, [pc, #12]
    // Then: 03 30 9f e7 = LDR r3, [pc, r3]
    // Then: 00 30 93 e5 = LDR r3, [r3]
    // Then: d0 00 c3 e1 = ???
    // Then: 1e ff 2f e1 = BX lr

    // The literal pool value is a PC-relative offset from the first LDR.
    // PC at first LDR = addr + 4 = 0x12e764
    // Target = (PC & ~3) + 12 = 0x12e764 + 12 = 0x12e770

    // At 0x12e770, the value should be the offset to the global pointer
    // Actually, the instruction is "LDR r3, [pc, #12]" which loads from PC+12
    // PC = 0x12e764, so load from 0x12e770

    var ldr_target = base.add(0x12e770);
    var offset = ldr_target.readU32();
    send({t:'info', m:'LDR target value = ' + offset + ' (0x' + offset.toString(16) + ')'});

    // The second instruction "LDR r3, [pc, r3]" loads from PC + r3
    // PC = 0x12e768, r3 = the value we just loaded
    var global_ptr_addr = base.add(0x12e768).add(offset);
    send({t:'info', m:'Global pointer at ' + global_ptr_addr});

    try {
        var ptr1 = global_ptr_addr.readPointer();
        send({t:'info', m:'Level 1 ptr = ' + ptr1});

        var ptr2 = ptr1.readPointer();
        send({t:'info', m:'Level 2 ptr (map manager?) = ' + ptr2});

        // Try reading first few fields
        send({t:'info', m:'First fields: ' + hexdump(ptr2, {length: 64})});
    } catch(e) {
        send({t:'err', m:'Read failed: ' + e});
    }

    // Also try: find the jlmap_createMapForID function and analyze it
    // At 0x12e778:
    // 4070 e92d -> PUSH {...}
    // Based on the strings, it takes (int mapID, ...)
    // Let's read its first instructions
    var createMap_addr = base.add(0x12e778);
    send({t:'info', m:'jlmap_createMapForID first 32 bytes: ' + hexdump(createMap_addr, {length: 32})});
}

send({t:'ready'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("\n>>> READY <<<", flush=True)
    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['m']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.", flush=True)
    session.detach()
