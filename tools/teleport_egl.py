# -*- coding: utf-8 -*-
"""Call jlapp_jumpUrl from game main thread — teleport controller"""
import sys, time, subprocess, os, json

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def connect():
    subprocess.run([ADB, "-s", SERIAL, "root"], capture_output=True, timeout=10)
    r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"], capture_output=True, text=True, timeout=15)
    pid = None
    for line in r.stdout.split("\n"):
        if "proj.xqj" in line:
            parts = line.split()
            if len(parts) >= 2: pid = int(parts[1]); break
    if not pid: raise Exception("Game not found")

    subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

    with open(os.path.join(SCRIPT_DIR, 'teleport_egl.js'), 'r', encoding='utf-8') as f:
        JS = f.read()

    import frida
    dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
    session = dev.attach(pid)

    script = session.create_script(JS)
    script.on('message', on_msg)
    script.load()
    time.sleep(2)
    return session, script

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if msg.get('type') == 'error':
        print(f"[!] {msg.get('description', msg)}", flush=True)
        return
    if not isinstance(payload, dict): return
    ptype = payload.get('t', '?')
    msg_text = payload.get('msg', '')
    if ptype == 'ready':
        print(f"[*] {msg_text}", flush=True)
    elif ptype == 'log':
        print(f"    {msg_text}", flush=True)
    elif ptype == 'err':
        print(f"[!] {msg_text}", flush=True)
    else:
        print(f"  [{ptype}] {msg_text}", flush=True)

def status(script):
    result = script.exports_sync.status()
    print(f"[*] Status: {result}", flush=True)

if __name__ == '__main__':
    print("[*] Connecting to game...", flush=True)
    session, script = connect()
    print("[*] Script loaded! Main thread hook active.", flush=True)
    print("[*]", flush=True)
    print("[*] Commands:", flush=True)
    print("[*]   arm <url>  — arm a jlapp_jumpUrl call from main thread", flush=True)
    print("[*]   status     — show current status", flush=True)
    print("[*]   quit       — exit", flush=True)
    print("[*]", flush=True)

    try:
        while True:
            cmd = input(">>> ").strip()
            if not cmd:
                continue
            if cmd == 'quit' or cmd == 'exit':
                break
            elif cmd == 'status' or cmd == 's':
                status(script)
            elif cmd.startswith('arm '):
                url = cmd[4:].strip()
                result = script.exports_sync.arm_jump(url)
                print(f"[*] {result}", flush=True)
            else:
                print(f"[!] Unknown: {cmd}", flush=True)
    except KeyboardInterrupt:
        pass

    session.detach()
    print("[*] Done.", flush=True)
