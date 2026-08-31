"""Call openURLJNI via Frida to test map jumping"""
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
// Find libtestcpp.so base
var base = null;
Process.enumerateRanges('r--').forEach(function(r) {
    if (r.file && r.file.path && r.file.path.indexOf('libtestcpp.so') !== -1) {
        if (base === null || r.base.compare(base) < 0) base = r.base;
    }
});
if (!base) {
    send({t:'err', m:'libtestcpp.so not found'});
} else {
    send({t:'info', m:'Base=' + base});

    // Try to find openURLJNI by scanning exports
    var modules = Process.enumerateModules();
    var found = false;
    modules.forEach(function(m) {
        if (m.name.indexOf('libtestcpp') !== -1) {
            m.enumerateExports().forEach(function(exp) {
                if (exp.name.indexOf('openURL') !== -1 || exp.name.indexOf('jumpUrl') !== -1) {
                    send({t:'export', name: exp.name, addr: exp.address});
                    found = true;
                }
            });
        }
    });
    if (!found) {
        send({t:'info', m:'No openURL/jumpUrl exports found, will try offset-based call'});
    }

    // Hook jlapp_jumpUrl to see if openURLJNI calls it
    try {
        Interceptor.attach(base.add(0x1375d0), {
            onEnter: function(args) {
                send({t:'jumpUrl_called', url: args[0].readCString() || '(null)'});
            }
        });
        send({t:'info', m:'jlapp_jumpUrl hooked (monitor)'});
    } catch(e) {
        send({t:'err', m:'jumpUrl hook: ' + e});
    }

    // Hook AppDelegate::jumpUrl
    try {
        Interceptor.attach(base.add(0xda099), {
            onEnter: function(args) {
                send({t:'delegate_jumpUrl', a0: args[0], a1: args[1]});
            }
        });
    } catch(e) {
        send({t:'err', m:'delegate::jumpUrl hook: ' + e});
    }
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
        print("Now test calling openURLJNI...", flush=True)
        # After script loads, inject a call
        test_call_script = """
        var base = null;
        Process.enumerateRanges('r--').forEach(function(r) {
            if (r.file && r.file.path && r.file.path.indexOf('libtestcpp.so') !== -1) {
                if (base === null || r.base.compare(base) < 0) base = r.base;
            }
        });

        // Try calling jlapp_jumpUrl directly (offset 0x1375d0)
        // It takes (const char* url) and is safe to hook
        var jlapp_jumpUrl = new NativeFunction(base.add(0x1375d0), 'void', ['pointer']);

        var urls = [
            'xqj://map?name=北冥城',
            'xqj://teleport?city=北冥城',
            'xqj://jump?map_id=1',
            'xqj://open?scene=beiming',
        ];

        urls.forEach(function(url) {
            send({t:'test', url: url});
            try {
                var str = Memory.allocUtf8String(url);
                jlapp_jumpUrl(str);
                send({t:'result', url: url, status: 'called OK'});
            } catch(e) {
                send({t:'result', url: url, status: 'ERROR: ' + e});
            }
        });
        send({t:'done'});
        """
        script2 = session.create_script(test_call_script)
        script2.on('message', on_msg2)
        script2.load()

    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)
    elif ptype == 'err':
        print(f"[!] {payload['m']}", flush=True)
    elif ptype == 'export':
        print(f"[EXP] {payload['name']} @ {payload['addr']}", flush=True)
    elif ptype == 'jumpUrl_called':
        print(f">>> jlapp_jumpUrl CALLED: {payload['url']}", flush=True)
    elif ptype == 'delegate_jumpUrl':
        print(f">>> AppDelegate::jumpUrl CALLED", flush=True)
    elif ptype == 'test':
        print(f"\n[TEST] Calling with URL: {payload['url']}", flush=True)
    elif ptype == 'result':
        print(f"  -> {payload['url']}: {payload['status']}", flush=True)
    elif ptype == 'done':
        print("\nAll test URLs called. Check game screen!", flush=True)

def on_msg2(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'test':
        print(f"\n[TEST] Calling with URL: {payload['url']}", flush=True)
    elif ptype == 'result':
        print(f"  -> {payload['url']}: {payload['status']}", flush=True)
    elif ptype == 'done':
        print("\nAll URLs called. Check game screen for any reaction!", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.", flush=True)
    session.detach()
