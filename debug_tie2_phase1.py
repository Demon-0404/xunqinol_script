# -*- coding: utf-8 -*-
"""铁2(浮游) Phase 1 调试：NPC对话进入副本（6步，参考90副本）"""
import sys, os, time, subprocess
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

SERIAL = "127.0.0.1:16480"
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"

KEY5 = (150, 1590)          # 数字键5 确认/对话
KEY_STAR = (150, 1790)      # *号键 一键接取
ENTER_CONFIRM = (100, 1200) # 确认进入/缴费进入


def tap(pos):
    print(f"点击 {pos}")
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap",
                    str(pos[0]), str(pos[1])], capture_output=True, timeout=10)


def screenshot():
    tmp = os.path.join(BASE_DIR, "logs", "_debug_tie2_tmp.png")
    with open(tmp, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=5)
    return np.array(Image.open(tmp))[:, :, :3]


def map_name(arr):
    from core.ocr_client import get_ocr_client
    reader = get_ocr_client()
    crop = arr[50:200, 830:1040, :]
    try:
        res = reader.readtext(crop, mag_ratio=1)
    except Exception:
        return ""
    return "".join(r[1] for r in res if r[2] >= 0.2)


print("=== 铁2 Phase 1: NPC对话进入副本（6步） ===")

print("步骤1: 键5 对话 (150,1590)")
tap(KEY5); time.sleep(1.0)

print("步骤2: 键5 进入对话 (150,1590)")
tap(KEY5); time.sleep(1.0)

print("步骤3: *号 一键接取 (150,1790)")
tap(KEY_STAR); time.sleep(1.0)

print("步骤4: 键5 确认 (150,1590)")
tap(KEY5); time.sleep(1.0)

print("步骤5: 确认进入 (100,1200)")
tap(ENTER_CONFIRM); time.sleep(0.8)

print("步骤6: 缴费确认 (100,1200)")
tap(ENTER_CONFIRM); time.sleep(3.0)

print("步骤7: 截图读地图名")
arr = screenshot()
name = map_name(arr)
print(f"进入后地图名: '{name}'")

print("=== Phase 1 完成 ===")
