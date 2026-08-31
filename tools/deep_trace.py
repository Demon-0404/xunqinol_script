# -*- coding: utf-8 -*-
"""Deep trace: capture ALL sends, track counter across ALL game sockets."""
import sys, time, os, json, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def find_all_game_fds(pid):
    """Find ALL game sockets (not just one)"""
    all_fds = []
    r = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls /proc/{pid}/fd/"], capture_output=True, text=True, timeout=10)
    for line in r.stdout.split("\n"):
        line = line.strip()
        if not line: continue
        try:
            fd = int(line)
            if fd <= 2: continue
            r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/{fd}"], capture_output=True, text=True, timeout=5)
            if "socket" in r2.stdout:
                all_fds.append(fd)
        except: pass
    return all_fds

def connect():
    subprocess.run([ADB, "-s", SERIAL, "root"], capture_output=True, timeout=10)
    r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"], capture_output=True, text=True, timeout=15)
    pid = None
    for line in r.stdout.split("\n"):
        if "proj.xqj" in line:
            parts = line.split()
            if len(parts) >= 2: pid = int(parts[1]); break
    if not pid: raise Exception("Game not found")

    # Find ALL game FDs
    all_fds = find_all_game_fds(pid)
    print(f"[*] Found {len(all_fds)} sockets: {all_fds}", flush=True)

    # Find the game TCP socket (connected to game server, not localhost)
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
                                    print(f"[*] Game TCP fd: {fd} remote={remote}", flush=True)
                            except: pass

    if not game_fds: raise Exception("No game sockets found")
    subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

    # Build JS that hooks ALL game FDs and tracks ALL sockets
    js_template = open(os.path.join(SCRIPT_DIR, 'teleport_v2.js'), 'r', encoding='utf-8').read()

    import frida
    dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
    session = dev.attach(pid)
    return session, js_template.replace('GAME_FDS_PLACEHOLDER', json.dumps(game_fds)), pid, game_fds


def main():
    session, js_code, pid, game_fds = connect()

    all_sends = []

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error':
            return  # suppress errors
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Ready", flush=True)
        elif ptype == 'monitor':
            all_sends.append({'len': payload['len'], 'hex': payload['hex']})
        elif ptype == 'portal_captured':
            if payload.get('len') == 29:
                all_sends.append({'len': 29, 'hex': payload['hex'], 'portal': True})
                print(f"\n>>> PORTAL captured!", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_monitor()
    script.exports_sync.start_portal_capture()

    print("\n" + "="*60)
    print("  STEP 1: Walk around freely for ~30 seconds")
    print("  (generates movement / heartbeat packets for analysis)")
    print("="*60, flush=True)
    time.sleep(30)
    print("\n" + "="*60)
    print("  STEP 2: NOW walk through a portal!")
    print("  (must change map)")
    print("="*60, flush=True)
    time.sleep(30)

    script.exports_sync.stop_monitor()

    print(f"\n[*] Total sends: {len(all_sends)}")

    if len(all_sends) < 2:
        print("[!] Not enough data")
        session.detach()
        return

    # === ANALYSIS ===
    # Group by type
    types = {}
    for i, s in enumerate(all_sends):
        sz = s['len']
        if sz not in types: types[sz] = []
        types[sz].append((i, s['hex']))

    print(f"\n--- Packets by type ---")
    for sz in sorted(types.keys()):
        print(f"  {sz}B: {len(types[sz])} packets")

    # For each type, compute XOR between consecutive packets
    print(f"\n--- XOR between consecutive packets (same type) ---")
    for sz in sorted(types.keys()):
        entries = types[sz]
        if len(entries) < 2: continue
        print(f"\n  [{sz}B packets]")
        xor_values = []
        for k in range(len(entries)-1):
            idx1, h1 = entries[k]
            idx2, h2 = entries[k+1]
            b1 = bytes.fromhex(h1)
            b2 = bytes.fromhex(h2)
            xors = [b1[j] ^ b2[j] for j in range(min(len(b1), len(b2)))]
            num_sends = idx2 - idx1
            # Check if XOR is uniform across bytes 1+
            unique_xors = set(xors[1:])  # skip type byte
            if len(unique_xors) == 1:
                xv = list(unique_xors)[0]
                xor_values.append((num_sends, xv))
                print(f"    #{idx1}->#{idx2} ({num_sends:2d} sends): UNIFORM XOR=0x{xv:02x}")
            else:
                # Group by value
                groups = {}
                for j in range(1, len(xors)):
                    v = xors[j]
                    if v not in groups: groups[v] = []
                    groups[v].append(j)
                gstr = ' | '.join(f'0x{k:02x} at {v}' for k,v in groups.items())
                print(f"    #{idx1}->#{idx2} ({num_sends:2d} sends): MIXED {gstr}")

        if xor_values:
            # Analyze relationship between num_sends and XOR
            print(f"    >>> sends vs XOR: ", end='')
            for ns, xv in xor_values:
                print(f"{ns}→0x{xv:02x} ", end='')
            print()

    # Regression: compute counter increment per send
    print(f"\n--- Counter increment analysis ---")
    hb_entries = types.get(17, [])
    if len(hb_entries) >= 2:
        print(f"  Using heartbeat pairs:")
        for k in range(len(hb_entries)-1):
            idx1, h1 = hb_entries[k]
            idx2, h2 = hb_entries[k+1]
            b1 = bytes.fromhex(h1)
            b2 = bytes.fromhex(h2)
            xv = b1[1] ^ b2[1]
            ns = idx2 - idx1
            print(f"    HB send#{idx1}->send#{idx2}: {ns} sends, XOR=0x{xv:02x}")
            # If counter = c0 + k * ns, then (c0 XOR (c0 + k*ns)) = xv
            # For various possible c0 values:
            solutions = []
            for c0 in range(256):
                if c0 ^ ((c0 + ns) & 0xFF) == xv:
                    solutions.append(c0)
            print(f"      Possible counter values: {len(solutions)}/256 -> {solutions[:10]}")

    # Portal analysis
    portal_entries = types.get(29, [])
    if portal_entries:
        print(f"\n--- Portal decryption attempt ---")
        pidx, phex = portal_entries[0]
        print(f"  Portal at send#{pidx}: {phex}")
        # Try to decrypt with nearest HB counter
        for k in range(len(hb_entries)-1):
            idx1, h1 = hb_entries[k]
            idx2, h2 = hb_entries[k+1]
            if idx1 < pidx < idx2:
                b1 = bytes.fromhex(h1)
                c_hb = b1[1]
                sends_dist = pidx - idx1
                # Try counter = c_hb + sends_dist
                c_try = (c_hb + sends_dist) & 0xFF
                pb = bytes.fromhex(phex)
                dec = bytes([pb[0]] + [pb[j] ^ c_try for j in range(1, 29)])
                print(f"    HB before at send#{idx1}, counter=0x{c_hb:02x}")
                print(f"    Portal at send#{pidx} ({sends_dist} sends after)")
                print(f"    Try counter=0x{c_try:02x}: {dec.hex()}")
                # Also try various increments
                for inc in [1, 2, 3, 5, 7, 11, 17]:
                    c_try = (c_hb + sends_dist * inc) & 0xFF
                    dec = bytes([pb[0]] + [pb[j] ^ c_try for j in range(1, 29)])
                    # Check if decrypted looks structured (repeating patterns)
                    has_repeat = len(set(dec[1:5])) < 4 or len(set(dec[10:14])) < 4
                    if has_repeat:
                        print(f"    inc*{inc} counter=0x{c_try:02x}: {dec.hex()}  <<< STRUCTURE!")

    session.detach()
    print("\n[*] Done.", flush=True)

if __name__ == '__main__':
    main()
