# -*- coding: utf-8 -*-
"""铁4(魔界之门) Phase 8 调试：接新任务 → Boss战 → 交任务 → 接新任务"""
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

KEY5 = (150, 1590)
KEY_STAR = (150, 1790)

# 战斗检测
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
    tmp = os.path.join(LOG_DIR, "_debug_tie4_tmp.png")
    with open(tmp, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=5)
    return np.array(Image.open(tmp))[:, :, :3]


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
    time.sleep(12.0 if is_boss else 1.0)


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


def accept_quest():
    if is_in_battle():
        print("  接取前遇怪! 等待战斗结束...")
        wait_battle_end()
    print("  接取任务: 5→5→*...")
    tap(KEY5, wait=0.8)
    tap(KEY5, wait=0.8)
    tap(KEY_STAR, "*号", wait=0.3)
    print("  *号接取完成")
    time.sleep(3.0)


def boss_battle():
    print("  等待 Boss 战触发...")
    t0 = time.time()
    triggered = False
    while time.time() - t0 < 30:
        if is_in_battle():
            triggered = True
            print("  检测到 Boss 战!")
            break
        time.sleep(0.5)
    if not triggered:
        print("  [警告] 30s 未检测到 Boss 战")
    wait_battle_end(is_boss=True)
    print("  Boss 战结束!")


print("=== 铁4 Phase 8: 接新任务 → Boss战 → 交任务 ===")

print("--- 第1段: 接新任务 ---")
accept_quest()

print("--- 第2段: Boss 战 ---")
boss_battle()

print("--- 第3段: 交任务 ---")
submit_quest()

print("=== Phase 8 完成 ===")
