# -*- coding: utf-8 -*-
"""phase5 单步调试: 裂影渊 -> 泣魔渊 传送门

用法:
  python _phase5_step.py 0   # 检测当前地图名
  python _phase5_step.py 1   # 点击传送门 (350,1100)
  python _phase5_step.py 2   # 等 3s 后检测地图名
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, r"E:\DATA\xunqinol_script")

import subprocess, io, time
import numpy as np
from PIL import Image

ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
SERIAL = "127.0.0.1:16416"
PORTAL_POS = (350, 1100)
MAP_NAME_POS = (950, 110)
MAP_NAME_RANGE = 120


def screenshot():
    r = subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       capture_output=True, timeout=8)
    if not r.stdout:
        return None
    return np.asarray(Image.open(io.BytesIO(r.stdout)).convert("RGB"))


_reader = None


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
    h, w = arr.shape[:2]
    cx, cy = MAP_NAME_POS
    crop = arr[max(0, cy - MAP_NAME_RANGE):min(h, cy + MAP_NAME_RANGE),
               max(0, cx - MAP_NAME_RANGE):min(w, cx + MAP_NAME_RANGE)]
    res = get_reader().readtext(crop)
    parts = []
    for r in res:
        if r[2] < 0.5:
            continue
        t = r[1]
        if any('一' <= ch <= '鿿' for ch in t):
            parts.append(t)
    return "".join(parts)


def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "0"
    if step == "0":
        print(time.strftime("[%H:%M:%S]"), f"当前地图: '{get_map_name()}'")
    elif step == "1":
        subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap",
                        str(PORTAL_POS[0]), str(PORTAL_POS[1])],
                       capture_output=True, timeout=8)
        print(time.strftime("[%H:%M:%S]"), f"点击传送门 {PORTAL_POS}")
    elif step == "2":
        time.sleep(3.0)
        print(time.strftime("[%H:%M:%S]"), f"3s 后地图: '{get_map_name()}'")
    else:
        print("用法: 0=检测地图 1=点击传送门 2=等3s检测")


if __name__ == "__main__":
    main()
