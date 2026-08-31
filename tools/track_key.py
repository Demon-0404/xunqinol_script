# -*- coding: utf-8 -*-
"""Track send count vs XOR key shift between portal sends."""
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

    portal_captures = []  # list of (send_count, hex, label)
    send_count = [0]  # mutable counter
    last_send_hex = [""]

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error':
            print(f"[!] {msg}", flush=True); return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Frida ready", flush=True)
        elif ptype == 'send_log':
            send_count[0] += 1
            last_send_hex[0] = payload['hex']
        elif ptype == 'portal_captured':
            if payload.get('len') == 29:
                portal_captures.append((send_count[0], payload['hex']))
                n = len(portal_captures)
                print(f"\n>>> [PORTAL #{n}] send#={send_count[0]} hex={payload['hex']}", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_portal_capture()
    print("[*] Monitoring ALL sends + capturing 29B portals", flush=True)

    # Walk 1
    before = len(portal_captures)
    print("\n" + "="*50)
    print(">>> STEP 1: Walk through portal A")
    print("="*50, flush=True)
    while len(portal_captures) <= before:
        time.sleep(0.3)

    # Walk 2 (return)
    before = len(portal_captures)
    print("\n" + "="*50)
    print(">>> STEP 2: Walk through RETURN portal (go back)")
    print("="*50, flush=True)
    while len(portal_captures) <= before:
        time.sleep(0.3)

    # Walk 3 (same portal)
    before = len(portal_captures)
    print("\n" + "="*50)
    print(">>> STEP 3: Walk through portal A AGAIN")
    print("="*50, flush=True)
    while len(portal_captures) <= before:
        time.sleep(0.3)

    # Walk 4 (return)
    before = len(portal_captures)
    print("\n" + "="*50)
    print(">>> STEP 4: Walk through RETURN portal again (optional, press Ctrl+C to skip)")
    print("="*50, flush=True)
    try:
        while len(portal_captures) <= before:
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass

    # Analysis
    print(f"\n{'='*60}")
    print(f"  XOR KEY SHIFT ANALYSIS")
    print(f"{'='*60}")

    for i in range(len(portal_captures)):
        cnt, hexstr = portal_captures[i]
        print(f"  Cap #{i+1}: send#={cnt:4d}  hex={hexstr}")

    # Compare same-portal pairs (A1 vs A2, ret1 vs ret2)
    if len(portal_captures) >= 3:
        cnt1, p1 = portal_captures[0]
        cnt2, p2 = portal_captures[2]
        delta_n = cnt2 - cnt1

        print(f"\n  Portal A #1 vs Portal A #2:")
        print(f"    Sends between: {delta_n}")
        print(f"    Byte-by-byte XOR diff:")
        b1 = bytes.fromhex(p1)
        b2 = bytes.fromhex(p2)
        xors = []
        for j in range(29):
            x = b1[j] ^ b2[j]
            xors.append(x)
        # Group consecutive same XOR values
        groups = []
        cur_val = xors[1]
        cur_start = 1
        for j in range(2, 29):
            if xors[j] != cur_val:
                groups.append((cur_start, j-1, cur_val))
                cur_val = xors[j]
                cur_start = j
        groups.append((cur_start, 28, cur_val))
        for start, end, val in groups:
            rng = f"[{start:2d}-{end:2d}]" if end > start else f"[{start:2d}     ]"
            print(f"      bytes {rng}: XOR=0x{val:02x}")

        if len(portal_captures) >= 4:
            cnt3, p3 = portal_captures[1]
            cnt4, p4 = portal_captures[3]
            delta_ret = cnt4 - cnt3
            print(f"\n  Return portal #1 vs Return #2:")
            print(f"    Sends between: {delta_ret}")
            b3 = bytes.fromhex(p3)
            b4 = bytes.fromhex(p4)
            xors_ret = [b3[j] ^ b4[j] for j in range(29)]
            groups_ret = []
            cur_val = xors_ret[1]
            cur_start = 1
            for j in range(2, 29):
                if xors_ret[j] != cur_val:
                    groups_ret.append((cur_start, j-1, cur_val))
                    cur_val = xors_ret[j]
                    cur_start = j
            groups_ret.append((cur_start, 28, cur_val))
            for start, end, val in groups_ret:
                rng = f"[{start:2d}-{end:2d}]" if end > start else f"[{start:2d}     ]"
                print(f"      bytes {rng}: XOR=0x{val:02x}")

            print(f"\n  >>> KEY INSIGHT:")
            print(f"  >>> Portal A sends between: {delta_n}, Return sends between: {delta_ret}")
            if delta_n == delta_ret:
                print(f"  >>> Send counts EQUAL!")
                # Check if XOR values are same
                if xors[1:] == xors_ret[1:]:
                    print(f"  >>> XOR pattern IDENTICAL! Key = f(send_count)")
                else:
                    print(f"  >>> XOR pattern DIFFERENT! Key depends on something else")
            else:
                print(f"  >>> Send counts DIFFERENT!")
                # See if XOR values correlate
                ratio = delta_n / delta_ret if delta_ret else float('inf')
                print(f"  >>> Ratio: {ratio:.2f}")

    session.detach()
    print("\n[*] Done.", flush=True)

if __name__ == '__main__':
    main()
