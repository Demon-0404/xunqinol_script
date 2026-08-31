# -*- coding: utf-8 -*-
"""Speed research: hook houdini clock + enumerate all packet subtypes"""
import sys, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"

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

game_fd = -1
for tcp_file in ["net/tcp", "net/tcp6"]:
    r = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/{tcp_file}"],
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.split("\n"):
        line = line.strip()
        if not line or line.startswith("sl"):
            continue
        parts = line.split()
        if len(parts) >= 10 and parts[3] == "01":
            inode = parts[9]
            if inode != "0":
                r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/ | grep {inode}"],
                                   capture_output=True, text=True, timeout=10)
                for fl in r2.stdout.split("\n"):
                    fp = fl.strip().split()
                    if len(fp) >= 8:
                        try:
                            fd = int(fp[7])
                            if fd > 2:
                                game_fd = fd
                                break
                        except:
                            pass
        if game_fd > 0:
            break
    if game_fd > 0:
        break
print(f"Game fd={game_fd}", flush=True)
if game_fd < 0:
    sys.exit(1)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

JS = f"""
var GAME_FD = {game_fd};

// === Part 1: Try hooking clock_gettime in libhoudini ===
var mods = Process.enumerateModules();
var houdiniMod = null;
mods.forEach(function(m) {{
    if (m.name.indexOf('houdini') >= 0) {{
        houdiniMod = m;
        send({{t: 'houdini', name: m.name, base: m.base, size: m.size}});
    }}
}});

// Also list all modules for reference
var modList = [];
mods.forEach(function(m) {{
    if (m.name.indexOf('lib') >= 0 || m.name.indexOf('base') >= 0) {{
        var exports = [];
        try {{
            m.enumerateExports().forEach(function(e) {{
                if (e.name.indexOf('clock') >= 0 || e.name.indexOf('time') >= 0) {{
                    exports.push(e.name);
                }}
            }});
        }} catch(e) {{}}
        if (exports.length > 0) {{
            send({{t: 'mod_time', name: m.name, exports: exports}});
        }}
    }}
}});

// Try hooking clock_gettime in libhoudini
if (houdiniMod) {{
    try {{
        var exports = houdiniMod.enumerateExports();
        exports.forEach(function(e) {{
            if (e.name === 'clock_gettime' || e.name === 'gettimeofday' || e.name === 'time') {{
                send({{t: 'houdini_export', name: e.name, address: e.address}});
            }}
        }});
    }} catch(e) {{
        send({{t: 'houdini_err', msg: e.toString()}});
    }}
}}

// === Part 2: Enumerate ALL outbound packet types ===
var libc = Process.getModuleByName("libc.so");
var packetTypes = {{}};

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();

        if (fd === GAME_FD) {{
            var first = buf.readU8();
            var key = first;  // for type 3 packets
            var key2 = buf.add(1).readU8();  // key at byte 1
            var subtype = -1;

            if (len === 30 && first === 3) {{
                subtype = buf.add(7).readU8() ^ key2;  // plain[6] = subtype
            }}

            var desc = 'len=' + len + ' subtype=0x' + (subtype >= 0 ? ('0'+subtype.toString(16)).slice(-2) : '??');
            if (!packetTypes[desc]) {{
                packetTypes[desc] = {{count: 0, first: first, hex: []}};
            }}
            var entry = packetTypes[desc];
            entry.count++;

            if (entry.hex.length < 3) {{
                var h = [];
                for (var i = 0; i < Math.min(len, 40); i++) {{
                    h.push(('0' + buf.add(i).readU8().toString(16)).slice(-2));
                }}
                entry.hex.push(h.join(' '));
            }}
        }}
    }}
}});

// Periodically report
setInterval(function() {{
    var keys = Object.keys(packetTypes);
    keys.sort();
    send({{t: 'types', keys: keys}});
    keys.forEach(function(k) {{
        var e = packetTypes[k];
        send({{t: 'type_detail', desc: k, count: e.count, samples: e.hex}});
    }});
}}, 15000);

send({{t: 'ready'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] 监控中...", flush=True)
        print("[*] Part 1: 搜索 libhoudini 时间函数", flush=True)
        print("[*] Part 2: 枚举所有发包类型", flush=True)
    elif ptype == 'houdini':
        print(f"[HOUDINI] {payload['name']} base={payload['base']} size={payload['size']}", flush=True)
    elif ptype == 'mod_time':
        print(f"[MOD] {payload['name']}: {', '.join(payload['exports'])}", flush=True)
    elif ptype == 'houdini_export':
        print(f"[HOUDINI EXPORT] {payload['name']} @ {payload['address']}", flush=True)
    elif ptype == 'houdini_err':
        print(f"[HOUDINI ERR] {payload['msg']}", flush=True)
    elif ptype == 'types':
        print(f"\n=== 发包类型 ({len(payload['keys'])} unique) ===", flush=True)
    elif ptype == 'type_detail':
        samples = payload['samples']
        print(f"  {payload['desc']}  x{payload['count']}", flush=True)
        for s in samples[:2]:
            print(f"    {s}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting 20s...", flush=True)
try:
    for i in range(20):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
