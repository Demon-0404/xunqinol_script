"""快速截图工具 —— 用于采集模板图
用法: python quick_cap.py <截图名> [设备名]
例如: python quick_cap.py monster1
      python quick_cap.py monster1 猛士
"""
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.device import scan_available_devices, connect_device_by_serial, switch_device
from core.actions import screenshot

if len(sys.argv) < 2:
    print("用法: python quick_cap.py <截图名> [设备名]")
    print("例如: python quick_cap.py monster1 猛士")
    sys.exit(1)

name = sys.argv[1]
want_device = sys.argv[2] if len(sys.argv) > 2 else None

# 扫描设备
devices = scan_available_devices()
if not devices:
    print("未发现任何 MuMu 实例！")
    sys.exit(1)

# 选择设备
target = None

# 先直接用 ADB 看看 7555 在不在线
import subprocess
adb = os.environ.get("ANDROID_ADB", "adb")
r = subprocess.run([adb, "devices"], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
online = []
for line in r.stdout.strip().split("\n")[1:]:
    if "\tdevice" in line:
        online.append(line.split("\t")[0])

if want_device:
    for d in devices:
        if d["name"] == want_device:
            target = d
            break
    if not target:
        print(f"未找到 '{want_device}'，可用: {[d['name'] for d in devices]}")
        sys.exit(1)
    # 优先用 7555（单开模式）
    port = target["serial"]
    if "127.0.0.1:7555" in online:
        port = "127.0.0.1:7555"
    elif port not in online:
        print(f"设备 {target['name']} 不在线 ({port})，尝试 7555...")
        port = "127.0.0.1:7555"
    ok = connect_device_by_serial(target["name"], port)
    if not ok:
        print(f"连接失败！")
        sys.exit(1)
else:
    # 默认选第一个在线设备
    if online:
        connect_device_by_serial("设备", online[0])
        target = {"name": "设备"}
    else:
        print("没有在线设备！")
        sys.exit(1)
switch_device(target["name"])
print(f"已连接 {target['name']}")

# 截图
save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "tower")
os.makedirs(save_dir, exist_ok=True)
path = os.path.join(save_dir, f"{name}.png")
screenshot(path)
print(f"已保存: {path}")
