"""天渊一层 第一步调试：打开周围列表 → OCR找天渊使者 → 判断第一行 → 自动寻路"""
import time
import os
import subprocess
import sys
import numpy as np
import cv2
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16384"

# ── 坐标 (1080x1920) ──────────────────────
NEARBY_BTN = (350, 1780)         # 数字键7 → 周围列表
NPC_TAB = (750, 250)             # NPC标签
ROW_X = 180                      # 点击行内X
ROW_Y_START = 450                # 第一行Y
ROW_SPACING = 120                # 行间距
ROW_COUNT = 7                    # 一页最多行数
NEXT_PAGE = (520, 1330)          # 翻页
AUTO_PATHFIND = (500, 660)       # 自动寻路按钮
PANEL_TITLE_CHECK = (500, 100)   # "周围列表"检测
PANEL_TITLE_SPREAD = 200
TARGET_NPC = "天渊使者"

BATTLE_CHECK_INTERVAL = 0.3

# 战斗模板
TPL_DIR = os.path.join(BASE_DIR, "templates", "tianyuan")
_tpl_round = cv2.imread(os.path.join(TPL_DIR, "round.png"))
_tpl_manual = cv2.imread(os.path.join(TPL_DIR, "manual.png"))
_tpl_auto = cv2.imread(os.path.join(TPL_DIR, "auto.png"))


def tap(pos, desc=""):
    x, y = int(pos[0]), int(pos[1])
    print(f"  点击 {desc}({x},{y})", flush=True)
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap", str(x), str(y)],
                   capture_output=True, timeout=5)


def screenshot():
    tmp = os.path.join(LOG_DIR, "_tianyuan_step1_tmp.png")
    with open(tmp, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=8)
    return np.array(Image.open(tmp).convert("RGB"))


_reader = None


def ocr(arr, mag_ratio=1):
    global _reader
    if _reader is None:
        sys.path.insert(0, BASE_DIR)
        from core.ocr_client import get_ocr_client
        _reader = get_ocr_client()
    return _reader.readtext(arr, mag_ratio=mag_ratio)


def check_text_at(keyword, center, spread):
    arr = screenshot()
    h, w = arr.shape[:2]
    cx, cy = center
    y1, y2 = max(0, cy - spread), min(h, cy + spread)
    x1, x2 = max(0, cx - spread), min(w, cx + spread)
    for r in ocr(arr[y1:y2, x1:x2, :]):
        if r[2] >= 0.1 and keyword in r[1]:
            return True
    return False


def match_template(arr, tpl, cx, cy, spread):
    if tpl is None:
        return False
    h, w = arr.shape[:2]
    y1, y2 = max(0, cy - spread), min(h, cy + spread)
    x1, x2 = max(0, cx - spread), min(w, cx + spread)
    if y2 - y1 < tpl.shape[0] or x2 - x1 < tpl.shape[1]:
        return False
    roi = cv2.cvtColor(arr[y1:y2, x1:x2, :], cv2.COLOR_RGB2BGR)
    res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(res)
    return max_val > 0.7


def is_in_battle():
    arr = screenshot()
    if arr is None:
        return False
    return (match_template(arr, _tpl_auto, 976, 1450, 80) or
            match_template(arr, _tpl_manual, 976, 1450, 80))


def wait_battle_end():
    print("  等待战斗结束...", flush=True)
    miss = 0
    t0 = time.time()
    while time.time() - t0 < 60:
        if is_in_battle():
            miss = 0
        else:
            miss += 1
            if miss >= 2 and time.time() - t0 >= 3.0:
                print("  战斗结束", flush=True)
                return
        time.sleep(BATTLE_CHECK_INTERVAL)
    print("  战斗结束(超时)", flush=True)


def open_npc_list():
    for retry in range(3):
        tap(NEARBY_BTN, "数字键7周围列表")
        time.sleep(1.5)
        if check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            print("  '周围列表'已打开", flush=True)
        else:
            print("  未检测到'周围列表'，重试...", flush=True)
            time.sleep(0.5)
            continue
        tap(NPC_TAB, "NPC标签")
        time.sleep(1.2)
        if check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            print("  NPC面板已打开", flush=True)
            return True
        print("  NPC标签后标题消失，重试...", flush=True)
    print("  NPC面板多次重试失败", flush=True)
    return False


def scan_npc_page():
    arr = screenshot()
    if arr is None:
        return []
    h, w = arr.shape[:2]
    y_top = max(0, ROW_Y_START - 60)
    y_bot = min(h, ROW_Y_START + ROW_COUNT * ROW_SPACING + 60)
    crop = arr[y_top:y_bot, 0:560, :]
    try:
        rs = ocr(crop, mag_ratio=2)
    except Exception:
        return []
    best_by_row = {}
    for r in rs:
        text, conf, bbox = r[1], r[2], r[0]
        ys = [p[1] for p in bbox]
        cy_abs = y_top + (min(ys) + max(ys)) / 2
        yc = ROW_Y_START + round((cy_abs - ROW_Y_START) / ROW_SPACING) * ROW_SPACING
        if abs(cy_abs - yc) > 50 or conf < 0.05:
            continue
        cur = best_by_row.get(yc)
        if cur is None or conf > cur[1]:
            best_by_row[yc] = (text, conf)
    results = []
    for yc in sorted(best_by_row):
        name, conf = best_by_row[yc]
        print(f"    Row Y={yc}: '{name}' ({conf:.2f})", flush=True)
        results.append((name, yc))
    return results


def find_npc(target):
    print(f"  查找'{target}'...", flush=True)
    open_npc_list()
    npcs = scan_npc_page()
    for name, y in npcs:
        # 天渊使者 = "渊"+"使" 同时出现：
        # 排除"天渊传送师"(无"使") 和 "镇龙使者"(无"渊")
        if "渊" in name and "使" in name:
            print(f"  找到: '{name}' @ Y={y}", flush=True)
            return (name, y)
    print(f"  未找到'{target}'", flush=True)
    return None


def npc_phase(target):
    result = find_npc(target)
    if result is None:
        print(f"  未找到{target}，跳过", flush=True)
        return
    name, y = result
    print(f"  点击NPC: '{name}' @ Y={y}", flush=True)
    tap((ROW_X, y), "NPC行")
    time.sleep(0.5)
    if y != ROW_Y_START:
        tap((ROW_X, y), "NPC行(再点一次，非第一行)")
        time.sleep(0.5)
    tap(AUTO_PATHFIND, "自动寻路")
    time.sleep(0.3)
    print("  自动寻路中(监测战斗)...", flush=True)

    PATHFIND_WAIT = 20.0
    MAX_PATHFIND_ROUNDS = 4
    DIALOG_CHECK_AFTER = 2.0
    arrived = False
    for attempt in range(MAX_PATHFIND_ROUNDS):
        elapsed = 0.0
        while elapsed < PATHFIND_WAIT:
            if is_in_battle():
                print(f"  寻路中遇怪! (第{attempt + 1}次)", flush=True)
                wait_battle_end()
                print("  继续寻路...", flush=True)
                break
            if elapsed >= DIALOG_CHECK_AFTER and check_dialog_popup():
                print(f"  检测到对话弹窗，已到达{target}", flush=True)
                arrived = True
                break
            time.sleep(BATTLE_CHECK_INTERVAL)
            elapsed += BATTLE_CHECK_INTERVAL
        else:
            print("  寻路完成", flush=True)
            arrived = True
        if arrived:
            break
    if not arrived:
        print(f"  寻路等待达上限({MAX_PATHFIND_ROUNDS}次)", flush=True)
    if is_in_battle():
        wait_battle_end()
    print(f"  到达{target}", flush=True)


def check_dialog_popup():
    arr = screenshot()
    if arr is None:
        return False
    h, w = arr.shape[:2]
    crop = arr[0:min(h, 800), 0:w, :]
    for r in ocr(crop):
        text = r[1]
        if r[2] >= 0.1 and ("按5键" in text or "按5" in text or "5键" in text):
            return True
    return False


if __name__ == "__main__":
    npc_phase(TARGET_NPC)
