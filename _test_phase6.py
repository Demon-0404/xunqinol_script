# -*- coding: utf-8 -*-
"""phase6 传送门验证: 泣魔渊 -> 陨仙渊

逻辑(仿 phase5):
  - 点击传送门 (350,1100) 共 8 次, 每次间隔 3s
  - 期间不间断检测地图名是否含 '陨'/'仙' 单字, 命中立刻停止
  - 遇到战斗: 暂停点击和计时, 等战斗结束再重置 3s 计时继续
"""
import subprocess, io, time, os, sys
import numpy as np
import cv2
from PIL import Image

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, r"E:\DATA\xunqinol_script")

ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
SERIAL = "127.0.0.1:16416"
CLICK_SEQ = [(300, 1100)] * 5 + [(650, 1100)] * 3
MAP_NAME_POS = (950, 110)
MAP_NAME_RANGE = 120
MAX_CLICKS = 8
INTERVAL = 3.0
DONE_WAIT = 10.0
TARGET = "陨仙"
TEMPLATE_DIR = r"E:\DATA\xunqinol_script\templates\tianyuan"


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def tap(x, y):
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap",
                    str(int(x)), str(int(y))], capture_output=True, timeout=8)


def screenshot():
    r = subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       capture_output=True, timeout=8)
    if not r.stdout:
        return None
    return np.asarray(Image.open(io.BytesIO(r.stdout)).convert("RGB"))


_stream = None


def stream_frame():
    global _stream
    try:
        from core.screen_stream import get_stream
        _stream = get_stream(SERIAL)
        return _stream.get_frame()[0]
    except Exception:
        return None


def get_frame():
    f = stream_frame()
    if f is not None:
        return f
    return screenshot()


_reader = None


def get_reader():
    global _reader
    if _reader is None:
        from core.ocr_client import get_ocr_client
        _reader = get_ocr_client()
    return _reader


def get_map_name(verbose=False):
    arr = get_frame()
    if arr is None:
        return ""
    h, w = arr.shape[:2]
    cx, cy = MAP_NAME_POS
    y1, y2 = max(0, cy - MAP_NAME_RANGE), min(h, cy + MAP_NAME_RANGE)
    x1, x2 = max(0, cx - MAP_NAME_RANGE), min(w, cx + MAP_NAME_RANGE)
    crop = arr[y1:y2, x1:x2, :]
    try:
        results = get_reader().readtext(crop)
    except Exception:
        return ""
    parts = []
    raw = []
    for r in results:
        text, conf = r[1], r[2]
        raw.append((round(conf, 2), text))
        if conf < 0.5:
            continue
        if not any('一' <= ch <= '鿿' for ch in text):
            continue
        parts.append(text)
    if verbose:
        log("    [OCR raw]", raw, "-> parts", parts)
    return "".join(parts)


_tpl = None


def load_templates():
    global _tpl
    if _tpl is None:
        _tpl = {
            "round": cv2.imread(os.path.join(TEMPLATE_DIR, "round.png")),
            "manual": cv2.imread(os.path.join(TEMPLATE_DIR, "manual.png")),
            "auto": cv2.imread(os.path.join(TEMPLATE_DIR, "auto.png")),
        }


def match_template(arr, tpl, cx, cy, spread):
    h, w = arr.shape[:2]
    y1, y2 = max(0, cy - spread), min(h, cy + spread)
    x1, x2 = max(0, cx - spread), min(w, cx + spread)
    if y2 <= y1 or x2 <= x1:
        return False
    roi = arr[y1:y2, x1:x2, :]
    res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, _ = cv2.minMaxLoc(res)
    return maxv > 0.7


def is_in_battle():
    arr = get_frame()
    if arr is None:
        return False
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    load_templates()
    if match_template(bgr, _tpl["round"], 500, 200, 80):
        return True
    if match_template(bgr, _tpl["manual"], 1000, 1450, 80):
        return True
    if match_template(bgr, _tpl["auto"], 1000, 1450, 80):
        return True
    return False


def wait_battle_end():
    log("[战斗] 检测到战斗，暂停，等待结束...")
    miss = 0
    t0 = time.time()
    while True:
        if is_in_battle():
            miss = 0
        else:
            miss += 1
            if miss >= 2 and time.time() - t0 >= 3.0:
                break
        time.sleep(0.3)
    log("[战斗] 结束")


def main():
    log("=== phase6 传送门验证: 泣魔渊 -> 陨仙渊 ===")
    log("预热视频流...")
    f = stream_frame()
    log("视频流" + (f"就绪 {f.shape}" if f is not None else "不可用，用截图 fallback"))

    m0 = get_map_name(verbose=True)
    log(f"起始地图: '{m0}'")

    clicks = 0
    last_click = -1e9
    done_deadline = None

    try:
        while True:
            if is_in_battle():
                wait_battle_end()
                last_click = time.time()
                continue

            mn = get_map_name()
            if any(ch in mn for ch in TARGET):
                hit = next(ch for ch in TARGET if ch in mn)
                log(f"==> 检测到 '{hit}'，地图名 '{mn}'，立刻停止")
                break

            if clicks < len(CLICK_SEQ) and time.time() - last_click >= INTERVAL:
                pos = CLICK_SEQ[clicks]
                tap(*pos)
                clicks += 1
                last_click = time.time()
                log(f"传送门点击 {clicks}/{len(CLICK_SEQ)} @{pos}")
                get_map_name(verbose=True)
                if clicks >= len(CLICK_SEQ):
                    done_deadline = time.time() + DONE_WAIT
                    log(f"点满 {len(CLICK_SEQ)} 次，继续等传送动画 {DONE_WAIT}s...")

            if done_deadline and time.time() > done_deadline:
                log("等待传送动画超时")
                break

            time.sleep(0.3)
    except KeyboardInterrupt:
        log("用户中断")

    final = get_map_name(verbose=True)
    log(f"=== 结束，最终地图 '{final}' ===")


if __name__ == "__main__":
    main()
