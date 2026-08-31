# -*- coding: utf-8 -*-
"""Test if byte 20 is safe to modify (unlike byte 5 which caused disconnect)."""
import sys, time, os, json, subprocess

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
    game_fds = []
    for tcp_file in ["net/tcp", "net/tcp6"]:
        r = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/{tcp_file}"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.split("\n"):
            line = line.strip()
            if not line or line.startswith("sl"): continue
            parts = line.split()
            if len(parts) >= 10 and parts[3] == "01":
                inode = parts[9]
                if inode != "0":
                    r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/ | grep {inode}"], capture_output=True, text=True, timeout=10)
                    for fl in r2.stdout.split("\n"):
                        fp = fl.strip().split()
                        if len(fp) >= 8:
                            try:
                                fd = int(fp[7])
                                remote = parts[2]
                                if "0100007F" in remote or "0202000A" in remote: continue
                                if fd > 2 and fd not in game_fds:
                                    game_fds.append(fd)
                            except: pass
    if not game_fds: raise Exception("No game sockets found")
    subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)
    with open(os.path.join(SCRIPT_DIR, 'teleport_v2.js'), 'r', encoding='utf-8') as f:
        JS = f.read().replace('GAME_FDS_PLACEHOLDER', json.dumps(game_fds))
    import frida
    dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
    session = dev.attach(pid)
    return session, JS, pid

def main():
    session, js_code, pid = connect()
    captures = []
    diag_hit = [False]
    disconnect = [False]

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error': return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Ready", flush=True)
        elif ptype == 'diag_xor':
            diag_hit[0] = True
            print(f">>> byte[{payload['pos']}] 0x{payload['old']:02x} -> 0x{payload['new']:02x}", flush=True)
        elif ptype == 'portal_captured':
            if payload.get('len') == 29:
                captures.append(payload['hex'])
                print(f"  [Capture] {payload['hex']}", flush=True)
        elif ptype in ('recv_zero_blocked', 'recv_err', 'close_blocked', 'shutdown_blocked'):
            disconnect[0] = True
            print(f"[!!!] DISCONNECT: {ptype}", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_portal_capture()

    # TEST: XOR byte 20 with 0x01
    script.exports_sync.diag_xor_byte(20, 0x01)
    before = len(captures)

    print("\n" + "=" * 60)
    print("  TEST: Walk through portal - byte 20 XOR 0x01")
    print("  (modifying portal/map identifier byte)")
    print("=" * 60, flush=True)

    deadline = time.time() + 30
    while not diag_hit[0] and time.time() < deadline:
        time.sleep(0.3)
        if disconnect[0]:
            print(">>> DISCONNECTED! Bytes 20-23 ARE protected like byte 5!")
            break

    if diag_hit[0] and not disconnect[0]:
        time.sleep(5)
        if disconnect[0]:
            print(">>> DISCONNECTED after delay!")
        else:
            print(">>> NO disconnect! Bytes 20-23 safe to modify.")
            print(">>> Did portal work normally? Where did you go?")

    script.exports_sync.diag_clear()
    session.detach()
    print("[*] Done.", flush=True)

if __name__ == '__main__':
    main()
