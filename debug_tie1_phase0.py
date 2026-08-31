# -*- coding: utf-8 -*-
"""铁1(赤炼) Phase 0 调试：备忘→副本→OCR找赤/炼→点行→瞬间传送"""
import sys, os, time, subprocess
import numpy as np
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

SERIAL = "127.0.0.1:16480"
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"

MEMO = (1000, 1200)      # 备忘
DUNGEON_TAB = (750, 200) # 副本标签


def tap(pos):
    print(f"点击 {pos}")
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap",
                    str(pos[0]), str(pos[1])], capture_output=True, timeout=10)


def screenshot():
    tmp = os.path.join(BASE_DIR, "logs", "_debug_tie1_tmp.png")
    with open(tmp, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=5)
    arr = np.array(Image.open(tmp))[:, :, :3]
    return arr


def ocr_all(arr, mag=1):
    from core.ocr_client import get_ocr_client
    reader = get_ocr_client()
    return reader.readtext(arr, mag_ratio=mag)


def dump_text(arr, title="识别到的文字"):
    print(f"--- {title} ---")
    res = ocr_all(arr)
    for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        if conf < 0.3:
            continue
        cx = int((bbox[0][0] + bbox[2][0]) / 2)
        cy = int((bbox[0][1] + bbox[2][1]) / 2)
        print(f"  ({cx},{cy}) conf={conf:.2f} '{text}'")
    return res


def find_text(arr, keyword, y_start, y_end, x_start=0, x_end=1080):
    res = ocr_all(arr)
    for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        if conf < 0.3 or keyword not in text:
            continue
        cx = int((bbox[0][0] + bbox[2][0]) / 2)
        cy = int((bbox[0][1] + bbox[2][1]) / 2)
        if x_start <= cx <= x_end and y_start <= cy <= y_end:
            return (cx, cy, text, conf)
    return None


print("=== 铁1 Phase 0: 备忘→副本→OCR找赤炼→点行→瞬间传送 ===")

print("步骤1: 点击备忘 (1000,1200)")
tap(MEMO); time.sleep(1.2)

print("步骤2: 点击副本标签 (750,200)")
tap(DUNGEON_TAB); time.sleep(1.2)

print("步骤3: 截图 + OCR 识别副本列表")
arr = screenshot()
dump_text(arr)

pos = find_text(arr, "赤", 300, 1300) or find_text(arr, "炼", 300, 1300)
if not pos:
    print("!!! 未找到 赤/炼，请查看上方识别结果")
    sys.exit(1)
cx, cy, text, conf = pos
print(f"步骤4: 找到 '{text}' @ ({cx},{cy}) conf={conf:.2f}")

print(f"步骤5: 点击该行 (250,{cy}) 两次")
tap((250, cy)); time.sleep(1.0)
tap((250, cy)); time.sleep(1.0)

print("步骤6: 截图 + OCR 找瞬间传送")
arr2 = screenshot()
tp = find_text(arr2, "瞬间传送", 400, 1200, 0, 1080)
if not tp:
    dump_text(arr2, "未找到瞬间传送，识别结果")
    print("!!! 未找到瞬间传送")
    sys.exit(1)
tx, ty, ttext, tconf = tp
print(f"步骤7: 找到 '{ttext}' @ ({tx},{ty}) conf={tconf:.2f}")

print("步骤8: 点击瞬间传送")
tap((tx, ty)); time.sleep(3.0)

print("=== Phase 0 完成，已传送到铁1入口 ===")
