"""测试：用怪物名字模板匹配找怪并走过去"""
import sys, os, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.device import connect_device_by_serial, switch_device
import subprocess
from airtest.core.api import touch, exists, Template

# ADB 在线设备
adb = os.environ.get("ANDROID_ADB", "adb")
r = subprocess.run([adb, "devices"], capture_output=True, text=True, encoding="utf-8", errors="replace")
online = [l.split("\t")[0] for l in r.stdout.strip().split("\n")[1:] if "\tdevice" in l]
if not online:
    print("没有在线设备!"); sys.exit(1)
port = "127.0.0.1:7555" if "127.0.0.1:7555" in online else online[0]

ok = connect_device_by_serial("设备", port)
switch_device("设备")
print(f"已连接 {port}")

# 加载怪物模板
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
tpl_path = os.path.join(BASE_DIR, "templates", "tower", "names", "monster_floor1_01.png")
if not os.path.exists(tpl_path):
    print(f"模板不存在: {tpl_path}"); sys.exit(1)

monster_tpl = Template(tpl_path, threshold=0.6, rgb=True)

# 在屏幕上找怪物
print("搜索离火剑...")
pos = exists(monster_tpl)
if pos:
    print(f"找到! 位置={pos}")
    touch(pos)
    print("点击走过去...")
    time.sleep(2)
    touch(pos)
    print("再次点击")
else:
    print("未找到，试试降低阈值...")
    monster_tpl = Template(tpl_path, threshold=0.45, rgb=True)
    pos = exists(monster_tpl)
    if pos:
        print(f"低阈值找到! 位置={pos}")
        touch(pos)
    else:
        print("仍未找到，需要重新截图")
