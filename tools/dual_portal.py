# -*- coding: utf-8 -*-
"""Capture 2 different portals in same session, XOR them to find destination bytes."""
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
    captures = []  # (label, send_index, hex, send_count_before)

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error': return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Frida ready", flush=True)
        elif ptype == 'portal_captured':
            if payload.get('len') == 29:
                captures.append(payload['hex'])
                n = len(captures)
                print(f"\n>>> [CAPTURE #{n}] 29B portal: {payload['hex']}", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_portal_capture()

    # === Portal A ===
    before = len(captures)
    print("\n" + "="*60)
    print("  STEP 1: Walk through PORTAL A (first portal)")
    print("="*60, flush=True)
    while len(captures) <= before:
        time.sleep(0.3)
    pA = captures[-1]
    print(f">>> Portal A captured!", flush=True)

    # === Return portal (go back to origin) ===
    before = len(captures)
    print("\n" + "="*60)
    print("  STEP 2: Walk through RETURN portal (go back)")
    print("="*60, flush=True)
    while len(captures) <= before:
        time.sleep(0.3)
    pRet = captures[-1]
    print(f">>> Return portal captured!", flush=True)

    # === Portal B (different portal!) ===
    before = len(captures)
    print("\n" + "="*60)
    print("  STEP 3: Walk through PORTAL B (DIFFERENT portal!!)")
    print("="*60, flush=True)
    while len(captures) <= before:
        time.sleep(0.3)
    pB = captures[-1]
    print(f">>> Portal B captured!", flush=True)

    # === COMPARE ===
    print(f"\n{'='*60}")
    print(f"  COMPARISON: Portal A vs Portal B")
    print(f"{'='*60}")
    print(f"  Portal A: {pA}")
    print(f"  Portal B: {pB}")
    print(f"  Return:   {pRet}")

    bA = bytes.fromhex(pA)
    bB = bytes.fromhex(pB)
    bRet = bytes.fromhex(pRet)

    # XOR A vs B
    xAB = [bA[i] ^ bB[i] for i in range(29)]
    # XOR A vs Return
    xAR = [bA[i] ^ bRet[i] for i in range(29)]
    # XOR B vs Return
    xBR = [bB[i] ^ bRet[i] for i in range(29)]

    print(f"\n  Byte-by-byte: Portal A ^ Portal B")
    print(f"  {'Pos':>4}  {'A':>4}  {'B':>4}  {'A^B':>4}")
    print(f"  {'---':>4}  {'---':>4}  {'---':>4}  {'----':>4}")

    groups_AB = {}
    for i in range(29):
        v = xAB[i]
        if v not in groups_AB: groups_AB[v] = []
        groups_AB[v].append(i)
        print(f"  {i:3d}  0x{bA[i]:02x}  0x{bB[i]:02x}  0x{v:02x}")

    # Group analysis
    print(f"\n  XOR value groups (A ^ B):")
    for v in sorted(groups_AB.keys()):
        pos = groups_AB[v]
        if len(pos) >= 2:
            rng = f"[{pos[0]}-{pos[-1]}]" if pos == list(range(pos[0], pos[-1]+1)) else str(pos)
        else:
            rng = str(pos)
        print(f"    0x{v:02x} at bytes {rng} ({len(pos)} bytes)")

    # Key insight: find bytes that are SAME between A and B (XOR=0x00)
    same_AB = [i for i in range(29) if xAB[i] == 0]
    diff_AB = [i for i in range(29) if xAB[i] != 0]
    print(f"\n  Same bytes (A=B): {same_AB if same_AB else 'NONE'}")
    print(f"  Different bytes: {diff_AB}")

    # Also compare A vs Return to find portal-pair-specific bytes
    same_AR = [i for i in range(29) if xAR[i] == 0]
    print(f"\n  Same bytes (A=Return): {same_AR if same_AR else 'NONE'}")

    # Check if A vs B XOR pattern is uniform (counter delta) or mixed (data diff)
    unique_xors = set(xAB[1:])  # skip byte 0
    print(f"\n  Unique XOR values in A^B (excluding byte 0): {len(unique_xors)}")
    if len(unique_xors) <= 3:
        print(f"  >>> Mostly uniform! Counter delta dominates.")
        # The uniform XOR values tell us the counter delta between A and B
        for v in sorted(unique_xors):
            cnt = sum(1 for x in xAB[1:] if x == v)
            print(f"    0x{v:02x}: {cnt}/28 bytes")
    else:
        print(f"  >>> MIXED! Different portals have different data at many positions.")
        print(f"  The positions with DIFFERENT XOR values from the majority are DESTINATION bytes!")
        # Find the dominant XOR value
        from collections import Counter
        xor_counts = Counter(xAB[1:])
        dominant = xor_counts.most_common(1)[0]
        print(f"  Dominant XOR: 0x{dominant[0]:02x} ({dominant[1]}/28 bytes) = counter delta")
        outliers = [i for i in range(1, 29) if xAB[i] != dominant[0]]
        print(f"  Outlier positions (candidate DESTINATION): {outliers}")

    session.detach()
    print("\n[*] Done.", flush=True)


if __name__ == '__main__':
    main()
