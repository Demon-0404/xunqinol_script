# -*- coding: utf-8 -*-
"""铁2(浮游) Phase 7 调试：点击(550,200)4次(间隔3s)走传送门，检测进入新地图"""
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

POS = (550, 200)       # 传送门方向点击位置
TIMES = 4              # 点击次数
WAIT_STEP = 3.0        # 每次点击间隔(走路)
MAP_NAME_CROP = (50, 200, 830, 1040)  # y1,y2,x1,x2 地图名区域

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


def get_map_name():
    arr = screenshot()
    if arr is None:
        return ""
    y1, y2, x1, x2 = MAP_NAME_CROP
    crop = arr[y1:y2, x1:x2, :]
    try:
        results = get_reader().readtext(crop, mag_ratio=1)
    except Exception:
        return ""
    return "".join(r[1] for r in results if r[2] >= 0.2)


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


def get_initial_map():
    for _ in range(5):
        name = get_map_name()
        if name:
            return name
        time.sleep(1.0)
    return ""


print(f"=== 铁2 Phase 7: 点击(550,200){TIMES}次(间隔{WAIT_STEP}s)，检测新地图 ===")

initial = get_initial_map()
print(f"初始地图: '{initial}'")

entered = False
for i in range(TIMES):
    # 战斗时不点击：遇怪先等战斗结束
    if is_in_battle():
        print(f"  第{i + 1}次前遇怪! 等待战斗结束(不计时)...")
        wait_battle_end()
    tap(POS, wait=WAIT_STEP)
    name = get_map_name()
    tag = ""
    if initial and name and name != initial:
        tag = "  [地图已变!]"
        entered = True
    print(f"  第{i + 1}次后 地图: '{name}'{tag}")
    if entered:
        break

print(f"=== Phase 7 完成 (进入新地图: {entered}) ===")
