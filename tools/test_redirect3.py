# -*- coding: utf-8 -*-
"""Full self-contained PoC: capture A, B, return; compute real redirect key; apply it."""
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

def wait_for_capture(captures, current_count):
    """Wait for a new 29B portal to be captured. Returns the new hex."""
    while len(captures) <= current_count:
        time.sleep(0.3)
    return captures[-1]

def main():
    session, js_code, pid = connect()
    captures = []
    redirect_done = [False]

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error': return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Ready", flush=True)
        elif ptype == 'byte_redirect':
            redirect_done[0] = True
            print(f">>> REDIRECT: {payload.get('msg', '')}", flush=True)
        elif ptype == 'portal_captured':
            if payload.get('len') == 29:
                captures.append(payload['hex'])
                n = len(captures)
                print(f"  [Capture #{n}] {payload['hex']}", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_portal_capture()

    # === STEP 1: Portal A ===
    print("\n" + "=" * 60)
    print("  STEP 1: Walk through Portal A")
    print("  (any portal - remember which one!)")
    print("=" * 60, flush=True)
    cap_a = wait_for_capture(captures, 0)
    print("  >>> Portal A captured. Now at destination A.", flush=True)

    # === STEP 2: Return ===
    print("\n" + "=" * 60)
    print("  STEP 2: Walk back through the RETURN portal")
    print("=" * 60, flush=True)
    cap_ret = wait_for_capture(captures, 1)
    print("  >>> Return captured. Back at origin.", flush=True)

    # === STEP 3: Portal B (DIFFERENT portal!) ===
    print("\n" + "=" * 60)
    print("  STEP 3: Walk through Portal B (DIFFERENT portal!)")
    print("  (must be a different portal from Step 1)")
    print("=" * 60, flush=True)
    cap_b = wait_for_capture(captures, 2)
    print("  >>> Portal B captured. Now at destination B.", flush=True)

    # === ANALYSIS: compute redirect key ===
    b_a = bytes.fromhex(cap_a)
    b_b = bytes.fromhex(cap_b)

    # Find dominant XOR = counter delta
    from collections import Counter
    xors = [b_a[i] ^ b_b[i] for i in range(1, 29)]
    dominant = Counter(xors).most_common(1)[0][0]
    dom_count = sum(1 for x in xors if x == dominant)

    print(f"\n{'=' * 60}")
    print(f"  ANALYSIS: Portal A vs Portal B")
    print(f"  Counter delta: 0x{dominant:02x} ({dom_count}/28 bytes)")
    print(f"{'=' * 60}")

    # Find destination bytes (XOR != dominant)
    dest_info = []
    for i in range(1, 29):
        xv = b_a[i] ^ b_b[i]
        if xv != dominant:
            plain_xor = xv ^ dominant
            dest_info.append((i, xv, plain_xor))
            print(f"  Byte {i}: enc XOR=0x{xv:02x}, plain XOR=0x{plain_xor:02x}")

    if not dest_info:
        print("\n[!] NO destination bytes found! All bytes identical between portals?")
        print("    This means A and B are the SAME portal or go to the SAME destination.")
        session.detach()
        return

    # Build redirect key for the destination bytes
    print(f"\n[*] Destination bytes: {[d[0] for d in dest_info]}")
    print(f"[*] Plain XOR values: {[f'0x{d[2]:02x}' for d in dest_info]}")

    # Build hex key for bytes 24-27 specifically
    # Find the plain XOR for bytes 24-27
    key_bytes = {}
    for i, xv, plain_xor in dest_info:
        key_bytes[i] = plain_xor

    # Build hex key string for bytes 24-27
    redirect_hex = ''
    for i in range(24, 28):
        if i in key_bytes:
            redirect_hex += f'{key_bytes[i]:02x}'
        else:
            redirect_hex += '00'  # no change for this byte

    print(f"[*] Redirect key (bytes 24-27): {redirect_hex}")

    # === STEP 4: Return from destination B ===
    print("\n" + "=" * 60)
    print("  STEP 4: Walk back through the RETURN portal")
    print("  (go back to origin)")
    print("=" * 60, flush=True)
    cap_ret2 = wait_for_capture(captures, 3)
    print("  >>> Return captured. Back at origin.", flush=True)

    # === STEP 5: Portal A again WITH redirect ===
    script.exports_sync.arm_byte_redirect(redirect_hex)
    redirect_done[0] = False

    print("\n" + "=" * 60)
    print("  STEP 5: Walk through Portal A AGAIN")
    print(f"  Bytes 24-27 will XOR with: {redirect_hex}")
    print("  >>> Should go to Portal B's destination instead of A's!")
    print("=" * 60, flush=True)

    cap_redirect = wait_for_capture(captures, 4)
    if redirect_done[0]:
        print(f"  >>> REDIRECT APPLIED! Modified: {cap_redirect}", flush=True)
        b_mod = bytes.fromhex(cap_redirect)
        print(f"  Bytes 24-27 sent: {b_mod[24]:02x} {b_mod[25]:02x} {b_mod[26]:02x} {b_mod[27]:02x}", flush=True)
        print(f"  Check: are you at Portal B's destination instead of A's?", flush=True)
    else:
        print("  [!] No redirect triggered - did you walk through Portal A?", flush=True)

    time.sleep(2)
    script.exports_sync.disable_byte_redirect()
    session.detach()
    print("\n[*] Done.", flush=True)

if __name__ == '__main__':
    main()
