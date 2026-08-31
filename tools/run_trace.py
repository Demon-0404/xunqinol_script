"""Call stack trace launcher"""
import frida, time, sys, json

with open("E:/DATA/xunqinol_script/tools/trace_portal.js", "r", encoding="utf-8") as f:
    JS = f.read()

dev = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = dev.attach(5630)
script = session.create_script(JS)

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict): return
    t = p.get("t", "")
    if t == "ready":
        print("[READY] " + p.get("msg", ""))
    elif t == "info":
        print("[INFO] " + p.get("msg", ""))
    elif t == "portal_trace":
        print("\n[PORTAL #%d] raw=%s" % (p["count"], p["raw"]))
    elif t == "trace_frame":
        print("  #%d %s %s" % (p["idx"], p["module"], p["symbol"]))
    elif t == "found_func":
        print("  >>> 候选函数: #%d %s @ %s" % (p["idx"], p["module"], p["addr"]))
    elif t == "trace_detail":
        print(p["msg"])
    sys.stdout.flush()

script.on("message", on_msg)
script.load()
time.sleep(0.5)

print("=" * 50)
print("调用栈追踪就绪 - 请走传送门")
print("=" * 50)

try:
    time.sleep(180)
except KeyboardInterrupt:
    pass

try:
    traces = script.exports_sync.get_traces()
    print("\n=== 所有追踪结果 ===")
    print(traces[:2000])
except: pass

try:
    session.detach()
except: pass
print("\nDone")
