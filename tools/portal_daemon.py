"""Persistent portal watcher - stays alive, captures all portals in one session."""
import frida, json, time, sys

OUTFILE = "E:/DATA/xunqinol_script/tools/portal_log.txt"
PID = 5630

with open("portal_auto.js", "r", encoding="utf-8") as f:
    JS = f.read()

dev = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = dev.attach(PID)
script = session.create_script(JS)

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict):
        return
    t = p.get("t", "")

    if t == "ready":
        with open(OUTFILE, "w") as f:
            f.write(f"READY|fd={p['fd']}\n")
        print(f"READY fd={p['fd']}")
    elif t == "portal":
        line = f"PORTAL|{p['n']}|{p['raw']}\n"
        with open(OUTFILE, "a") as f:
            f.write(line)
        print(f">>> PORTAL #{p['n']}: {p['raw']}")

    sys.stdout.flush()

script.on("message", on_msg)
script.load()

print("DAEMON RUNNING")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

session.detach()
print("STOPPED")
