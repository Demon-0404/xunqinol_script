# -*- coding: utf-8 -*-
"""铁4(魔界之门) Phase 2 调试：找心魔交接 → 遇怪1次 → 找心魔交接"""
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

# NPC列表坐标
NEARBY_BTN = (350, 1780)     # 周围列表按钮
NPC_TAB = (750, 250)         # NPC标签
ROW_X = 180                  # 点击行内X
ROW_Y_START = 450            # 第一行Y
ROW_SPACING = 120            # 行间距
ROW_COUNT = 7                # 一页最多行数
NEXT_PAGE = (520, 1330)      # 翻页按钮
AUTO_PATHFIND = (500, 660)   # 自动寻路按钮
CANCEL_PANELS = [(950, 1200), (950, 1450)]
PANEL_TITLE_CHECK = (500, 100)
PANEL_TITLE_SPREAD = 200

KEY5 = (150, 1590)
KEY_STAR = (150, 1790)
KEY0 = (950, 1590)           # 数字键0 自动遇怪

# 战斗检测
ROUND_CHECK = (500, 200)
ROUND_RANGE = 80
ROUND_THRESHOLD = 0.85
MANUAL_CHECK = (1000, 1450)
MANUAL_RANGE = 80
MANUAL_THRESHOLD = 0.7

TARGET_NPC = "心魔"
BATTLE_COUNT = 1             # 遇怪1次

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


def get_reader():
    global _reader
    if _reader is None:
        from core.ocr_client import get_ocr_client
        _reader = get_ocr_client()
    return _reader


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


def dismiss_panels():
    for cx, cy in CANCEL_PANELS:
        if check_text_at("取消", (cx, cy), 100):
            print(f"  检测到误开面板 @({cx},{cy})，点击取消关闭")
            tap((cx, cy), wait=0.5)
            return True
    return False


def open_npc_list():
    for retry in range(3):
        print(f"  打开周围列表... (尝试{retry + 1}/3)")
        tap(NEARBY_BTN, wait=1.5)
        if check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            print("  '周围列表'已打开")
        else:
            print("  未检测到'周围列表'，尝试关闭误开面板...")
            dismiss_panels()
            time.sleep(0.5)
            continue
        tap(NPC_TAB, wait=1.2)
        return True
    print("  NPC面板多次重试失败")
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


def find_npc(target):
    for page in range(1, 5):
        print(f"  查找'{target}' — 第{page}页...")
        open_npc_list()
        npcs = scan_npc_page()
        for name, y in npcs:
            if target in name or name in target:
                print(f"  找到: '{name}' @ Y={y}")
                return (name, y)
            common = sum(1 for ch in name if ch in target)
            if common >= 1:
                print(f"  模糊匹配: '{name}' ~ '{target}' @ Y={y}")
                return (name, y)
        if page < 4:
            print(f"  第{page}页未找到，翻页...")
            tap(NEXT_PAGE, wait=0.8)
        else:
            print(f"  翻页{page}次仍未找到'{target}'")
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
    time.sleep(12.0 if is_boss else 1.0)


def npc_phase(target):
    if is_in_battle():
        print("  找NPC前遇怪! 等待战斗结束...")
        wait_battle_end()
    result = find_npc(target)
    if result is None:
        print(f"  [失败] 未找到{target}，跳过")
        return False
    name, y = result
    print(f"  点击NPC: '{name}' @ Y={y}")
    tap((ROW_X, y), wait=0.5)
    if y == ROW_Y_START:
        tap(KEY5, "键5", wait=0.3)
    else:
        tap(AUTO_PATHFIND, "自动寻路", wait=0.3)
        tap(KEY5, "键5", wait=0.3)
    print("  自动寻路中(监测战斗)...")
    PATHFIND_WAIT = 8.0
    MAX_PATHFIND_ROUNDS = 4
    for attempt in range(MAX_PATHFIND_ROUNDS):
        elapsed = 0.0
        while elapsed < PATHFIND_WAIT:
            if is_in_battle():
                print(f"  寻路中遇怪! (第{attempt + 1}次)")
                wait_battle_end()
                print("  继续寻路...")
                break
            time.sleep(0.3)
            elapsed += 0.3
        else:
            print("  寻路完成")
            break
    if is_in_battle():
        wait_battle_end()
    print(f"  到达 {target}")
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


def auto_battle(count):
    print(f"  按键0 开启自动遇怪 (目标{count}场)...")
    tap(KEY0, "键0", wait=1.0)
    battles = 0
    t0 = time.time()
    while battles < count and time.time() - t0 < 300:
        if is_in_battle():
            battles += 1
            print(f"  [战斗] 第{battles}场开始...")
            wait_battle_end()
            print(f"  [战斗] 第{battles}场结束")
        time.sleep(0.3)
    # 确保战斗已结束再点取消（按键0落在战斗界面会无效）
    if is_in_battle():
        print("  战斗未结束，等待本场结束再取消...")
        wait_battle_end()
    print(f"  按键0 取消自动遇怪 (共{battles}场)")
    tap(KEY0, "键0", wait=0.5)
    time.sleep(1.0)
    # 取消后确认无残留战斗
    for _ in range(10):
        if is_in_battle():
            print("  残留战斗! 等待结束...")
            wait_battle_end()
            break
        time.sleep(0.5)


print("=== 铁4 Phase 2: 找心魔交接 → 遇怪1次 → 找心魔交接 ===")

print("--- 第1段: 找心魔 → 提交 → 接取 ---")
if npc_phase(TARGET_NPC):
    submit_quest()
    accept_quest()

print("--- 第2段: 遇怪1次 ---")
auto_battle(BATTLE_COUNT)

print("--- 第3段: 再找心魔 → 提交 → 接取 ---")
if npc_phase(TARGET_NPC):
    submit_quest()
    accept_quest()

print("=== Phase 2 完成 ===")
