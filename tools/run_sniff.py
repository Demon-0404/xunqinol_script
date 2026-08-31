"""Portal sniff launcher for TianYin"""
import frida, time, sys, json

OUTFILE = "E:/DATA/xunqinol_script/tools/portal_sniff_log.txt"

with open("E:/DATA/xunqinol_script/tools/portal_sniff.js", "r", encoding="utf-8") as f:
    JS = f.read()

dev = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = dev.attach(5630)
script = session.create_script(JS)

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict):
        return
    t = p.get("t", "")
    s = json.dumps(msg, ensure_ascii=False)
    with open(OUTFILE, "a", encoding="utf-8") as f:
        f.write(s + "\n")

    # Print key events
    if t == "ready":
        print("[READY] Script loaded!")
        print("  " + p.get("msg", ""))
        print("  " + p.get("msg2", ""))
        print("  " + p.get("msg3", ""))
    elif t == "portal":
        print("[PORTAL #%d] %s" % (p.get("index", 0), p.get("raw", "")))
    elif t == "portal_detail":
        print(p.get("detail", ""))
    elif t == "key_found":
        print("[KEY] XOR key = 0x%02x" % p["key"])
    elif t == "map_data":
        print("[MAP] #%d %dB head=%s" % (p.get("count", 0), p.get("len", 0), p.get("head", "")))
    elif t == "recv_type5":
        print("[TYPE5] %dB %s" % (p.get("len", 0), p.get("msg", "")))
    elif t == "move":
        print("[MOVE] %dB byte0=%s" % (p.get("len", 0), p.get("byte0", "")))
    elif t == "info":
        print("[INFO] " + p["msg"])
    elif t == "warn":
        print("[WARN] " + p["msg"])
    elif t == "error":
        print("[ERROR] " + p["msg"])

    sys.stdout.flush()

script.on("message", on_msg)
script.load()
time.sleep(0.5)

print("")
print("=" * 50)
print("  Portal Sniff 已就绪 - 请在游戏中走传送门")
print("  日志: " + OUTFILE)
print("=" * 50)

try:
    time.sleep(300)
except KeyboardInterrupt:
    pass

try:
    session.detach()
except:
    pass
print("Done")
