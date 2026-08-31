# -*- coding: utf-8 -*-
"""Single-session PoC: walk same portal twice, 2nd time XOR bytes 24-27 to change dest."""
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

    captures = []  # (step_label, hex)
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
                print(f"[Capture #{n}] {payload['hex']}", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_portal_capture()

    # === STEP 1: walk through ANY portal ===
    before = len(captures)
    print("\n" + "=" * 60)
    print("  STEP 1: Walk through any portal (Portal X)")
    print("  Remember which map this portal takes you to!")
    print("=" * 60, flush=True)
    while len(captures) <= before:
        time.sleep(0.3)
    cap1 = captures[-1]
    print(f">>> Captured! You should now be at Portal X's destination.", flush=True)

    # === STEP 2: walk back through return portal ===
    before = len(captures)
    print("\n" + "=" * 60)
    print("  STEP 2: Walk back through the RETURN portal")
    print("  (go back to where you came from)")
    print("=" * 60, flush=True)
    while len(captures) <= before:
        time.sleep(0.3)
    cap_ret = captures[-1]
    print(f">>> Captured return portal!", flush=True)

    # === Analyze: compute redirect key for this portal pair ===
    b1 = bytes.fromhex(cap1)
    b_ret = bytes.fromhex(cap_ret)

    # Dominant XOR = counter delta
    xor_vals = [b1[i] ^ b_ret[i] for i in range(1, 29)]
    from collections import Counter
    dominant = Counter(xor_vals).most_common(1)[0][0]
    print(f"\n[*] Counter delta (Portal X vs Return): 0x{dominant:02x}", flush=True)

    # Which bytes differ from dominant? (these are the destination bytes)
    dest_bytes = [i for i in range(1, 29) if (b1[i] ^ b_ret[i]) != dominant]
    print(f"[*] Destination bytes (diff from dominant): {dest_bytes}", flush=True)

    if not dest_bytes:
        print("[!] No destination bytes found! All bytes same between portal and return?")
        session.detach()
        return

    # Build a simple XOR key for those bytes: flip the lowest bit
    # This should send us to a DIFFERENT map (adjacent map ID)
    xor_key_bytes = [0] * 29
    for i in dest_bytes:
        xor_key_bytes[i] = 0x01  # XOR each destination byte with 0x01

    # Convert to hex string for bytes 24-27 only (our current understanding)
    # Actually, use the detected dest_bytes to build the key
    dest_range = dest_bytes  # use all detected destination bytes
    xor_hex = ''
    for i in range(24, 28):  # focus on bytes 24-27
        if i < 29:
            xor_hex += f'{0x01:02x}'  # XOR with 0x01
    # pad to 4 bytes for bytes 24-27
    xor_hex = '01010101'

    print(f"[*] Redirect key: XOR bytes 24-27 with {xor_hex}", flush=True)

    # === STEP 3: Arm redirect, walk through SAME Portal X ===
    script.exports_sync.arm_byte_redirect(xor_hex)
    before = len(captures)
    redirect_done[0] = False

    print("\n" + "=" * 60)
    print("  STEP 3: Walk through the SAME Portal X again!")
    print("  (the exact same portal as Step 1)")
    print(f"  Bytes 24-27 will be XORed with {xor_hex}")
    print("  You should end up at a DIFFERENT map than Step 1!")
    print("=" * 60, flush=True)

    while not redirect_done[0] and len(captures) <= before:
        time.sleep(0.3)

    if redirect_done[0]:
        cap3 = captures[-1]
        print(f">>> Redirect applied! Modified: {cap3}", flush=True)
        # Show the change
        b3 = bytes.fromhex(cap3)
        print(f"  Bytes 24-27 changed to: {b3[24]:02x} {b3[25]:02x} {b3[26]:02x} {b3[27]:02x}", flush=True)
        print(f"  Check if you're at a DIFFERENT map than Step 1!", flush=True)
    else:
        print("[!] No redirect triggered", flush=True)

    time.sleep(2)
    script.exports_sync.disable_byte_redirect()
    session.detach()
    print("\n[*] Done.", flush=True)


if __name__ == '__main__':
    main()
