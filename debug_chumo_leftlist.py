# -*- coding: utf-8 -*-
"""仗剑除魔 任务列表左侧区域细扫：只扫左侧任务列表列(x 0~540)，看清有哪些任务条目"""
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


def tap(pos, desc="", wait=0.5):
    print(f"点击 {desc}{pos}")
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap",
                    str(pos[0]), str(pos[1])], capture_output=True, timeout=10)
    time.sleep(wait)


def screenshot():
    tmp = os.path.join(LOG_DIR, "_debug_chumo_left_tmp.png")
    with open(tmp, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=5)
    return np.array(Image.open(tmp))[:, :, :3]


def main():
    from core.ocr_client import get_ocr_client
    reader = get_ocr_client()

    print("=== 左侧任务列表列细扫 ===")
    tap(KEY1, "任务列表(数字键1)", 1.5)
    arr = screenshot()
    h, w = arr.shape[:2]

    # 左侧任务列表列 x 0~540，y 250~1350
    left = arr[250:1350, 0:540, :]
    ts = time.strftime("%H%M%S")
    Image.fromarray(left).save(os.path.join(LOG_DIR, f"_debug_chumo_left_{ts}.png"))
    print(f"已保存左侧裁剪 _debug_chumo_left_{ts}.png")

    print("--- 左侧区域 OCR (mag=1, conf>=0.1) ---")
    res = reader.readtext(left, mag_ratio=1)
    for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        if conf < 0.1:
            continue
        cx = int((bbox[0][0] + bbox[2][0]) / 2)
        cy = int((bbox[0][1] + bbox[2][1]) / 2) + 250  # 加回y偏移
        print(f"  ({cx},{cy}) conf={conf:.2f} '{text}'")

    print("--- 左侧区域 OCR (mag=2, conf>=0.1) ---")
    res2 = reader.readtext(left, mag_ratio=2)
    for r in sorted(res2, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        if conf < 0.1:
            continue
        cx = int((bbox[0][0] + bbox[2][0]) / 2)
        cy = int((bbox[0][1] + bbox[2][1]) / 2) + 250
        print(f"  ({cx},{cy}) conf={conf:.2f} '{text}'")

    print("=== 细扫完成 ===")


if __name__ == "__main__":
    main()
