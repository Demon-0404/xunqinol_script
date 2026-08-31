"""
Portal packet watcher - auto-captures and compares portal packets
Run this once, then walk through portals at your own pace.
"""
import frida, json, time, sys, os

PID = 5630
captures = []

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict):
        return
    t = p.get("t", "?")

    if t == "ready":
        print(f"\n[就绪] fd={p.get('fd','?')} key={p.get('key',0)}")
        print("[提示] 走到传送门，跟我说'抓 <名字>' 比如 '抓 北冥城郊'")
    elif t == "fd_found":
        print(f"[OK] 游戏socket: fd={p['fd']}")
    elif t == "key_found":
        print(f"[OK] XOR密钥: 0x{p['key']:02x}")
    elif t == "captured":
        captures.append({"label": p["label"], "plain": p["plain"]})
        print(f"\n{'='*55}")
        print(f"[抓到 #{len(captures)}] {p['label']}")
        print(f"明文: {p['plain']}")
        print(f"逐字节: {p.get('detail','')}")
        print(f"{'='*55}\n")

        if len(captures) >= 2:
            print(">>> 已抓到2个包，对比差异: ")
            c1, c2 = captures[-2], captures[-1]
            diffs = 0
            for i in range(29):
                b1 = int(c1["plain"][i*2:i*2+2], 16)
                b2 = int(c2["plain"][i*2:i*2+2], 16)
                if b1 != b2:
                    diffs += 1
                    print(f"  Byte[{i:2d}]: 0x{b1:02x} ({b1:3d}) -> 0x{b2:02x} ({b2:3d})")
            if diffs == 0:
                print("  (完全相同)")
            print()
        print("[提示] 继续走到另一个传送门，跟我说'抓 <名字>'")
    elif t == "send":
        if p.get("type") != 0x03 or p.get("len") != 29:
            pass  # ignore non-portal sends
    elif t == "info":
        print(f"[信息] {p['msg']}")
    elif t == "error":
        print(f"[错误] {p['msg']}")

    sys.stdout.flush()


with open("portal_compare.js", "r", encoding="utf-8") as f:
    JS = f.read()

print("连接游戏中...")
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = dev.attach(PID)
script = session.create_script(JS)
script.on("message", on_msg)
script.load()

print("[就绪] 跟我说'抓 <名字>'来武装抓包")

while True:
    try:
        cmd = input().strip()
        if not cmd:
            continue
        if cmd.startswith("抓 "):
            label = cmd[2:].strip()
            script.exports_sync.arm_capture(label)
            print(f">>> 已就绪: {label}")
            print(f">>> 现在走进传送门 ! <<<")
        elif cmd == "c":
            if len(captures) >= 2:
                c1, c2 = captures[-2], captures[-1]
                print(f"\n对比 [{c1['label']}] vs [{c2['label']}]:")
                for i in range(29):
                    b1 = int(c1["plain"][i*2:i*2+2], 16)
                    b2 = int(c2["plain"][i*2:i*2+2], 16)
                    if b1 != b2:
                        print(f"  Byte[{i:2d}]: 0x{b1:02x} -> 0x{b2:02x}")
            else:
                print(f"需要2个包, 现在只有{len(captures)}个")
        elif cmd == "l":
            for i, c in enumerate(captures):
                print(f"  [{i}] {c['label']}: {c['plain']}")
        elif cmd == "q":
            break
        elif cmd == "s":
            s = script.exports_sync.get_status()
            print(f"  {s}")
        sys.stdout.flush()
    except (EOFError, KeyboardInterrupt):
        break

session.detach()
print("已断开")
