"""记录屏幕点击坐标 —— 用户在模拟器上点击时自动记录坐标
用法: python record_taps.py [设备名]
按 Enter 结束录制
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import subprocess
import re
import time
import json
import threading

from core.device import scan_available_devices, connect_device_by_serial, switch_device

adb = os.environ.get("ANDROID_ADB", "adb")

# 连接设备
r = subprocess.run([adb, "devices"], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
online = [l.split("\t")[0] for l in r.stdout.strip().split("\n")[1:] if "\tdevice" in l]
print(f"在线设备: {online}")
if not online:
    print("无在线设备"); sys.exit(1)

devices = scan_available_devices()
want = sys.argv[1] if len(sys.argv) > 1 else None
target = None
if want:
    for d in devices:
        if d["name"] == want:
            target = d
            break
if not target:
    port = "127.0.0.1:7555" if "127.0.0.1:7555" in online else online[0]
    target = {"name": "设备", "serial": port}

ok, _ = connect_device_by_serial(target["name"], target["serial"])
switch_device(target["name"])
print(f"已连接 {target['name']} ({target['serial']})")

serial = target["serial"]

# 找到触摸输入设备
r = subprocess.run([adb, "-s", serial, "shell", "getevent", "-p"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
# 找支持 ABS_MT_POSITION_X 的设备
touch_device = None
current_dev = None
for line in r.stdout.split("\n"):
    if line.startswith("add device"):
        current_dev = line.split(":")[1].strip()
    if "ABS_MT_POSITION_X" in line and current_dev:
        touch_device = current_dev
        break

if not touch_device:
    print("找不到触摸设备!")
    sys.exit(1)
print(f"触摸设备: {touch_device}")

taps = []
last_x, last_y = 0, 0
recording = True


def monitor_touches():
    global recording, last_x, last_y
    proc = subprocess.Popen(
        [adb, "-s", serial, "shell", "getevent", "-l", touch_device],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace"
    )
    for line in proc.stdout:
        if not recording:
            proc.terminate()
            break
        # 解析坐标（十六进制）
        mx = re.search(r'ABS_MT_POSITION_X\s+([0-9a-fA-F]+)', line)
        if mx:
            last_x = int(mx.group(1), 16)
        my = re.search(r'ABS_MT_POSITION_Y\s+([0-9a-fA-F]+)', line)
        if my:
            last_y = int(my.group(1), 16)
        # BTN_TOUCH DOWN 表示按下
        if "BTN_TOUCH" in line and "DOWN" in line:
            taps.append({"x": last_x, "y": last_y, "t": time.time()})
            print(f"  [{len(taps)}] 点击 ({last_x}, {last_y})")


thread = threading.Thread(target=monitor_touches, daemon=True)
thread.start()

print("\n开始录制！在模拟器上点击，坐标会实时显示。")
print("按 Enter 结束录制...\n")

input()

recording = False
time.sleep(0.3)

# 保存
save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "logs", f"tap_record_{time.strftime('%Y%m%d_%H%M%S')}.json")
with open(save_path, "w", encoding="utf-8") as f:
    json.dump(taps, f, ensure_ascii=False, indent=2)
print(f"\n已保存 {len(taps)} 个点击坐标到: {save_path}")

# 打印汇总
print("\n点击序列:")
for i, t in enumerate(taps):
    print(f"  [{i+1}] ({t['x']}, {t['y']})")
