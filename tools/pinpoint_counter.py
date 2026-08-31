# -*- coding: utf-8 -*-
"""Pinpoint: capture HB1 -> portal -> HB2 sequence, solve counter increment."""
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
    all_sends = []
    hb_seq = []
    portal_seq = []
    move_seq = []

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error': return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Ready", flush=True)
        elif ptype == 'monitor':
            idx = len(all_sends)
            entry = {'idx': idx, 'len': payload['len'], 'hex': payload['hex']}
            all_sends.append(entry)
            if payload['len'] == 17:
                hb_seq.append(entry)
                print(f"  [HB#{len(hb_seq)} at send#{idx}]", flush=True)
            elif payload['len'] == 30:
                move_seq.append(entry)
        elif ptype == 'portal_captured':
            if payload.get('len') == 29:
                idx = len(all_sends)
                entry = {'idx': idx, 'len': 29, 'hex': payload['hex'], 'portal': True}
                all_sends.append(entry)
                portal_seq.append(entry)
                print(f"\n>>> [PORTAL at send#{idx}]", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_monitor()
    script.exports_sync.start_portal_capture()

    # Step 1: wait for first HB
    print("\n[Phase 1] Waiting for baseline heartbeat...", flush=True)
    while len(hb_seq) < 1:
        time.sleep(0.3)
    hb1 = hb_seq[-1]
    print(f"  Got HB#1 at send#{hb1['idx']}", flush=True)

    # Step 2: walk through portal
    print("\n" + "="*60)
    print("  >>> NOW: Walk through a portal!")
    print("="*60, flush=True)
    while len(portal_seq) < 1:
        time.sleep(0.3)
    portal = portal_seq[-1]
    print(f"  Portal at send#{portal['idx']}", flush=True)

    # Step 3: wait for next HB
    print("\n[Phase 3] Waiting for heartbeat after portal...", flush=True)
    target = len(hb_seq) + 1
    deadline = time.time() + 90
    while len(hb_seq) < target and time.time() < deadline:
        time.sleep(0.3)

    if len(hb_seq) >= 2:
        hb2 = hb_seq[-1]
        print(f"  Got HB#2 at send#{hb2['idx']}", flush=True)
    else:
        print("[!] No second HB within 90s", flush=True)
        hb2 = None

    script.exports_sync.stop_monitor()

    # === SOLVE COUNTER ===
    print(f"\n{'='*60}")
    print(f"  COUNTER SOLVER")
    print(f"{'='*60}")

    hb1_hex = hb1['hex']
    b1 = bytes.fromhex(hb1_hex)
    hb1_counter = b1[1]  # byte 1 of HB = counter for all data bytes

    sends_hb1_to_portal = portal['idx'] - hb1['idx']

    print(f"  HB#1 at send#{hb1['idx']}, counter = 0x{hb1_counter:02x}")
    print(f"  Portal at send#{portal['idx']}, {sends_hb1_to_portal} sends after HB#1")
    print(f"  Portal raw: {portal['hex']}")

    if hb2:
        hb2_hex = hb2['hex']
        b2 = bytes.fromhex(hb2_hex)
        hb2_counter = b2[1]
        sends_hb1_to_hb2 = hb2['idx'] - hb1['idx']
        sends_portal_to_hb2 = hb2['idx'] - portal['idx']
        hb_xor = hb1_counter ^ hb2_counter

        print(f"  HB#2 at send#{hb2['idx']}, counter = 0x{hb2_counter:02x}")
        print(f"  HB#1->HB#2: {sends_hb1_to_hb2} sends, XOR = 0x{hb_xor:02x}")
        print(f"  Portal->HB#2: {sends_portal_to_hb2} sends")

        # Brute force: try all possible counter increments per send (1-30)
        print(f"\n  --- Testing counter increment k (1-30) ---")
        print(f"  For each k: does C XOR (C + k*{sends_hb1_to_hb2}) = 0x{hb_xor:02x}?")

        print(f"\n  {'k':>4}  {'delta':>6}  {'C XOR (C+delta)':>15}  {'match?':>8}  {'counter at portal':>18}  {'portal decrypted (first 16B)'}")
        print(f"  {'-'*4}  {'-'*6}  {'-'*15}  {'-'*8}  {'-'*18}  {'-'*40}")

        pb = bytes.fromhex(portal['hex'])

        for k in range(1, 31):
            delta = sends_hb1_to_hb2 * k
            # Check: does there exist C such that C XOR (C+delta mod 256) = hb_xor?
            solutions = []
            for c in range(256):
                if (c ^ ((c + delta) & 0xFF)) == hb_xor:
                    solutions.append(c)
            match = len(solutions) > 0

            if match:
                # With HB#1 counter = the actual c, does c match one of the solutions?
                if hb1_counter in solutions:
                    c_at_portal = (hb1_counter + sends_hb1_to_portal * k) & 0xFF
                    dec = bytes([pb[0]] + [pb[j] ^ c_at_portal for j in range(1, 29)])
                    dec_hex = dec.hex()
                    print(f"  {k:4d}  {delta:6d}  YES ({len(solutions):3d} sol)  {'MATCH!':>8}  0x{c_at_portal:02x}              {dec_hex[:40]}")
                else:
                    c_at_portal = (hb1_counter + sends_hb1_to_portal * k) & 0xFF
                    dec = bytes([pb[0]] + [pb[j] ^ c_at_portal for j in range(1, 29)])
                    dec_hex = dec.hex()
                    # Check if decrypted has structure (repeating bytes)
                    has_struct = False
                    for seg_start in [1, 5, 9, 13, 17, 21, 25]:
                        if seg_start + 4 <= 29:
                            seg = dec[seg_start:seg_start+4]
                            if len(set(seg)) <= 2:
                                has_struct = True; break
                    tag = "<<< STRUCT" if has_struct else ""
                    if has_struct:
                        print(f"  {k:4d}  {delta:6d}  YES ({len(solutions):3d} sol)  NO      0x{c_at_portal:02x}              {dec_hex[:40]}  {tag}")
            # else: skip non-matching k (don't print)
    else:
        print(f"\n  [!] No second HB. Analyzing with single HB...")
        # Try different k values directly
        pb = bytes.fromhex(portal['hex'])
        print(f"\n  Trying various k values (HB counter=0x{hb1_counter:02x}, {sends_hb1_to_portal} sends):")
        for k in range(1, 21):
            c_at_portal = (hb1_counter + sends_hb1_to_portal * k) & 0xFF
            dec = bytes([pb[0]] + [pb[j] ^ c_at_portal for j in range(1, 29)])
            print(f"    k={k:2d} counter=0x{c_at_portal:02x}: {dec.hex()}")

    # Also show portal #9=#10 duplicate analysis
    print(f"\n  --- Movement byte structure (30B) ---")
    if len(move_seq) >= 2:
        m1 = bytes.fromhex(move_seq[0]['hex'])
        m2 = bytes.fromhex(move_seq[-1]['hex'])
        xors = [m1[j] ^ m2[j] for j in range(30)]
        groups = {}
        for j in range(1, 30):
            v = xors[j]
            if v not in groups: groups[v] = []
            groups[v].append(j)
        print(f"  First move: {move_seq[0]['hex'][:30]}...")
        print(f"  Last  move: {move_seq[-1]['hex'][:30]}...")
        print(f"  XOR byte groups:")
        for v, positions in sorted(groups.items()):
            if len(positions) >= 2:
                pstr = f"[{positions[0]}-{positions[-1]}]" if positions == list(range(positions[0], positions[-1]+1)) else str(positions[:5])
                print(f"    0x{v:02x} at bytes {pstr} ({len(positions)} bytes)")

    session.detach()
    print("\n[*] Done.", flush=True)


if __name__ == '__main__':
    main()
