# -*- coding: utf-8 -*-
"""铁1(赤炼) Phase 13 探测：打开任务列表，OCR识别所有任务名+坐标"""
import sys, os, time, subprocess
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
LOG_DIR = os.path.join(BASE_DIR, "logs")

SERIAL = "127.0.0.1:16480"
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"

KEY1 = (350, 1590)   # 数字键1 打开任务列表


def tap(pos, desc="", wait=0.3):
    print(f"点击 {desc}{pos}")
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap",
                    str(pos[0]), str(pos[1])], capture_output=True, timeout=10)
    time.sleep(wait)


def screenshot():
    tmp = os.path.join(LOG_DIR, "_debug_tie1_tmp.png")
    with open(tmp, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=5)
    return np.array(Image.open(tmp))[:, :, :3]


def ocr_dump(arr):
    from core.ocr_client import get_ocr_client
    reader = get_ocr_client()
    res = reader.readtext(arr, mag_ratio=1)
    for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        if conf < 0.2:
            continue
        cx = int((bbox[0][0] + bbox[2][0]) / 2)
        cy = int((bbox[0][1] + bbox[2][1]) / 2)
        print(f"  ({cx},{cy}) conf={conf:.2f} '{text}'")


print("=== Phase 13 探测: 打开任务列表 ===")
tap(KEY1, "任务列表(1)", 1.5)
arr = screenshot()
ts = time.strftime("%H%M%S")
Image.fromarray(arr).save(os.path.join(LOG_DIR, f"_debug_tie1_questlist_{ts}.png"))
print(f"已保存截图 _debug_tie1_questlist_{ts}.png")
print("--- 任务列表 OCR 识别结果 ---")
ocr_dump(arr)
print("=== 探测完成 ===")
