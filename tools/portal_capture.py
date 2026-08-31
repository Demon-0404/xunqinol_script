"""One-shot portal capture"""
import frida, sys, json, time, os

LABEL = sys.argv[1] if len(sys.argv) > 1 else "unknown"
PID = 5630

with open("portal_compare.js", "r", encoding="utf-8") as f:
    JS = f.read()

dev = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = dev.attach(PID)
script = session.create_script(JS)

OUTPUT = f"E:/DATA/xunqinol_script/tools/result_{LABEL}.txt"
result = {"status": "waiting", "plain": "", "key": 0}

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict): return
    t = p.get("t", "?")

    if t == "ready":
        script.exports_sync.arm_capture(LABEL)
        result["status"] = "armed"
    elif t == "key_found":
        result["key"] = p["key"]
    elif t == "captured":
        result["status"] = "captured"
        result["plain"] = p["plain"]
        result["label"] = p["label"]
        result["breakdown"] = p.get("detail", "")

script.on("message", on_msg)
script.load()

time.sleep(1.5)

# Check every second for up to 30s
for i in range(30):
    time.sleep(1)
    if result["status"] == "captured":
        break

session.detach()

# Write result file
with open(OUTPUT, "w") as f:
    f.write(f"status={result['status']}\n")
    f.write(f"key=0x{result['key']:02x}\n")
    f.write(f"label={result.get('label', 'N/A')}\n")
    f.write(f"plain={result['plain']}\n")

print(f"status={result['status']}")
print(f"key=0x{result['key']:02x}")
print(f"plain={result['plain']}")
