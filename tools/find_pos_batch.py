# -*- coding: utf-8 -*-
"""注入 -> 初始快照 -> 等用户走步 -> 二次快照 -> 比较"""
import frida
import json
import sys
import os
import time

SCRIPT = "E:/DATA/xunqinol_script/tools/find_pos.js"

def on_msg(msg, data):
    if msg['type'] == 'send':
        p = msg.get('payload', {})
        t = p.get('t', '')
        if t == 'snap':
            print(f"[SNAP] {p['label']}: {p['count']} values")
        elif t == 'init_floats':
            d = json.loads(p.get('data', '[]'))
            print(f"[FLOATS] {len(d)} candidates")
            for i, f in enumerate(d[:10]):
                print(f"  [{i}] {f['addr']}: ({f['x']}, {f['y']}, {f['z']})")
        elif t == 'ready':
            print(f"[READY] {p['msg']}")
        elif t == 'info':
            pass
        else:
            pass
    elif msg['type'] == 'error':
        print(f"[ERROR] {msg.get('description','')}")

print("Connecting to 127.0.0.1:27056 ...")
device = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = device.attach(5630)

with open(SCRIPT, 'r', encoding='utf-8') as f:
    code = f.read()

script = session.create_script(code)
script.on('message', on_msg)
script.load()
time.sleep(5)  # Wait for initial scan + snapshot

print("\n" + "="*50)
print("[STEP 1] Initial snapshot complete!")
print("[STEP 2] Waiting 10 seconds for you to walk...")
print("          Walk ONE STEP now!")
print("="*50)

for i in range(10, 0, -1):
    print(f"  {i}...")
    time.sleep(1)

print("\n[STEP 3] Taking AFTER snapshot...")
script.exports.snapshot("after")
time.sleep(1)

print("[STEP 4] Comparing...")
result = script.exports.compare()
changes = json.loads(result)

print(f"\n{'='*50}")
print(f"RESULTS: {len(changes)} changed addresses")
print(f"{'='*50}")

for i, c in enumerate(changes[:30]):
    print(f"  [{i:2d}] {c['addr']}: {c['v1']} -> {c['v2']} (diff={c['diff']})")

# Also get candidates
cands = json.loads(script.exports.get_candidates())
print(f"\nTop candidates:")
for i, c in enumerate(cands[:10]):
    print(f"  [{i}] {c['addr']}: {c['v1']} -> {c['v2']} (diff={c['diff']})")

# Save
with open("/tmp/pos_results.json", "w") as f:
    json.dump({"changes": changes, "candidates": cands}, f)
print("\nSaved to /tmp/pos_results.json")

session.detach()
print("Done.")
