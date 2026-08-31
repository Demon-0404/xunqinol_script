"""Portal packet comparison runner — capture multiple portal packets and compare them"""
import frida, sys, json, time

CAPTURES = []

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict):
        return
    t = p.get("t", "?")

    if t == "ready":
        print(f"[READY] {p.get('msg', '')}")
    elif t == "fd_found":
        print(f"[FD] Game socket fd={p['fd']} -> {p.get('ip','?')}:{p.get('port','?')}")
    elif t == "key_found":
        print(f"[KEY] XOR key = 0x{p['key']:02x} ({p.get('side','send')})")
    elif t == "captured":
        CAPTURES.append({"label": p["label"], "plain": p["plain"]})
        print(f"\n{'='*60}")
        print(f"[CAPTURE #{p['count']}] Label: {p['label']}")
        print(f"Plain ({len(p['plain'])/2:.0f}B): {p['plain']}")
    elif t == "breakdown":
        print(f"Bytes: {p['detail']}")
    elif t == "dec_vals":
        print(f"Decimal: {p['vals']}")
        print(f"{'='*60}\n")
    elif t == "send":
        print(f"[SEND] type=0x{p['type']:02x} len={p['len']} plain={p['plain']}")
    elif t == "info":
        print(f"[INFO] {p['msg']}")
    elif t == "error":
        print(f"[ERROR] {p['msg']}")
    else:
        print(f"[{t}] {p}")

    sys.stdout.flush()

def main():
    PID = 5630

    with open("portal_compare.js", "r", encoding="utf-8") as f:
        JS = f.read()

    print(f"Connecting to 127.0.0.1:27056 -> PID {PID}")
    dev = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
    session = dev.attach(PID)
    script = session.create_script(JS)
    script.on("message", on_msg)
    script.load()
    time.sleep(1.5)

    print("\n" + "="*60)
    print("PORTAL PACKET COMPARISON TOOL")
    print("="*60)
    print("""
Commands:
  a <label>  — Arm capture for next portal walk (e.g. "a map_a")
  c           — Compare last two captures
  ca          — Compare all captures (show differing bytes)
  s           — Show status
  l           — List all captures
  clear       — Clear all captures
  send <idx> <mods>  — Build & send test packet (e.g. "send 0 5:aa12")
  raw <hex>   — Send raw plain hex to socket
  q           — Quit

Workflow:
  1. Type "a portal_A" to arm capture
  2. Walk through portal A in game
  3. Type "a portal_B" to arm capture
  4. Walk through portal B (DIFFERENT destination)
  5. Type "c" to compare
""")

    try:
        while True:
            cmd = input("(portal) ").strip()
            if not cmd:
                continue

            parts = cmd.split(None, 1)
            op = parts[0].lower()

            if op == "q":
                break
            elif op == "a":
                label = parts[1] if len(parts) > 1 else "unnamed"
                result = script.exports_sync.arm_capture(label)
                print(f"  {result}")
                print(f"  >> NOW walk through the portal in game <<")
            elif op == "c":
                if len(CAPTURES) < 2:
                    print(f"  Need 2+ captures, have {len(CAPTURES)}")
                else:
                    c1 = CAPTURES[-2]
                    c2 = CAPTURES[-1]
                    print(f"\n  Comparing [{c1['label']}] vs [{c2['label']}]:")
                    diff_count = 0
                    for i in range(29):
                        b1 = int(c1["plain"][i*2:i*2+2], 16)
                        b2 = int(c2["plain"][i*2:i*2+2], 16)
                        if b1 != b2:
                            diff_count += 1
                            print(f"    Byte[{i:2d}]: 0x{b1:02x} ({b1:3d}) -> 0x{b2:02x} ({b2:3d})")
                    if diff_count == 0:
                        print("    (identical)")
                    else:
                        print(f"    Total: {diff_count} bytes differ")
            elif op == "ca":
                result = script.exports_sync.compare_all()
                try:
                    diff = json.loads(result)
                    if isinstance(diff, dict) and "error" not in diff:
                        print("  Bytes that differ across captures:")
                        for idx, changes in sorted(diff.items(), key=lambda x: int(x[0])):
                            print(f"    Byte[{idx}]: {changes}")
                    else:
                        print(f"  {diff}")
                except:
                    print(f"  {result}")
            elif op == "s":
                result = script.exports_sync.get_status()
                print(f"  {result}")
            elif op == "l":
                for i, c in enumerate(CAPTURES):
                    print(f"  [{i}] {c['label']}: {c['plain']}")
            elif op == "clear":
                script.exports_sync.clear_captures()
                CAPTURES.clear()
                print("  Cleared")
            elif op == "send":
                args = parts[1] if len(parts) > 1 else ""
                sp = args.split()
                if len(sp) >= 2:
                    idx = int(sp[0])
                    mods = sp[1]
                    plain = script.exports_sync.build_packet(idx, mods)
                    print(f"  Built: {plain}")
                    result = script.exports_sync.send_raw(plain, 0)
                    print(f"  {result}")
                else:
                    print("  Usage: send <idx> <mods>")
            elif op == "raw":
                if len(parts) > 1:
                    result = script.exports_sync.send_raw(parts[1], 0)
                    print(f"  {result}")
                else:
                    print("  Usage: raw <hex>")
            else:
                print(f"  Unknown: {op}")

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        session.detach()
        print("Disconnected")

if __name__ == "__main__":
    main()
