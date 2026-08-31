# -*- coding: utf-8 -*-
"""Teleport system v5 — recv stream injection
"""
import sys, time, subprocess, os, json

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAP_DB = os.path.join(SCRIPT_DIR, '..', 'map_data', 'maps.json')

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
                                # Skip ADB/local connections (127.0.0.1, 10.0.2.2)
                                remote = parts[2]
                                if "0100007F" in remote or "0202000A" in remote: continue
                                if fd > 2 and fd not in game_fds:
                                    game_fds.append(fd)
                                    print(f"[*] Game fd: {fd} remote={remote}", flush=True)
                            except: pass

    if not game_fds: raise Exception("No game sockets found")

    subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"], capture_output=True, timeout=10)

    with open(os.path.join(SCRIPT_DIR, 'teleport_v2.js'), 'r', encoding='utf-8') as f:
        JS = f.read().replace('GAME_FDS_PLACEHOLDER', json.dumps(game_fds))

    import frida
    dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
    session = dev.attach(pid)

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error': print(f"[!] {msg}", flush=True); return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready': print("[*] Connected", flush=True)
        elif ptype == 'key':
            print(f"[*] Key: 0x{payload['key']:02x} — NOW walk through portal!", flush=True)
            global _key_notified
            _key_notified = True
        elif ptype == 'capture_done': print(f"[*] Captured {payload['len']}B", flush=True)
        elif ptype == 'send_log': print(f"[SEND fd={payload.get('fd','?')}] {payload['len']}B: {payload['hex'][:40]}", flush=True)
        elif ptype == 'inj_armed': print(f"[*] {payload['msg']}", flush=True)
        elif ptype == 'inj_log': print(f"[>] recv={payload['len']}B remain={payload['remain']}B", flush=True)
        elif ptype == 'inj_chunk': print(f"[>] Wrote {payload['wrote']}B ({payload['offset']}/{payload['total']}) real={payload['real']}B", flush=True)
        elif ptype == 'inj_done': print(f"[*] {payload['msg']}", flush=True)
        elif ptype == 'monitor': print(f"[MON] len={payload['len']} {payload['hex']}", flush=True)
        elif ptype == 'hb_queued': print(f"[*] {payload['msg']}", flush=True)
        elif ptype == 'fake_recv': print(f"[*] {payload['msg']} ({payload['len']}B)", flush=True)
        elif ptype == 'portal_redirect': print(f"[!!!] {payload['msg']}", flush=True)
        elif ptype == 'alive':
            if payload['since_recv'] > 5000:
                print(f"[!!!] NO RECV FOR {payload['since_recv']}ms! silence_left={payload['silence_left']}ms", flush=True)
        elif ptype == 'recv_filter': print(f"[FILTER] {payload['msg']}", flush=True)
        elif ptype == 'inj_wait': pass  # suppress verbose gate-skip messages
        elif ptype == 'portal_captured': print(f"[*] PORTAL SEND: {payload['hex']}", flush=True)
        elif ptype == 'silence_off': print(f"[*] {payload['msg']}", flush=True)
        elif ptype == 'close_blocked': print(f"[!!!] CLOSE BLOCKED fd={payload['fd']} (#{payload['total']})\n  {payload.get('stack','')}", flush=True)
        elif ptype == 'shutdown_blocked': print(f"[!!!] SHUTDOWN BLOCKED fd={payload['fd']} how={payload['how']} (#{payload['total']})\n  {payload.get('stack','')}", flush=True)
        elif ptype == 'silence_recv': print(f"[RECV fd={payload.get('fd','?')}] {payload['len']}B: {payload['hex']}", flush=True)
        elif ptype == 'recv_zero_blocked': print(f"[!!!] {payload['msg']} fd={payload.get('fd','?')}", flush=True)
        elif ptype == 'recv_err': print(f"[!!!] RECV ERR fd={payload.get('fd','?')}: {payload['len']} {payload['msg']}", flush=True)

    script = session.create_script(JS)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)
    return session, script

def cmd_record(name):
    session, script = connect()
    print(f"[*] Recording: {name}", flush=True)
    print("[*] Walk through portal! 20s...", flush=True)
    script.exports_sync.start_capture()
    time.sleep(20)
    plain = script.exports_sync.stop_capture()
    if not plain or len(plain) < 100:
        print(f"[!] Failed: {len(plain)//2 if plain else 0}B", flush=True)
        session.detach(); return

    os.makedirs(os.path.dirname(MAP_DB), exist_ok=True)
    maps = json.load(open(MAP_DB)) if os.path.exists(MAP_DB) else {}
    maps[name] = {'plain_hex': plain, 'size': len(plain)//2}
    json.dump(maps, open(MAP_DB, 'w'), indent=2)
    print(f"[*] '{name}' saved ({len(plain)//2}B)", flush=True)
    session.detach()

def cmd_go(name):
    if not os.path.exists(MAP_DB): print("[!] No maps"); return
    maps = json.load(open(MAP_DB))
    if name not in maps: print(f"[!] Not found: {list(maps.keys())}"); return

    session, script = connect()
    plain = maps[name]['plain_hex']
    print(f"[*] Armed '{name}' ({len(plain)//2}B) — walk through ANY portal!", flush=True)
    result = script.exports_sync.inject(plain)
    print(f"[*] {result}", flush=True)
    try:
        time.sleep(360)
    except KeyboardInterrupt:
        pass
    stats = script.exports_sync.get_stats()
    print(f"[*] Stats: {stats}", flush=True)
    print("[*] Done.", flush=True)
    session.detach()

def cmd_list():
    if not os.path.exists(MAP_DB): print("[*] No maps"); return
    maps = json.load(open(MAP_DB))
    print(f"[*] {len(maps)} maps:", flush=True)
    for n, i in maps.items(): print(f"  - {n} ({i['size']}B)", flush=True)

def cmd_go_filter(name):
    """RECV filter mode: inject map data, then block incompatible server recv while
    letting client sends flow freely. Keeps connection alive with fake heartbeats."""
    if not os.path.exists(MAP_DB): print("[!] No maps"); return
    maps = json.load(open(MAP_DB))
    if name not in maps: print(f"[!] Not found: {list(maps.keys())}"); return

    session, script = connect()
    plain = maps[name]['plain_hex']
    print(f"[*] RECV FILTER mode: '{name}' ({len(plain)//2}B)", flush=True)
    print("[*] Client sends OK, server recv will be filtered.", flush=True)
    print("[*] Walk through ANY portal!", flush=True)
    result = script.exports_sync.inject_recv_filter(plain)
    print(f"[*] {result}", flush=True)
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    stats = script.exports_sync.disable_silence()
    print(f"[*] Disabled: {stats}", flush=True)
    session.detach()

def cmd_go_portal(name):
    if not os.path.exists(MAP_DB): print("[!] No maps"); return
    maps = json.load(open(MAP_DB))
    if name not in maps: print(f"[!] Not found: {list(maps.keys())}"); return
    if 'portal_plain' not in maps[name]: print(f"[!] No portal_plain for {name}"); return

    session, script = connect()
    portal_plain = maps[name]['portal_plain']
    print(f"[*] Portal redirect armed '{name}' ({len(portal_plain)//2}B) — walk through ANY portal!", flush=True)
    result = script.exports_sync.arm_portal_redirect(portal_plain)
    print(f"[*] {result}", flush=True)
    time.sleep(90)
    print("[*] Done.", flush=True)
    session.detach()

def cmd_monitor():
    session, script = connect()
    result = script.exports_sync.start_monitor()
    print(f"[*] {result} — logging ALL sends. Ctrl+C to stop.", flush=True)
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        script.exports_sync.stop_monitor()
        print("[*] Monitor stopped.", flush=True)
        session.detach()

def cmd_portal_plain():
    session, script = connect()
    print("[*] Portal capture armed. Send packets are PLAINTEXT — use 'enc' field.")
    print("[*] Step 1: walk through a portal NOW!")
    print("[*] Step 2: walk back, then through SAME portal again!")
    print("[*] (waiting 180s...)", flush=True)
    script.exports_sync.start_portal_capture()
    time.sleep(180)
    result = script.exports_sync.stop_portal_capture_plain()
    try:
        packets = json.loads(result)
        if packets:
            # Filter to only 29B portal packets
            portals = [p for p in packets if len(p['enc']) // 2 == 29]
            print(f"[*] Captured {len(portals)} x 29B portal(s):", flush=True)
            for i, p in enumerate(portals):
                print(f"\n  --- Portal #{i+1} ---", flush=True)
                print(f"  enc (real plaintext): {p['enc']}", flush=True)
                bytes_str = ' '.join(p['enc'][j:j+2] for j in range(0, len(p['enc']), 2))
                print(f"  bytes: {bytes_str}", flush=True)

            if len(portals) >= 2:
                print(f"\n{'='*60}")
                print(f"  BYTE-BY-BYTE COMPARISON: Portal #1 vs Portal #2")
                print(f"{'='*60}")
                b1 = bytes.fromhex(portals[0]['enc'])
                b2 = bytes.fromhex(portals[1]['enc'])
                print(f"{'Pos':>4}  {'#1':>4}  {'#2':>4}  Status")
                print(f"{'---':>4}  {'---':>4}  {'---':>4}  ------")
                same = 0; diff = 0; diff_pos = []
                for i in range(max(len(b1), len(b2))):
                    v1 = b1[i] if i < len(b1) else None
                    v2 = b2[i] if i < len(b2) else None
                    if v1 == v2:
                        same += 1; s = "SAME"
                    else:
                        diff += 1; s = "DIFF <<<"; diff_pos.append(i)
                    print(f"  {i:3d}  {f'0x{v1:02x}' if v1 else 'N/A':>4}  {f'0x{v2:02x}' if v2 else 'N/A':>4}  {s}")
                print(f"\n  Same: {same}, Diff: {diff}")
                if diff_pos:
                    print(f"  Diff positions: {diff_pos}")
                    print(f"  => These {diff} byte positions are DYNAMIC (seq/timestamp/checksum)")
                    same_pos = [i for i in range(29) if i not in diff_pos]
                    print(f"  => These {len(same_pos)} positions are STATIC (candidate destination bytes): {same_pos}")
        else:
            print("[!] No portal send detected", flush=True)
    except Exception as e:
        print(f"[!] Error: {e} | {result}", flush=True)
    session.detach()

def cmd_portal_send():
    session, script = connect()
    print("[*] Walk through a portal NOW! (waiting 15s...)", flush=True)
    script.exports_sync.start_portal_capture()
    time.sleep(20)
    result = script.exports_sync.stop_portal_capture()
    try:
        packets = json.loads(result)
        if packets:
            print(f"[*] Captured {len(packets)} portal candidate(s):", flush=True)
            for i, p in enumerate(packets):
                print(f"  [{i}] len={len(p)//2} {p}", flush=True)
        else:
            print("[!] No portal send detected", flush=True)
    except:
        print(f"[!] Error parsing: {result}", flush=True)
    session.detach()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: teleport.py [record <name> | go <name> | go_filter <name> | list | monitor | portal]"); sys.exit(1)
    {'portal_plain': cmd_portal_plain,
     'record': lambda: cmd_record(sys.argv[2]) if len(sys.argv)>2 else print("Need name"),
     'go': lambda: cmd_go(sys.argv[2]) if len(sys.argv)>2 else print("Need name"),
     'go_filter': lambda: cmd_go_filter(sys.argv[2]) if len(sys.argv)>2 else print("Need name"),
     'go_portal': lambda: cmd_go_portal(sys.argv[2]) if len(sys.argv)>2 else print("Need name"),
     'list': cmd_list,
     'monitor': cmd_monitor,
     'portal': cmd_portal_send}.get(sys.argv[1], lambda: print(f"Unknown: {sys.argv[1]}"))()
