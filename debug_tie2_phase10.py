# -*- coding: utf-8 -*-
"""铁2(浮游) Phase 10 调试：打开任务列表→找(副)解决之道→传送→提交任务"""
import sys, os, time, subprocess
import numpy as np
import cv2
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
LOG_DIR = os.path.join(BASE_DIR, "logs")

SERIAL = "127.0.0.1:16480"
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"

KEY1 = (350, 1590)        # 数字键1 打开任务列表
STEP_CONFIRM = (100, 1450)  # 确定按钮
TELEPORT = (500, 790)     # 瞬间传送按钮
KEY5 = (150, 1590)
KEY_STAR = (150, 1790)

TASK_KEYWORDS = ["解决之道", "解决", "之道"]

# 战斗检测（同铁1）
ROUND_CHECK = (500, 200)
ROUND_RANGE = 80
ROUND_THRESHOLD = 0.85
MANUAL_CHECK = (1000, 1450)
MANUAL_RANGE = 80
MANUAL_THRESHOLD = 0.7

_reader = None
_tpl_round = None
_tpl_manual = None


def tap(pos, desc="", wait=0.3):
    print(f"点击 {desc}{pos}")
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap",
                    str(pos[0]), str(pos[1])], capture_output=True, timeout=10)
    time.sleep(wait)


def screenshot():
    tmp = os.path.join(LOG_DIR, "_debug_tie2_tmp.png")
    with open(tmp, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=5)
    return np.array(Image.open(tmp))[:, :, :3]


def get_reader():
    global _reader
    if _reader is None:
        from core.ocr_client import get_ocr_client
        _reader = get_ocr_client()
    return _reader


def find_text_in_area(keyword, y_start, y_end, x_start=0, x_end=1080):
    arr = screenshot()
    if arr is None:
        return None
    try:
        res = get_reader().readtext(arr, mag_ratio=1)
    except Exception:
        return None
    for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        if conf < 0.3 or keyword not in text:
            continue
        cx = int((bbox[0][0] + bbox[2][0]) / 2)
        cy = int((bbox[0][1] + bbox[2][1]) / 2)
        if x_start <= cx <= x_end and y_start <= cy <= y_end:
            return (cx, cy)
    return None


def load_templates():
    global _tpl_round, _tpl_manual
    if _tpl_round is None:
        tpl_dir = os.path.join(BASE_DIR, "templates", "tianyuan")
        _tpl_round = cv2.imread(os.path.join(tpl_dir, "round.png"))
        _tpl_manual = cv2.imread(os.path.join(tpl_dir, "manual.png"))


def match_template(arr, tpl, cx, cy, spread, threshold=0.7):
    h, w = arr.shape[:2]
    y1, y2 = max(0, cy - spread), min(h, cy + spread)
    x1, x2 = max(0, cx - spread), min(w, cx + spread)
    if y2 <= y1 or x2 <= x1:
        return False
    roi = arr[y1:y2, x1:x2, :]
    result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return max_val > threshold


def is_in_battle():
    arr = screenshot()
    if arr is None:
        return False
    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    load_templates()
    if match_template(arr, _tpl_round, ROUND_CHECK[0], ROUND_CHECK[1], ROUND_RANGE, ROUND_THRESHOLD):
        return True
    if match_template(arr, _tpl_manual, MANUAL_CHECK[0], MANUAL_CHECK[1], MANUAL_RANGE, MANUAL_THRESHOLD):
        return True
    return False


def wait_battle_end(is_boss=False):
    miss = 0
    t0 = time.time()
    while miss < 3 and time.time() - t0 < 60:
        time.sleep(0.5)
        if is_in_battle():
            miss = 0
        else:
            miss += 1
    time.sleep(8.0 if is_boss else 1.0)


def quest_teleport():
    print("── 任务传送: 选中(副)解决之道→确定→瞬间传送 ──")
    if is_in_battle():
        print("  传送前遇怪! 等待战斗结束...")
        wait_battle_end()
    tap(KEY1, "任务列表(键1)", wait=1.5)
    pos = None
    for kw in TASK_KEYWORDS:
        pos = find_text_in_area(kw, 300, 1300)
        if pos:
            print(f"  用关键词'{kw}'找到任务")
            break
    if pos is None:
        print("  [失败] 未找到目标任务(解决之道)")
        return False
    cx, cy = pos
    print(f"  找到任务 @ ({cx},{cy})，点击选中")
    tap((cx, cy), wait=0.8)
    tap(STEP_CONFIRM, "确定", wait=0.8)
    tap(TELEPORT, "瞬间传送", wait=3.0)
    time.sleep(2.0)
    print("  传送完成")
    return True


def submit_quest():
    if is_in_battle():
        print("  提交前遇怪! 等待战斗结束...")
        wait_battle_end()
    print("  提交任务: 5→5→*...")
    tap(KEY5, wait=0.8)
    tap(KEY5, wait=0.8)
    tap(KEY_STAR, "*号", wait=0.3)
    print("  *号提交，等待12s结算...")
    time.sleep(12.0)


print("=== 铁2 Phase 10: 任务列表找解决之道→传送→提交 ===")
quest_teleport()
submit_quest()
print("=== Phase 10 完成 ===")
