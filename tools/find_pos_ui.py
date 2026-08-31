# -*- coding: utf-8 -*-
"""交互式找坐标工具"""
import frida
import sys
import json
import os

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "find_pos.js")

def on_message(msg, data):
    if msg['type'] == 'send':
        p = msg.get('payload', {})
        t = p.get('t', '')
        if t == 'info':
            print(f"  [INFO] {p.get('msg','')}")
        elif t == 'snap':
            print(f"  [SNAP] {p.get('label','')}: {p.get('count',0)} values")
        elif t == 'init_floats':
            print(f"  [FLOATS] {len(json.loads(p.get('data','[]')))} candidates found")
        elif t == 'ready':
            print(f"  [READY] {p.get('msg','')} | {p.get('msg2','')}")
        else:
            pass  # suppress other messages
    elif msg['type'] == 'error':
        print(f"  [ERROR] {msg.get('description','')}")

def main():
    device = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
    session = device.attach(5630)

    with open(SCRIPT_PATH, 'r', encoding='utf-8') as f:
        script = session.create_script(f.read())
    script.on('message', on_message)
    script.load()

    print("=" * 55)
    print("  找坐标工具 - find_pos.js")
    print("=" * 55)
    print()
    print("  1. 在游戏里走一步 (wasd/点击)")
    print("  2. 按回车执行 snapshot('after') + compare()")
    print("  3. 查看哪些内存地址变化了")
    print()

    input("按回车开始 (先走一步再按) ...")

    # Take after snapshot
    print("\n>>> 创建 after 快照...")
    script.exports.snapshot("after")
    import time; time.sleep(0.5)

    print(">>> 比较快照...")
    result = script.exports.compare()
    changes = json.loads(result)
    print(f"\n找到 {len(changes)} 个变化地址 (显示前20):")
    print("-" * 55)
    for i, c in enumerate(changes[:20]):
        print(f"  [{i}] {c.get('addr','?')}: {c.get('v1',0)} -> {c.get('v2',0)} (diff={c.get('diff',0)})")

    # Also scan floats
    print("\n>>> 重新扫描 float 坐标...")
    floats = json.loads(script.exports.scan_floats())
    print(f"找到 {len(floats)} 个候选坐标:")
    print("-" * 55)
    for i, f in enumerate(floats[:15]):
        print(f"  [{i}] {f.get('addr','?')}: ({f.get('x','?')}, {f.get('y','?')}, {f.get('z','?')})")

    # Interactive loop
    print("\n" + "=" * 55)
    print("交互模式:")
    print("  addr <addr>     - 查看地址值")
    print("  around <addr>   - 查看地址周围32字节")
    print("  write <addr> <x> <y> - 写坐标!")
    print("  snap <label>    - 创建新快照")
    print("  comp            - 比较最近两次快照")
    print("  quit            - 退出")
    print("=" * 55)

    while True:
        try:
            cmd = input("> ").strip()
            if not cmd:
                continue
            parts = cmd.split()
            if parts[0] == 'quit':
                break
            elif parts[0] == 'addr' and len(parts) >= 2:
                r = script.exports.watch_addr(parts[1])
                print(r)
            elif parts[0] == 'around' and len(parts) >= 2:
                r = script.exports.read_around(parts[1])
                print(r)
            elif parts[0] == 'write' and len(parts) >= 4:
                r = script.exports.write_position(parts[1], float(parts[2]), float(parts[3]))
                print(r)
            elif parts[0] == 'snap' and len(parts) >= 2:
                script.exports.snapshot(parts[1])
                print(f"Snapshot '{parts[1]}' taken")
            elif parts[0] == 'comp':
                r = script.exports.compare()
                changes2 = json.loads(r)
                print(f"Changes: {len(changes2)}")
                for i, c in enumerate(changes2[:20]):
                    print(f"  [{i}] {c.get('addr','?')}: {c.get('v1',0)} -> {c.get('v2',0)} (diff={c.get('diff',0)})")
            else:
                print("Unknown command")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

    session.detach()
    print("Done.")

if __name__ == '__main__':
    main()
