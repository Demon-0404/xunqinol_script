"""非交互式诊断启动器 — 注入diag_handler.js并记录所有输出"""
import frida, time, sys, json

OUTFILE = "E:/DATA/xunqinol_script/tools/diag_output.txt"

with open("E:/DATA/xunqinol_script/tools/diag_handler.js", "r", encoding="utf-8") as f:
    JS = f.read()

dev = frida.get_device_manager().add_remote_device("127.0.0.1:27056")
session = dev.attach(5630)
script = session.create_script(JS)

def on_msg(msg, data):
    p = msg.get("payload", {})
    if not isinstance(p, dict):
        return
    t = p.get("t", "")
    line = ""

    if t == "ready":
        line = f"READY|fd={p.get('gameFd')}|key={p.get('key')}"
        for k in [f'msg{i}' for i in range(2, 14)]:
            v = p.get(k)
            if v: print(v); line += f"\n{v}"

    elif t == "handler_enter":
        line = f"HANDLER|#{p['count']}|R0={p['r0']}|R1={p['r1']}|R2={p['r2']}|R3={p['r3']}|LR={p['lr']}|URL={p.get('url','?')}|objDump={p.get('objDump','?')}"

    elif t == "handler_url":
        line = f"HANDLER_URL|{p['url']}"

    elif t == "handler_leave":
        line = f"HANDLER_LEAVE|ret={p['ret']}"

    elif t == "func1_enter":
        line = f"FUNC1|R0={p['r0']}|R1={p['r1']}|R2={p['r2']}|R3={p['r3']}"

    elif t == "func2_enter":
        line = f"FUNC2|R0={p['r0']}|R1={p['r1']}|R2={p['r2']}|R3={p['r3']}"

    elif t == "portal_packet":
        line = f"PORTAL_PACKET|plain={p['plain']}"

    elif t == "portal_detail":
        line = f"PORTAL_DETAIL|{p['detail']}"

    elif t == "key_found":
        line = f"KEY|{p['key']}|side={p.get('side','?')}"

    elif t == "fd_found":
        line = f"FD|{p['fd']}"

    elif t == "disasm":
        label = p['label']
        insts = p.get('instructions', [])
        lines = [f"DISASM|{label}|@{p['addr']}"]
        for ins in insts:
            if 'err' in ins:
                lines.append(f"  {ins['offset']:4d} [ERR] {ins['err']}")
            else:
                lines.append(f"  {ins['offset']:4d} {ins['bytes']} {ins['asm']}")
        line = "\n".join(lines)

    elif t == "info":
        line = f"INFO|{p['msg']}"

    elif t == "warn":
        line = f"WARN|{p['msg']}"

    elif t == "error":
        line = f"ERROR|{p['msg']}"

    else:
        return

    # 写文件 + 打印
    with open(OUTFILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line[:200])
    sys.stdout.flush()

script.on("message", on_msg)
script.load()

print("=" * 60)
print("诊断脚本已注入天音 (PID=5630)")
print("")
print("【现在请操作】在游戏中点击任意传送门走一次")
print("")
print("走完后回来告诉我，我会读取结果")
print(f"输出文件: {OUTFILE}")
print("=" * 60)
sys.stdout.flush()

# 等待30秒让用户走传送门，然后每5秒检查一次
try:
    time.sleep(300)  # 等5分钟，足够用户操作
except KeyboardInterrupt:
    pass

session.detach()
print("脚本已退出")
