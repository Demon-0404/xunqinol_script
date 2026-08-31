"""
天音设备 — 传送门handler诊断工具
======================================
目的: 抓取C++ handler参数 → 验证能否直接调用跳图函数

使用方法:
  1. 确保天音设备已连接 (ADB 127.0.0.1:16384, Frida 127.0.0.1:27056)
  2. 确保游戏已登录，角色站在任意位置
  3. 运行此脚本: D:/Setup_and_Downloads/Setup/python3.12.4/python.exe tools/diag_handler.py
  4. 按控制台提示操作
"""
import frida, time, sys, json

FILES = "E:/DATA/xunqinol_script/tools"
FRIDA_HOST = "127.0.0.1:27056"

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict):
        return
    t = p.get("t", "")

    if t == "ready":
        print(f"\n{'='*60}")
        print(f"[就绪] {p.get('msg', '')}")
        for k in [f'msg{i}' for i in range(2, 14)]:
            v = p.get(k)
            if v:
                print(v)
        print(f"fd={p.get('gameFd')} key={p.get('key')}")
        print(f"{'='*60}\n")

    elif t == "info":
        print(f" [信息] {p['msg']}")

    elif t == "warn":
        print(f" [警告] {p['msg']}")

    elif t == "error":
        print(f" [错误] {p['msg']}")

    elif t == "fd_found":
        print(f" [FD] 游戏socket fd={p.get('fd')} {p.get('msg','')}")

    elif t == "key_found":
        print(f" [密钥] XOR key = 0x{p['key']:02x} ({p.get('side','send')}侧检测)")

    elif t == "handler_enter":
        print(f"\n{'*'*50}")
        print(f"[HANDLER] 第{p['count']}次调用 ━━━━━━━━━━━━━━━━")
        print(f"  R0 (handlerObj): {p['r0']}")
        print(f"  R1 (urlPtr):     {p['r1']}")
        print(f"  R2:              {p['r2']}")
        print(f"  R3:              {p['r3']}")
        print(f"  LR (返回地址):   {p['lr']}")
        print(f"  URL:             {p.get('url', '?')}")
        print(f"  objDump(32B):    {p.get('objDump', '?')}")
        print(f"{'*'*50}")

    elif t == "handler_url":
        print(f"  >>> URL字符串: {p['url']}")

    elif t == "handler_str2":
        print(f"  >>> R2字符串: {p['str']}")

    elif t == "handler_leave":
        print(f"  <<< handler 返回: {p['ret']}")

    elif t == "func1_enter":
        print(f"  [func1] ENTER R0={p['r0']} R1={p['r1']} R2={p['r2']} R3={p['r3']}")

    elif t == "func1_leave":
        print(f"  [func1] LEAVE ret={p['ret']}")

    elif t == "func2_enter":
        print(f"  [func2] ENTER R0={p['r0']} R1={p['r1']} R2={p['r2']} R3={p['r3']}")

    elif t == "func2_leave":
        print(f"  [func2] LEAVE ret={p['ret']}")

    elif t == "portal_packet":
        print(f"\n  [传送包] 明文({len(p['plain'])//2}B): {p['plain']}")

    elif t == "portal_detail":
        print(p['detail'])

    elif t == "disasm":
        label = p['label']
        insts = p.get('instructions', [])
        print(f"\n  === 反汇编 {label} @ {p['addr']} ===")
        for ins in insts:
            if 'err' in ins:
                print(f"    {ins['offset']:4d}  [ERR] {ins['err']}")
            else:
                print(f"    {ins['offset']:4d}  {ins['bytes']:<12s}  {ins['asm']}")

    elif t == "try_call":
        print(f"  [尝试调用] {p['msg']}")

    else:
        # 忽略过于频繁的消息
        pass

    sys.stdout.flush()


def main():
    print("=" * 60)
    print("  天音 — 传送门handler诊断工具")
    print("=" * 60)

    # 读取JS
    js_path = f"{FILES}/diag_handler.js"
    with open(js_path, "r", encoding="utf-8") as f:
        JS = f.read()

    # 连接天音
    print(f"\n连接 Frida: {FRIDA_HOST} ...")
    try:
        dev = frida.get_device_manager().add_remote_device(FRIDA_HOST)
    except Exception as e:
        print(f"[失败] 无法连接Frida: {e}")
        print("请确认:")
        print("  1. 天音模拟器已启动")
        print("  2. frida-server 已运行 (adb shell /data/local/tmp/frida-server -l 0.0.0.0:27056 &)")
        return

    # 尝试附加游戏进程
    print("查找游戏进程...")
    app = None
    try:
        app = dev.get_frontmost_application()
        print(f"  前台应用: {app.name} (PID={app.pid})")
    except:
        pass

    if not app or "proj.xqj" not in getattr(app, 'identifier', ''):
        print("尝试枚举进程找 proj.xqj ...")
        try:
            for proc in dev.enumerate_processes():
                if "xqj" in proc.name.lower() or "xunqin" in proc.name.lower():
                    print(f"  找到: {proc.name} (PID={proc.pid})")
                    app = proc
                    break
        except:
            pass

    if not app:
        pid = input("请输入游戏PID (或直接回车尝试5630): ").strip()
        if not pid:
            pid = 5630
        else:
            pid = int(pid)
    else:
        pid = app.pid

    print(f"附加 PID={pid} ...")
    try:
        session = dev.attach(pid)
    except Exception as e:
        print(f"[失败] 无法附加: {e}")
        return

    script = session.create_script(JS)
    script.on("message", on_msg)
    script.load()
    time.sleep(1)

    print("""
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  【现在请操作游戏】                                          │
│                                                             │
│  点击任意一个传送门，走过去触发传送。                         │
│                                                             │
│  观察本窗口输出:                                             │
│    - handler_enter → 确认handler被调用                       │
│    - handler_url  → 确认URL格式                              │
│    - portal_packet → 确认传送包内容                          │
│                                                             │
│  走完后回来，输入命令进行下一步测试。                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
""")

    # 交互命令
    print("命令: status / last / try <URL> / tryfull <URL> / quit\n")

    try:
        while True:
            cmd = input("(handler)> ").strip()
            if not cmd:
                continue

            if cmd == "quit" or cmd == "exit":
                break

            elif cmd == "status":
                try:
                    r = script.exports_sync.get_status()
                    print(json.dumps(json.loads(r), indent=2, ensure_ascii=False))
                except Exception as e:
                    print(f"Error: {e}")

            elif cmd == "last":
                try:
                    r = script.exports_sync.get_last_call()
                    print(json.dumps(json.loads(r), indent=2, ensure_ascii=False))
                except Exception as e:
                    print(f"Error: {e}")

            elif cmd == "calls":
                try:
                    r = script.exports_sync.get_all_calls()
                    print(json.dumps(json.loads(r), indent=2, ensure_ascii=False))
                except Exception as e:
                    print(f"Error: {e}")

            elif cmd == "key":
                try:
                    k = script.exports_sync.get_key()
                    print(f"XOR key = 0x{k:02x}" if k else "key not detected yet")
                except Exception as e:
                    print(f"Error: {e}")

            elif cmd.startswith("try "):
                url = cmd[4:].strip()
                print(f"尝试调用 handler('{url}') ...")
                print("警告: 可能会掉线或崩溃，确定吗? (yes/no)")
                ok = input("> ").strip().lower()
                if ok == "yes":
                    try:
                        r = script.exports_sync.try_call_handler(url)
                        print(f"结果: {r}")
                    except Exception as e:
                        print(f"Error: {e}")

            elif cmd.startswith("tryfull "):
                url = cmd[7:].strip()
                print(f"尝试完整调用 func1+handler('{url}') ...")
                print("警告: 可能会掉线或崩溃，确定吗? (yes/no)")
                ok = input("> ").strip().lower()
                if ok == "yes":
                    try:
                        r = script.exports_sync.try_call_full(url)
                        print(f"结果: {r}")
                    except Exception as e:
                        print(f"Error: {e}")

            elif cmd == "help":
                print("""
命令说明:
  status   - 查看当前状态 (fd, key, handler地址等)
  last     - 查看最近一次handler调用的参数
  calls    - 查看所有handler调用记录
  key      - 查看XOR加密密钥
  try <URL>     - 用上次的handlerObj直接调用handler
                  例: try xqj://map?name=邯郸行政区
  tryfull <URL> - 完整模拟: func1初始化 + handler调用
                  例: tryfull xqj://map?name=汉中行政区
  quit     - 退出
""")

            else:
                print(f"未知命令: {cmd} (输入 help 查看帮助)")

    except KeyboardInterrupt:
        print("\n中断")
    finally:
        session.detach()
        print("已断开")


if __name__ == "__main__":
    main()
