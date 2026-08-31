"""天渊一层 剩余步骤调试：接取任务 → 自动遇怪一次 → 取消 → 找天渊使者寻路 → 提交任务"""
import time
import sys
import os

import debug_tianyuan_step1 as d

# ── 坐标 (1080x1920) ──────────────────────
KEY5 = (150, 1590)          # 数字键5 对话/接取/提交
KEY0 = (950, 1590)          # 数字键0 自动遇怪切换(toggle)
STAR_KEY = (150, 1790)      # *号键 一键接取/提交


def check_popup_text(keyword, cx, cy, half_w, half_h):
    """局部OCR检测短命弹窗文字(adb截图，尽力抓)"""
    arr = d.screenshot()
    if arr is None:
        return False
    h, w = arr.shape[:2]
    x1, x2 = max(0, cx - half_w), min(w, cx + half_w)
    y1, y2 = max(0, cy - half_h), min(h, cy + half_h)
    try:
        rs = d.ocr(arr[y1:y2, x1:x2, :])
    except Exception:
        return False
    for r in rs:
        if r[2] >= 0.1 and keyword in r[1]:
            return True
    return False


def check_cancel_popup():
    """检测取消弹窗：'状态取消'/'取消'(窄横条区域 x[450,720] y[640,750])"""
    arr = d.screenshot()
    if arr is None:
        return False
    h, w = arr.shape[:2]
    try:
        rs = d.ocr(arr[640:min(h, 750), 450:min(w, 720), :])
    except Exception:
        return False
    for r in rs:
        text = r[1]
        if r[2] >= 0.1 and ("状态取消" in text or "取消" in text):
            return True
    return False


def accept_quest():
    print("── 接取任务: 键5→键5→* ──", flush=True)
    d.tap(KEY5, "键5对话")
    time.sleep(0.8)
    d.tap(KEY5, "键5接取")
    time.sleep(0.8)
    d.tap(STAR_KEY, "*号一键接取")
    time.sleep(3.0)
    print("  接取任务完成", flush=True)


def auto_battle_once():
    print("── 自动遇怪一次 ──", flush=True)
    d.tap(KEY0, "键0开启自动遇怪")
    started = False
    t0 = time.time()
    while time.time() - t0 < 2.0:
        if check_popup_text("处于自动遇怪", 500, 695, 200, 55):
            print("  已确认开启: '你现在处于自动遇怪状态!'", flush=True)
            started = True
            break
        time.sleep(0.15)
    if not started:
        print("  [警告] 自动遇怪开启未确认成功", flush=True)

    battles = 0
    while battles < 1:
        if d.is_in_battle():
            battles += 1
            print(f"  第{battles}场战斗...", flush=True)
            d.wait_battle_end()
            print(f"  第{battles}场结束!", flush=True)
        time.sleep(d.BATTLE_CHECK_INTERVAL)

    d.tap(KEY0, "键0取消自动遇怪")
    cancelled = False
    t0 = time.time()
    while time.time() - t0 < 2.0:
        if check_cancel_popup():
            print("  已确认取消: '自动遇怪状态取消!'", flush=True)
            cancelled = True
            break
        time.sleep(0.15)
    if not cancelled:
        print("  [警告] 取消未确认成功", flush=True)

    for i in range(2):
        time.sleep(2.0)
        if d.is_in_battle():
            print(f"  残留战斗(第{i + 1}场)，等待结束...", flush=True)
            d.wait_battle_end()
        else:
            break
    print("  自动遇怪已取消", flush=True)


def submit_quest():
    print("── 提交任务: 键5→键5→*→12s ──", flush=True)
    d.tap(KEY5, "键5对话")
    time.sleep(0.8)
    d.tap(KEY5, "键5提交")
    time.sleep(0.8)
    d.tap(STAR_KEY, "*号提交")
    time.sleep(12.0)
    print("  提交任务完成", flush=True)


if __name__ == "__main__":
    accept_quest()
    auto_battle_once()
    d.npc_phase(d.TARGET_NPC)
    submit_quest()
