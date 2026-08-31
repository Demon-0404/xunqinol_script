# -*- coding: utf-8 -*-
"""铁4(魔界之门) Phase 1 调试：按键对话进入副本 → 周围列表找石碑"""
import sys, os, time, subprocess
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
LOG_DIR = os.path.join(BASE_DIR, "logs")

SERIAL = "127.0.0.1:16480"
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"

KEY5 = (150, 1590)          # 数字键5 确认/对话
KEY_STAR = (150, 1790)      # *号键 一键接取
ENTER_CONFIRM = (100, 1200) # 确认进入/缴费进入

NEARBY_BTN = (350, 1780)    # 周围列表按钮
NPC_TAB = (750, 250)        # NPC标签
ROW_X = 180
ROW_Y_START = 450
ROW_SPACING = 120
ROW_COUNT = 7
NEXT_PAGE = (520, 1330)
AUTO_PATHFIND = (500, 660)
PANEL_TITLE_CHECK = (500, 100)
PANEL_TITLE_SPREAD = 200


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


def get_reader():
    from core.ocr_client import get_ocr_client
    return get_ocr_client()


def map_name(arr):
    crop = arr[50:200, 830:1040, :]
    try:
        res = get_reader().readtext(crop, mag_ratio=1)
    except Exception:
        return ""
    return "".join(r[1] for r in res if r[2] >= 0.2)


def dump_text(arr, title="识别到的文字", min_conf=0.2):
    print(f"--- {title} ---")
    res = get_reader().readtext(arr, mag_ratio=1)
    for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        if conf < min_conf:
            continue
        cx = int((bbox[0][0] + bbox[2][0]) / 2)
        cy = int((bbox[0][1] + bbox[2][1]) / 2)
        print(f"  ({cx},{cy}) conf={conf:.2f} '{text}'")
    return res


def check_text_at(keyword, center, spread):
    arr = screenshot()
    if arr is None:
        return False
    h, w = arr.shape[:2]
    x, y = center
    y1, y2 = max(0, y - spread), min(h, y + spread)
    x1, x2 = max(0, x - spread), min(w, x + spread)
    crop = arr[y1:y2, x1:x2, :]
    try:
        results = get_reader().readtext(crop)
    except Exception:
        return False
    for r in results:
        if r[2] >= 0.1 and keyword in r[1]:
            return True
    return False


def open_npc_list():
    for retry in range(3):
        print(f"  打开周围列表... (尝试{retry + 1}/3)")
        tap(NEARBY_BTN, wait=1.5)
        if check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            print("  '周围列表'已打开")
            tap(NPC_TAB, wait=1.2)
            return True
        else:
            print("  未检测到'周围列表'，重试...")
    print("  周围列表面板打开失败")
    return False


def scan_npc_page():
    arr = screenshot()
    if arr is None:
        return []
    h, w = arr.shape[:2]
    results_list = []
    ts = time.strftime("%H%M%S")
    try:
        Image.fromarray(arr).save(os.path.join(LOG_DIR, f"_debug_tie4_npc_{ts}.png"))
    except Exception:
        pass
    for i in range(ROW_COUNT):
        yc = ROW_Y_START + i * ROW_SPACING
        y1, y2 = max(0, yc - 45), min(h, yc + 45)
        row = arr[y1:y2, 0:540, :]
        gray = np.mean(row, axis=2)
        dark_ratio = (gray < 80).mean()
        if dark_ratio < 0.02:
            continue
        for mag in [1, 3]:
            try:
                results = get_reader().readtext(row, mag_ratio=mag)
            except Exception:
                continue
            if not results:
                continue
            for r in sorted(results, key=lambda r: r[2], reverse=True):
                text, conf = r[1], r[2]
                if conf < 0.05:
                    continue
                print(f"    Row{i} Y={yc}: OCR='{text}' conf={conf:.2f}")
                results_list.append((text, yc))
                break
            break
    print(f"  [扫描NPC] 完成: {len(results_list)} 条")
    return results_list


print("=== 铁4 Phase 1: 按键对话进入副本 → 周围列表找石碑 ===")

print("--- Part A: 按键对话进入副本（6步，参考铁1/铁2）---")
print("步骤1: 键5 对话 (150,1590)")
tap(KEY5, wait=1.0)
print("步骤2: 键5 进入对话 (150,1590)")
tap(KEY5, wait=1.0)
print("步骤3: *号 一键接取 (150,1790)")
tap(KEY_STAR, wait=1.0)
print("步骤4: 键5 确认 (150,1590)")
tap(KEY5, wait=1.0)
print("步骤5: 确认进入 (100,1200)")
tap(ENTER_CONFIRM, wait=0.8)
print("步骤6: 缴费确认 (100,1200)")
tap(ENTER_CONFIRM, wait=3.0)

print("步骤7: 截图读地图名 + 界面OCR")
arr = screenshot()
print(f"  进入后地图名: '{map_name(arr)}'")
dump_text(arr, "进入后界面文字")

print("--- Part B: 打开周围列表找石碑 ---")
if open_npc_list():
    scan_npc_page()
else:
    print("  周围列表未打开，请查看上方界面OCR手动确认")

print("=== Phase 1 调试结束 ===")
