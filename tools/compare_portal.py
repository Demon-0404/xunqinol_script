# -*- coding: utf-8 -*-
"""Interactive portal capture — clear prompts for each walk."""
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
    captured_29b = []

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error':
            print(f"[!] {msg}", flush=True); return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Frida ready", flush=True)
        elif ptype == 'portal_captured':
            if payload.get('len') == 29:
                captured_29b.append(payload['hex'])
                n = len(captured_29b)
                print(f"\n>>> [CAPTURE #{n}] 29B portal packet!", flush=True)
                print(f"    hex: {payload['hex']}", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)

    # Arm continuous portal capture
    script.exports_sync.start_portal_capture()
    print("[*] Portal monitor active", flush=True)

    # === Portal #1 ===
    before1 = len(captured_29b)
    print("\n" + "="*50)
    print(">>> STEP 1: Walk through portal A (change map)")
    print(">>> Waiting for 29B capture...")
    print("="*50, flush=True)
    while len(captured_29b) <= before1:
        time.sleep(0.3)
    p1 = captured_29b[-1]
    print(f">>> Portal #1 captured!", flush=True)

    # === Return portal (ignore) ===
    before_ret = len(captured_29b)
    print("\n" + "="*50)
    print(">>> STEP 2: Walk through RETURN portal (go back)")
    print(">>> Waiting for 29B capture...")
    print("="*50, flush=True)
    while len(captured_29b) <= before_ret:
        time.sleep(0.3)
    pret = captured_29b[-1]
    print(f">>> Return portal captured (will be ignored for comparison)", flush=True)

    # === Portal #2 (same as #1) ===
    before2 = len(captured_29b)
    print("\n" + "="*50)
    print(">>> STEP 3: Walk through portal A AGAIN (SAME portal as step 1)")
    print(">>> Waiting for 29B capture...")
    print("="*50, flush=True)
    while len(captured_29b) <= before2:
        time.sleep(0.3)
    p2 = captured_29b[-1]
    print(f">>> Portal #2 captured!", flush=True)

    # === COMPARE ===
    print(f"\n{'='*60}")
    print(f"  COMPARE: Portal A #1 vs Portal A #2")
    print(f"{'='*60}")
    print(f"  #1: {p1}")
    print(f"  #2: {p2}")
    print(f"\n  Byte-by-byte diff (send packet, plaintext, 29B):")
    print(f"  {'Pos':>4}  {'#1':>4}  {'#2':>4}  Status")
    print(f"  {'---':>4}  {'---':>4}  {'---':>4}  ------")

    b1 = bytes.fromhex(p1)
    b2 = bytes.fromhex(p2)
    same = 0; diff = 0; diff_pos = []
    for i in range(29):
        v1 = b1[i]; v2 = b2[i]
        if v1 == v2:
            same += 1; s = "SAME"
        else:
            diff += 1; s = "DIFF <<<"; diff_pos.append(i)
        print(f"  {i:3d}  0x{v1:02x}  0x{v2:02x}  {s}")

    print(f"\n  >>> SUMMARY: SAME={same}, DIFF={diff}")
    if diff_pos:
        print(f"  >>> DYNAMIC byte positions (seq/timestamp/checksum): {diff_pos}")
        static = [i for i in range(29) if i not in diff_pos]
        print(f"  >>> STATIC byte positions (candidate DESTINATION): {static}")
        print(f"\n  >>> Return portal (#ret): {pret}")
        bret = bytes.fromhex(pret)
        ret_same = sum(1 for i in range(29) if b1[i] == bret[i])
        print(f"  >>> #1 vs return portal: SAME={ret_same}/29")
        # Also show which positions differ between #1 and return
        ret_diff = [i for i in range(29) if b1[i] != bret[i]]
        print(f"  >>> #1 vs return DIFF positions: {ret_diff}")
        # Intersection: positions that are SAME in #1=#2 but DIFF in #1=return
        dest_candidates = [i for i in static if i in ret_diff]
        print(f"  >>> LIKELY DESTINATION bytes (static for same portal, diff for return): {dest_candidates}")

    session.detach()
    print("\n[*] Done.", flush=True)

if __name__ == '__main__':
    main()
