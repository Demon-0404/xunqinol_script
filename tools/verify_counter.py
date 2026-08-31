# -*- coding: utf-8 -*-
"""Capture HB + portal + HB sequence with clear walk prompts."""
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
    timeline = []
    hb_count = [0]
    portal_count = [0]

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error':
            print(f"[!] {msg}", flush=True); return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Frida ready", flush=True)
        elif ptype == 'monitor':
            idx = len(timeline)
            entry = {'len': payload['len'], 'hex': payload['hex'], 'idx': idx}
            timeline.append(entry)
            if payload['len'] == 17:
                hb_count[0] += 1
                print(f"  [HB#{hb_count[0]} at send#{idx}]", flush=True)
        elif ptype == 'portal_captured':
            if payload.get('len') == 29:
                idx = len(timeline)
                portal_count[0] += 1
                timeline.append({'len': 29, 'hex': payload['hex'], 'idx': idx, 'portal': True})
                print(f"\n>>> [PORTAL at send#{idx}] captured!", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_monitor()
    script.exports_sync.start_portal_capture()

    # Phase 1: wait for first heartbeat as baseline
    print("[*] Phase 1: waiting for baseline heartbeat...", flush=True)
    while hb_count[0] < 1:
        time.sleep(0.3)
    print("[*] Baseline HB captured!", flush=True)

    # Phase 2: walk through portal
    print("\n" + "="*60)
    print(">>> NOW: Walk through a portal!")
    print("="*60, flush=True)
    while portal_count[0] < 1:
        time.sleep(0.3)

    # Phase 3: wait for a heartbeat after portal
    print("\n[*] Phase 3: waiting for heartbeat after portal...", flush=True)
    target_hb = hb_count[0] + 1
    deadline = time.time() + 60
    while hb_count[0] < target_hb and time.time() < deadline:
        time.sleep(0.3)

    script.exports_sync.stop_monitor()

    # === ANALYSIS ===
    print(f"\n{'='*60}")
    print(f"  ANALYSIS")
    print(f"{'='*60}")
    print(f"  Total sends: {len(timeline)}")

    hbs = [t for t in timeline if t['len'] == 17]
    portals = [t for t in timeline if t.get('portal')]
    moves = [t for t in timeline if t['len'] == 30]

    print(f"  Heartbeats: {len(hbs)}")
    print(f"  Portals: {len(portals)}")
    print(f"  Movements: {len(moves)}")

    # Show all heartbeats with their positions
    print(f"\n--- Timeline ---")
    for hb in hbs:
        is_before = hb['idx'] < portals[0]['idx'] if portals else False
        label = "BEFORE portal" if is_before else "AFTER portal"
        print(f"  send#{hb['idx']:3d} [HB] {label}  {hb['hex']}")
    for p in portals:
        print(f"  send#{p['idx']:3d} [PORTAL]       {p['hex']}")

    # Extract counter from heartbeat before portal
    if hbs and portals:
        # Find the closest HB before the portal
        portal_idx = portals[0]['idx']
        hbs_before = [hb for hb in hbs if hb['idx'] < portal_idx]
        hbs_after = [hb for hb in hbs if hb['idx'] > portal_idx]

        if hbs_before:
            hb_before = hbs_before[-1]
            b = bytes.fromhex(hb_before['hex'])
            counter_hb = b[1]  # Single byte counter (byte 1 of HB = counter)
            sends_to_portal = portal_idx - hb_before['idx']
            counter_portal = (counter_hb + sends_to_portal) & 0xFF
            print(f"\n--- Counter prediction ---")
            print(f"  HB before portal at send#{hb_before['idx']}")
            print(f"  HB hex: {hb_before['hex']}")
            print(f"  Counter from HB (byte 1): 0x{counter_hb:02x}")
            print(f"  Sends from HB to portal: {sends_to_portal}")
            print(f"  Predicted counter at portal: 0x{counter_portal:02x}")

            # Decrypt portal with predicted counter
            p_hex = portals[0]['hex']
            p_bytes = bytes.fromhex(p_hex)
            decrypted = bytes([p_bytes[j] ^ counter_portal for j in range(1, 29)])
            print(f"\n  Portal raw: {p_hex}")
            print(f"  Decrypted (bytes 1-28 XOR counter):")
            print(f"  {' '.join(f'{b:02x}' for b in decrypted)}")
            print(f"  Decrypted byte 0 kept as is (0x03)")

            # Check if decrypted has recognizable structure
            dec_full = bytes([0x03]) + decrypted
            print(f"  Full decrypted: {dec_full.hex()}")

            if hbs_after:
                hb_after = hbs_after[0]
                b2 = bytes.fromhex(hb_after['hex'])
                counter_hb_after = b2[1]
                sends_after = hb_after['idx'] - portal_idx
                print(f"\n  HB after portal at send#{hb_after['idx']}")
                print(f"  Counter from HB after: 0x{counter_hb_after:02x}")
                print(f"  Sends from portal to HB: {sends_after}")
                # Verify: counter_hb_after should ≈ counter_portal + sends_after
                expected = (counter_portal + sends_after) & 0xFF
                actual_xor = counter_portal ^ counter_hb_after
                print(f"  Expected counter after: 0x{expected:02x}")

    session.detach()
    print("\n[*] Done.", flush=True)

if __name__ == '__main__':
    main()
