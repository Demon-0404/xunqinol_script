# -*- coding: utf-8 -*-
"""Test recv injection WITHOUT silence mode - let all sends flow freely."""
import sys, time, os, json, subprocess

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
    # Load map
    if not os.path.exists(MAP_DB):
        print("[!] No maps"); return
    maps = json.load(open(MAP_DB))
    name = sys.argv[1] if len(sys.argv) > 1 else 'to_handan'
    if name not in maps:
        print(f"[!] Not found: {list(maps.keys())}"); return

    session, js_code, pid = connect()
    plain = maps[name]['plain_hex']
    print(f"[*] Map '{name}' ({len(plain)//2}B)", flush=True)

    inject_done = [False]
    disconnect = [False]
    start_time = time.time()

    def on_msg(msg, data):
        payload = msg.get('payload', {})
        if msg.get('type') == 'error':
            print(f"[!] {msg}", flush=True); return
        if not isinstance(payload, dict): return
        ptype = payload.get('t', '?')
        if ptype == 'ready':
            print("[*] Connected", flush=True)
        elif ptype == 'key':
            print(f"[*] Key: 0x{payload['key']:02x} — NOW walking through portal...", flush=True)
        elif ptype == 'inj_armed':
            print(f"[*] {payload['msg']}", flush=True)
        elif ptype == 'inj_log':
            print(f"[>] recv={payload['len']}B remain={payload['remain']}B", flush=True)
        elif ptype == 'inj_chunk':
            print(f"[>] Wrote {payload['wrote']}B ({payload['offset']}/{payload['total']})", flush=True)
        elif ptype == 'inj_done':
            inject_done[0] = True
            elapsed = time.time() - start_time
            print(f"[***] INJECTION DONE (NO SILENCE)! elapsed={elapsed:.1f}s", flush=True)
            print(f"[***] {payload['msg']}", flush=True)
            print(f"[***] Sends flowing freely — watch for disconnect!", flush=True)
        elif ptype == 'inj_wait':
            pass  # suppress gate-skip messages
        elif ptype == 'portal_captured':
            print(f"[*] PORTAL: {payload['hex']}", flush=True)
        elif ptype == 'close_blocked':
            disconnect[0] = True
            elapsed = time.time() - start_time
            print(f"[!!!] CLOSE BLOCKED at {elapsed:.1f}s (fd={payload['fd']} #{payload['total']})", flush=True)
        elif ptype == 'shutdown_blocked':
            disconnect[0] = True
            elapsed = time.time() - start_time
            print(f"[!!!] SHUTDOWN BLOCKED at {elapsed:.1f}s", flush=True)
        elif ptype == 'recv_zero_blocked':
            disconnect[0] = True
            elapsed = time.time() - start_time
            print(f"[!!!] RECV ZERO at {elapsed:.1f}s (server FIN)", flush=True)
        elif ptype == 'recv_err':
            disconnect[0] = True
            elapsed = time.time() - start_time
            print(f"[!!!] RECV ERR at {elapsed:.1f}s", flush=True)
        elif ptype == 'silence_recv':
            print(f"[RECV] {payload['len']}B: {payload['hex'][:40]}", flush=True)
        elif ptype == 'send_log':
            print(f"[SEND] {payload['len']}B", flush=True)

    import frida
    script = session.create_script(js_code)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)

    print(f"\n{'='*60}")
    print(f"  NO-SILENCE INJECTION TEST: '{name}'")
    print(f"  Walk through ANY portal NOW!")
    print(f"  After injection, sends will flow freely — no blocking.")
    print(f"  Watch if game stays connected or disconnects.")
    print(f"{'='*60}\n", flush=True)

    result = script.exports_sync.inject_no_silence(plain)
    print(f"[*] {result}", flush=True)

    # Wait up to 120s
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(0.5)
            if inject_done[0]:
                elapsed = time.time() - start_time
                if not disconnect[0]:
                    # Periodically report status
                    if int(elapsed) % 10 == 0:
                        print(f"[*] Still connected... {elapsed:.0f}s since start", flush=True)
    except KeyboardInterrupt:
        pass

    elapsed = time.time() - start_time
    if disconnect[0]:
        print(f"\n[!!!] DISCONNECTED after {elapsed:.1f}s", flush=True)
    elif inject_done[0]:
        print(f"\n[***] STILL CONNECTED after {elapsed:.1f}s!", flush=True)
        print(f"[***] NO-SILENCE approach might work! Can you move around?", flush=True)
    else:
        print(f"\n[!] Injection never completed within {elapsed:.1f}s", flush=True)

    stats = script.exports_sync.get_stats()
    print(f"[*] Stats: {stats}", flush=True)
    session.detach()

if __name__ == '__main__':
    main()
