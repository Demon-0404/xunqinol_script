"""Read current map ID from memory by emulating jlmap_getMapID"""
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

    // Emulate jlmap_getMapID:
    // 0x12e760: LDR r3, [pc, #12]  -> reads from pc+12 = 0x12e770
    // 0x12e764: LDR r3, [pc, r3]   -> pc=0x12e768, so reads from 0x12e768 + offset
    // 0x12e768: LDR r3, [r3, #0]   -> reads from the address we just got
    // 0x12e76c: ???
    // 0x12e770: BX lr

    // Read the offset from literal pool at 0x12e770
    var lit_pool = base.add(0x12e770);
    var offset = lit_pool.readS32();
    send({t:'info', m:'Literal pool offset = ' + offset + ' (0x' + offset.toString(16) + ')'});

    // PC at second instruction = base + 0x12e768
    // Global pointer address = (base + 0x12e768) + offset
    var global_ptr_addr = base.add(0x12e768).add(offset);
    send({t:'info', m:'Global ptr addr = ' + global_ptr_addr});

    try {
        var ptr1 = global_ptr_addr.readPointer();
        send({t:'info', m:'Ptr1 = ' + ptr1});

        // Third instruction: LDR r3, [r3, #0] - loads from ptr1
        var ptr2 = ptr1.readPointer();
        send({t:'info', m:'Ptr2 = ' + ptr2});

        // The map ID should be at or near ptr2
        // The function then does some bit manipulation
        // Let's read 32 bytes around ptr2
        send({t:'info', m:'Data at ptr2:\\n' + hexdump(ptr2, {length: 64})});

        // Try reading map ID directly as various types
        var val32 = ptr2.readU32();
        var val16 = ptr2.readU16();
        send({t:'info', m:'u32=' + val32 + ' u16=' + val16});

        // Also try offset +0, +4, +8 etc
        for (var off = 0; off < 32; off += 4) {
            try {
                var v = ptr2.add(off).readU32();
                send({t:'debug', off: off, val: v});
            } catch(e) {}
        }
    } catch(e) {
        send({t:'err', m:'Read failed: ' + e});
    }

    // Also try: read the global directly
    // The global at 0x464a18 was g_jumpUrlCall
    // Maybe there's a g_mapManager or similar
    var g_mapMgr = base.add(0x12e770).readPointer();
    send({t:'info', m:'g_mapMgr guess: ' + g_mapMgr});
}

send({t:'ready'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("\n>>> DONE <<<", flush=True)
    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)
    elif ptype == 'debug':
        print(f"[DEBUG] off={payload['off']} val={payload['val']} (0x{payload['val'].toString(16)})", flush=True)
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
