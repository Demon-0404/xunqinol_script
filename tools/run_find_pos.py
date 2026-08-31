# -*- coding: utf-8 -*-
"""注入 find_pos.js 并接收消息"""
import frida
import sys
import json

SCRIPT_PATH = "E:/DATA/xunqinol_script/tools/find_pos.js"

def on_message(msg, data):
    if msg['type'] == 'send':
        payload = msg.get('payload', {})
        t = payload.get('t', '')
        if t == 'info':
            print(f"[INFO] {payload.get('msg', '')}")
        elif t == 'snap':
            print(f"[SNAP] {payload.get('label', '')}: {payload.get('count', 0)} values")
        elif t == 'init_floats':
            print(f"[INIT_FLOATS] {payload.get('data', '')[:500]}")
        elif t == 'ready':
            print(f"[READY] {payload.get('msg', '')}")
            print(f"         {payload.get('msg2', '')}")
            print(f"  initCandidates: {payload.get('initCandidates', 0)}")
        else:
            print(f"[MSG t={t}] {json.dumps(payload, ensure_ascii=False)[:300]}")
    elif msg['type'] == 'error':
        print(f"[ERROR] {msg.get('description', '')}")

def main():
    device = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
    session = device.attach(5630)

    with open(SCRIPT_PATH, 'r', encoding='utf-8') as f:
        script_code = f.read()

    script = session.create_script(script_code)
    script.on('message', on_message)
    script.load()

    print("=" * 60)
    print("find_pos.js 已注入！等待初始化结果...")
    print("=" * 60)

    # 保持运行接收消息
    try:
        import time
        time.sleep(10)
    except KeyboardInterrupt:
        pass

    # 提供交互命令
    print("\n可用 RPC 命令:")
    print("  snapshot('label')  - 创建内存快照")
    print("  compare()          - 比较最近两次快照")
    print("  scanFloats()       - 重新扫描float坐标")
    print("  getCandidates()    - 查看候选地址")
    print("  watchAddr(addr)    - 读取指定地址值")
    print("  readAround(addr)   - 读取地址周围32字节")
    print("\n输入 RPC 调用 (如 scanFloats()) 或 quit 退出:")

    while True:
        try:
            cmd = input("> ").strip()
            if not cmd:
                continue
            if cmd.lower() == 'quit':
                break

            # 执行RPC
            result = eval(f"script.exports.{cmd}")
            print(result)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

    session.detach()
    print("Done.")

if __name__ == '__main__':
    main()
