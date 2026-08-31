# -*- coding: utf-8 -*-
"""Run a given Frida JS script against the game process"""
import sys, time, subprocess, os, json

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_script(js_filename):
    subprocess.run([ADB, "-s", SERIAL, "root"], capture_output=True, timeout=10)
    r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"], capture_output=True, text=True, timeout=15)
    pid = None
    for line in r.stdout.split("\n"):
        if "proj.xqj" in line:
            parts = line.split()
            if len(parts) >= 2: pid = int(parts[1]); break
    if not pid: raise Exception("Game not found")

    subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

    with open(os.path.join(SCRIPT_DIR, js_filename), 'r', encoding='utf-8') as f:
        JS = f.read()

    import frida
    dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
    session = dev.attach(pid)

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error':
            print(f"[!] {msg.get('description', msg)}", flush=True)
            if 'stack' in msg:
                print(f"    Stack: {msg['stack']}", flush=True)
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

    script = session.create_script(JS)
    script.on('message', on_msg)
    script.load()
    return session, script

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: run_hook.py <script.js>")
        sys.exit(1)
    js_file = sys.argv[1]
    print(f"[*] Loading: {js_file}", flush=True)
    session, script = run_script(js_file)
    print(f"[*] Script loaded. Waiting... (Ctrl+C to stop)", flush=True)
    try:
        time.sleep(120)
    except KeyboardInterrupt:
        pass
    session.detach()
    print("[*] Done.", flush=True)
