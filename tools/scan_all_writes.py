"""Enumerate modules and find write-related functions"""
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

# Also check TCP connections with raw read
print("=== TCP connections (raw) ===", flush=True)
r = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/net/tcp"],
                   capture_output=True, text=True, timeout=10)
for line in r.stdout.split("\n"):
    if line.strip():
        parts = line.strip().split()
        if len(parts) >= 10:
            remote = parts[2]
            local = parts[1]
            inode = parts[9]
            # Decode port from hex
            try:
                rport_hex = remote.split(':')[1] if ':' in remote else ''
                if rport_hex:
                    rport = int(rport_hex, 16)
                    if rport == 30002:
                        print(f"  GAME CONN: local={local} remote={remote} inode={inode}", flush=True)
            except:
                pass
        print(f"  {line}", flush=True)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)
print("Attached!", flush=True)

JS = """
// Enumerate all modules
var modules = Process.enumerateModules();
var libcMod = null;
var sslMod = null;

modules.forEach(function(m) {
    if (m.name.indexOf('libc') !== -1 || m.name.indexOf('libssl') !== -1 ||
        m.name.indexOf('libcrypto') !== -1) {
        send({t:'module', name: m.name, base: m.base.toString(), size: m.size});
        if (m.name.indexOf('libc.so') !== -1) libcMod = m;
        if (m.name.indexOf('libssl') !== -1) sslMod = m;
    }
});

// Enumerate exports from libc to find write functions
if (libcMod) {
    var exports = libcMod.enumerateExports();
    var writeExports = [];
    exports.forEach(function(exp) {
        var n = exp.name.toLowerCase();
        if (n.indexOf('send') !== -1 || n.indexOf('write') !== -1 ||
            n.indexOf('recv') !== -1 || n.indexOf('read') !== -1) {
            writeExports.push(exp.name);
        }
    });
    send({t:'libc_exports', list: writeExports.join(', ')});
}

// Enumerate exports from libssl
if (sslMod) {
    var exports = sslMod.enumerateExports();
    var sslExports = [];
    exports.forEach(function(exp) {
        var n = exp.name.toLowerCase();
        if (n.indexOf('write') !== -1 || n.indexOf('read') !== -1) {
            sslExports.push(exp.name);
        }
    });
    send({t:'ssl_exports', list: sslExports.join(', ') || '(none matching)'});
}

// Now try to hook using full module names
function safeHook(moduleName, funcName) {
    try {
        var mod = Process.findModuleByName(moduleName);
        if (!mod) {
            send({t:'warn', msg: 'Module not found: ' + moduleName});
            return false;
        }
        var ptr = Module.findExportByName(moduleName, funcName);
        if (!ptr) {
            // Try to find in exports
            var exports = mod.enumerateExports();
            for (var i = 0; i < exports.length; i++) {
                if (exports[i].name === funcName) {
                    ptr = exports[i].address;
                    break;
                }
            }
        }
        if (!ptr) {
            send({t:'warn', msg: 'Export not found: ' + moduleName + '!' + funcName});
            return false;
        }
        send({t:'hooked', module: moduleName, func: funcName});
        Interceptor.attach(ptr, {
            onEnter: function(args) {
                var buf = null, len = 0;
                if (funcName.indexOf('write') !== -1 || funcName === 'send' || funcName === 'sendto') {
                    buf = args[1];
                    len = args[2].toInt32();
                }
                if (len > 0 && len <= 64 && buf) {
                    var first = buf.readU8();
                    send({t:'packet', func: funcName, len: len, first: first, hex: hexdump(buf, {length: Math.min(len, 32)})});
                }
            }
        });
        return true;
    } catch(e) {
        send({t:'err', msg: 'Hook failed: ' + moduleName + '!' + funcName + ' - ' + e});
        return false;
    }
}

// Get the actual module names from Process
var libcName = null, sslName = null;
modules.forEach(function(m) {
    if (m.name.endsWith('libc.so')) libcName = m.name;
    if (m.name.endsWith('libssl.so')) sslName = m.name;
});
send({t:'info', msg: 'libc=' + libcName + ' ssl=' + sslName});

if (libcName) {
    safeHook(libcName, 'send');
    safeHook(libcName, 'sendto');
    safeHook(libcName, 'write');
    safeHook(libcName, 'writev');
    safeHook(libcName, '__libc_write');
}
if (sslName) {
    safeHook(sslName, 'SSL_write');
    safeHook(sslName, 'SSL_write_ex');
}

send({t:'ready'});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("\n[*] Ready — move character in game...", flush=True)
    elif ptype == 'module':
        print(f"  [MOD] {payload['name']} base={payload['base']} size={payload['size']}", flush=True)
    elif ptype == 'libc_exports':
        print(f"\n  libc write exports: {payload['list']}", flush=True)
    elif ptype == 'ssl_exports':
        print(f"  ssl write exports: {payload['list']}", flush=True)
    elif ptype == 'hooked':
        print(f"  [+] HOOKED: {payload['module']}!{payload['func']}", flush=True)
    elif ptype == 'warn':
        print(f"  [!] {payload['msg']}", flush=True)
    elif ptype == 'packet':
        print(f"\n  >>> [{payload['func']}] len={payload['len']} first=0x{payload['first']:02x}", flush=True)
        print(f"  {payload['hex']}", flush=True)
    elif ptype == 'err':
        print(f"  [ERR] {payload['msg']}", flush=True)
    elif ptype == 'info':
        print(f"  [*] {payload['msg']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("\n等待数据包... (20秒)", flush=True)
try:
    for i in range(20):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
