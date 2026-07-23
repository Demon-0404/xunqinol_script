"""测试：屏幕网格扫描，找能触发"进入战斗"的怪物并走过去"""
import sys, os, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import subprocess
from airtest.core.api import touch, exists, Template
from core.device import scan_available_devices, connect_device_by_serial, switch_device
from core.actions import screenshot

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(BASE_DIR, "templates", "tower")

# ── 连接 ──
adb = os.environ.get("ANDROID_ADB", "adb")
r = subprocess.run([adb, "devices"], capture_output=True, text=True, encoding="utf-8", errors="replace")
online = [l.split("\t")[0] for l in r.stdout.strip().split("\n")[1:] if "\tdevice" in l]
print(f"在线: {online}")
if not online:
    print("没有在线设备!"); sys.exit(1)

devices = scan_available_devices()
want = sys.argv[1] if len(sys.argv) > 1 else None
target = None
if want:
    for d in devices:
        if d["name"] == want:
            target = {"name": d["name"], "serial": "127.0.0.1:7555" if "127.0.0.1:7555" in online else d["serial"]}
            break
if not target:
    target = {"name": "设备", "serial": online[0]}
ok = connect_device_by_serial(target["name"], target["serial"])
switch_device(target["name"])
print(f"已连接 {target['name']}")

# ── 战斗流程模板 ──
enter_battle = Template(os.path.join(TPL_DIR, "enter_battle.png"), threshold=0.75)

# ── 网格扫描 ──
# 屏幕1080x1920，人物在底部中央，怪物在中上部
# 扫描区域: x=80~1000, y=300~1500, 步长120
print("\n开始网格扫描，寻找怪物...")
found = None
for y in range(350, 1400, 100):
    if found: break
    for x in range(150, 950, 120):
        if found: break
        print(f"  点击 ({x},{y})...")
        # 先点地面走过去
        touch((x, y))
        time.sleep(0.3)

# 等角色走过去
print("等待角色移动...")
time.sleep(1.5)

# 再扫一次，这次点怪物触发对话
for y in range(350, 1400, 100):
    if found: break
    for x in range(150, 950, 80):
        if found: break
        touch((x, y))
        time.sleep(0.8)
        if exists(enter_battle):
            print(f"\n找到怪物! 位置=({x},{y}) 已弹出'进入战斗'")
            found = (x, y)
            touch(enter_battle)
            break
        # 点空白处关闭可能的误触
        touch((1000, 1800))
        time.sleep(0.2)

if found:
    print(f"成功! 怪物在 ({found[0]},{found[1]})")
else:
    print("未找到怪物，可能扫描区域不对")
