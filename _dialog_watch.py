# -*- coding: utf-8 -*-
"""监听设备画面，抓到"按5键"对话对话框就保存截图+打印 bbox，用于实测对话框位置与OCR能力"""
import sys, time, os, io, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, r"E:\DATA\xunqinol_script")

import numpy as np
from PIL import Image
from core.ocr_client import get_ocr_client

SERIAL = "127.0.0.1:16416"
ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
OUT = r"E:\DATA\xunqinol_script\_dialog_watch"
os.makedirs(OUT, exist_ok=True)

reader = get_ocr_client()


def screencap():
    r = subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       capture_output=True, timeout=10)
    if not r.stdout:
        return None
    return np.array(Image.open(io.BytesIO(r.stdout)).convert("RGB"))


print("OCR 预热...", flush=True)
reader.readtext(np.zeros((80, 80, 3), dtype=np.uint8))
print("开始监控，Ctrl+C 停止", flush=True)

KW = ["按5键", "按5", "5键"]
while True:
    arr = screencap()
    if arr is None:
        print(f"[{time.strftime('%H:%M:%S')}] screencap 失败", flush=True)
        time.sleep(1.0)
        continue
    t0 = time.time()
    res = reader.readtext(arr)
    dt = time.time() - t0
    hits = []
    for r in res:
        text = r[1]
        if any(k in text for k in KW):
            box = r[0]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            hits.append((r[2], int(min(xs)), int(max(xs)), int(min(ys)), int(max(ys)), text))
    ts = time.strftime("%H%M%S")
    if hits:
        fn = os.path.join(OUT, f"dialog_{ts}.png")
        Image.fromarray(arr).save(fn)
        print(f"[{time.strftime('%H:%M:%S')}] ★命中 {len(hits)}条 → {fn}", flush=True)
        for c, x1, x2, y1, y2, text in hits:
            print(f"    conf={c:.2f} x[{x1},{x2}] y[{y1},{y2}] {text!r}", flush=True)
    else:
        print(f"[{time.strftime('%H:%M:%S')}] 无命中 (OCR {dt*1000:.0f}ms)", flush=True)
    time.sleep(0.3)
