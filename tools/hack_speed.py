# -*- coding: utf-8 -*-
"""Speed hack v3: hook math functions to trace coordinate system + try memory write"""
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

# Find fd
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
var libc = Process.getModuleByName("libc.so");
var M1 = null, M2 = null;
var currentX = null, currentY = null;
var posLog = [];

// Phase 1: Capture current position
Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var plain = [];
            for (var i = 0; i < 29; i++) plain.push(buf.add(i + 1).readU8() ^ key);
            M1 = plain[1]; M2 = plain[3];
            var newX = plain[17], newY = plain[21];
            if (currentX !== null) {{
                var dx = newX - currentX;
                var dy = newY - currentY;
                if (dx !== 0 || dy !== 0) {{
                    posLog.push({{x: newX, y: newY, dx: dx, dy: dy}});
                    send({{t: 'move', x: newX, y: newY, dx: dx, dy: dy}});
                }}
            }}
            currentX = newX;
            currentY = newY;
        }}
    }}
}});

// Phase 2: Try to find position in memory by reading /proc/self/mem
// Use the libc read() to access process memory
var readNative = new NativeFunction(libc.getExportByName("read"), 'ssize_t', ['int', 'pointer', 'size_t']);
var openNative = new NativeFunction(libc.getExportByName("open"), 'int', ['pointer', 'int', 'int']);
var closeNative = new NativeFunction(libc.getExportByName("close"), 'int', ['int']);
var lseekNative = new NativeFunction(libc.getExportByName("lseek"), 'off_t', ['int', 'off_t', 'int']);

// Phase 3: Hook math functions to trace movement calculations
var mathModules = ['libm.so', 'libc.so'];
var mathFuncs = ['sin', 'cos', 'atan2', 'sqrt', 'sinf', 'cosf', 'atan2f', 'sqrtf'];

mathFuncs.forEach(function(funcName) {{
    mathModules.forEach(function(modName) {{
        try {{
            var mod = Process.getModuleByName(modName);
            var addr = mod.getExportByName(funcName);
            if (addr) {{
                Interceptor.attach(addr, {{
                    onEnter: function(args) {{
                        this.funcName = funcName;
                        if (funcName === 'atan2' || funcName === 'atan2f') {{
                            this.y = parseFloat(args[0]);
                            this.x = parseFloat(args[1]);
                        }} else if (funcName === 'sqrt' || funcName === 'sqrtf') {{
                            this.val = parseFloat(args[0]);
                        }} else {{
                            this.val = parseFloat(args[0]);
                        }}
                    }},
                    onLeave: function(ret) {{
                        if (posLog.length > 0 && posLog.length <= 5) {{
                            var info = '';
                            if (this.funcName === 'atan2' || this.funcName === 'atan2f') {{
                                info = 'atan2(y=' + this.y.toFixed(2) + ', x=' + this.x.toFixed(2) + ')=' + parseFloat(ret).toFixed(4);
                            }} else if (this.funcName === 'sqrt' || this.funcName === 'sqrtf') {{
                                info = 'sqrt(' + this.val.toFixed(2) + ')=' + parseFloat(ret).toFixed(2);
                            }} else {{
                                info = this.funcName + '(' + this.val.toFixed(4) + ')=' + parseFloat(ret).toFixed(4);
                            }}
                            send({{t: 'math', info: info}});
                        }}
                    }}
                }});
            }}
        }} catch(e) {{}}
    }});
}});

send({{t: 'ready'}});

// Phase 4: After 5 seconds, try to modify the in-place speed hack with force
setTimeout(function() {{
    send({{t: 'status', msg: 'Hooks active. Move to trigger math traces.'}});
}}, 5000);
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')
    if ptype == 'ready':
        print("[*] Math hooks + position monitor ready", flush=True)
        print("[*] 请在游戏中点击远处让角色移动！", flush=True)
    elif ptype == 'move':
        print(f"  MOVE: X={payload['x']} Y={payload['y']} dx={payload['dx']:+d} dy={payload['dy']:+d}", flush=True)
    elif ptype == 'math':
        print(f"    MATH: {payload['info']}", flush=True)
    elif ptype == 'status':
        print(f"[*] {payload['msg']}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
print("Waiting 30s...", flush=True)
try:
    for i in range(30):
        time.sleep(1)
except KeyboardInterrupt:
    pass
session.detach()
print("Done.", flush=True)
