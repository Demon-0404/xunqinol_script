# -*- coding: utf-8 -*-
"""Use monitor mode to capture all sends, analyze heartbeat XOR pattern."""
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

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error':
            print(f"[!] {msg}", flush=True); return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Frida ready", flush=True)
        elif ptype == 'monitor':
            all_sends.append({'len': payload['len'], 'hex': payload['hex']})

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    script.exports_sync.start_monitor()
    print("[*] Monitor ON. Stand still for 30s...", flush=True)
    time.sleep(90)
    script.exports_sync.stop_monitor()

    print(f"[*] Total sends: {len(all_sends)}")

    # Group by size
    by_size = {}
    for s in all_sends:
        sz = s['len']
        if sz not in by_size: by_size[sz] = []
        by_size[sz].append(s['hex'])

    print(f"\n--- Packet types ---")
    for sz in sorted(by_size.keys()):
        print(f"  {sz}B: {len(by_size[sz])} packets")

    # Heartbeat analysis
    hbs = by_size.get(17, [])
    if len(hbs) >= 2:
        print(f"\n--- Heartbeat (17B): {len(hbs)} total ---")
        for i in range(min(5, len(hbs))):
            print(f"  HB#{i}: {hbs[i]}")

        print(f"\n  XOR between consecutive HBs:")
        for i in range(min(5, len(hbs)-1)):
            b1 = bytes.fromhex(hbs[i])
            b2 = bytes.fromhex(hbs[i+1])
            xors = [b1[j] ^ b2[j] for j in range(17)]
            xstr = ' '.join(f'{x:02x}' for x in xors)
            print(f"  HB#{i} ^ HB#{i+1}: [{xstr}]")

        # Check byte 0 consistency
        byte0s = [bytes.fromhex(h)[0] for h in hbs]
        if len(set(byte0s)) == 1:
            print(f"\n  >>> Byte 0 always 0x{byte0s[0]:02x} (consistent)")

        # Hypothesis: HB = 01 00 00 00 00 ... (17 zero bytes after type)
        print(f"\n  >>> If HB plain = 01 + 16 zero bytes:")
        for i in range(min(3, len(hbs))):
            b = bytes.fromhex(hbs[i])
            cnt = [b[j] ^ (1 if j==0 else 0) for j in range(17)]
            print(f"  Counter from HB#{i}: {' '.join(f'{c:02x}' for c in cnt)}")

        # Hypothesis: HB = 01 + repeated 4-byte blocks
        print(f"\n  >>> HB byte pattern (looking for repeats):")
        for i in range(min(2, len(hbs))):
            b = bytes.fromhex(hbs[i])
            print(f"  HB#{i}:")
            for off in [0, 1, 5, 9, 13]:
                seg = b[off:off+4].hex() if off+4 <= 17 else b[off:].hex()
                print(f"    [{off:2d}-{min(off+3,16):2d}]: {seg}")

    # Movement analysis
    moves = by_size.get(30, [])
    if len(moves) >= 2:
        print(f"\n--- Movement (30B): {len(moves)} total ---")
        for i in range(min(3, len(moves)-1)):
            b1 = bytes.fromhex(moves[i])
            b2 = bytes.fromhex(moves[i+1])
            xors = [b1[j] ^ b2[j] for j in range(30)]
            groups = []
            cur = xors[1]; start = 1
            for j in range(2, 30):
                if xors[j] != cur:
                    groups.append((start, j-1, cur))
                    cur = xors[j]; start = j
            groups.append((start, 29, cur))
            gstr = ' | '.join(f'[{s:2d}-{e:2d}]=0x{v:02x}' for s,e,v in groups if v != 0)
            print(f"  Move#{i} ^ Move#{i+1}: {gstr}")

    session.detach()
    print("\n[*] Done.", flush=True)

if __name__ == '__main__':
    main()
