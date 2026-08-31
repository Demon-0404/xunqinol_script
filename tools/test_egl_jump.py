"""Auto-test jlapp_jumpUrl from EGL thread"""
import sys, time, subprocess, os, json

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

subprocess.run([ADB, "-s", SERIAL, "root"], capture_output=True, timeout=10)
r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"], capture_output=True, text=True, timeout=15)
pid = None
for line in r.stdout.split("\n"):
    if "proj.xqj" in line:
        parts = line.split()
        if len(parts) >= 2: pid = int(parts[1]); break
print(f"[*] PID={pid}")

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

with open(os.path.join(SCRIPT_DIR, 'teleport_egl_v2.js'), 'r', encoding='utf-8') as f:
    JS = f.read()

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

fired = False
def on_msg(msg, data):
    global fired
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        desc = msg.get('description', str(msg))
        if 'Script' in desc:
            print(f"[!] {desc}", flush=True)
        return
    if not isinstance(payload, dict): return
    ptype = payload.get('t', '?')
    msg_text = payload.get('msg', '')
    if ptype == 'ready': print(f"[*] {msg_text}", flush=True)
    elif ptype == 'log':
        if 'HOOK FIRED' in msg_text:
            print(f"\n{'='*60}")
            fired = True
        print(f"    {msg_text}", flush=True)
    elif ptype == 'err': print(f"[!] {msg_text}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()
time.sleep(2)

url = sys.argv[1] if len(sys.argv) > 1 else 'xqj://map?name=test'

print(f"\n[*] Arming: {url}", flush=True)
result = script.exports_sync.arm_jump(url)
print(f"    {result}", flush=True)

print(f"[*] Waiting up to 30s for hook to fire...", flush=True)
for i in range(30):
    time.sleep(1)
    if fired:
        print(f"\n[!!!] HOOK FIRED! Check game screen!", flush=True)
        break
    if i % 5 == 0:
        status = script.exports_sync.status()
        print(f"    [{i}s] {status}", flush=True)

if not fired:
    print(f"\n[!] Hook did not fire within 30s", flush=True)
    status = script.exports_sync.status()
    print(f"    Final status: {status}", flush=True)

time.sleep(2)
session.detach()
print("[*] Done.", flush=True)
