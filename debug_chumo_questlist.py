# -*- coding: utf-8 -*-
"""仗剑除魔 任务列表探测：按数字键1打开任务列表 → OCR识别所有任务名 → 模糊匹配'仗剑除魔'"""
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

QUEST_LIST_Y_START = 300
QUEST_LIST_Y_END = 1300


def tap(pos, desc="", wait=0.5):
    print(f"点击 {desc}{pos}")
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap",
                    str(pos[0]), str(pos[1])], capture_output=True, timeout=10)
    time.sleep(wait)


def screenshot():
    tmp = os.path.join(LOG_DIR, "_debug_chumo_tmp.png")
    with open(tmp, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=5)
    return np.array(Image.open(tmp))[:, :, :3]


def match_chumo_quest(text):
    if "除魔" in text or "仗剑" in text:
        return True
    common = sum(1 for ch in text if ch in "仗剑除魔")
    return common >= 2


def main():
    from core.ocr_client import get_ocr_client
    reader = get_ocr_client()

    print("=== 仗剑除魔 任务列表探测 ===")
    tap(KEY1, "任务列表(数字键1)", 1.5)
    arr = screenshot()
    ts = time.strftime("%H%M%S")
    Image.fromarray(arr).save(os.path.join(LOG_DIR, f"_debug_chumo_questlist_{ts}.png"))
    print(f"已保存截图 _debug_chumo_questlist_{ts}.png")

    res = reader.readtext(arr, mag_ratio=1)
    print("--- 任务列表 OCR 识别结果 (y 300~1300) ---")
    found = []
    for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        if conf < 0.2:
            continue
        cx = int((bbox[0][0] + bbox[2][0]) / 2)
        cy = int((bbox[0][1] + bbox[2][1]) / 2)
        in_list = QUEST_LIST_Y_START <= cy <= QUEST_LIST_Y_END
        mark = "  <-- 匹配仗剑除魔!" if (in_list and match_chumo_quest(text)) else ""
        print(f"  ({cx},{cy}) conf={conf:.2f} '{text}'{' [列表区]' if in_list else ''}{mark}")
        if in_list and match_chumo_quest(text):
            found.append((cx, cy, text, conf))

    print("--- 匹配结果 ---")
    if found:
        for cx, cy, text, conf in found:
            print(f"  命中: '{text}' @({cx},{cy}) conf={conf:.2f}")
    else:
        print("  未匹配到'仗剑除魔'，请检查截图和关键词")
    print("=== 探测完成 ===")


if __name__ == "__main__":
    main()
