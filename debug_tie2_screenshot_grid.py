# -*- coding: utf-8 -*-
"""铁2 截图当前画面 → 画坐标网格 → 弹出图片"""
import sys, os, time, subprocess
import numpy as np
import cv2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
SERIAL = "127.0.0.1:16480"
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"

ts = time.strftime("%H%M%S")
shot = os.path.join(LOG_DIR, f"screenshot_tie2_{ts}.png")
with open(shot, "wb") as f:
    subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                   stdout=f, stderr=subprocess.DEVNULL, timeout=5)
print(f"截图保存: {shot}")

with open(shot, "rb") as f:
    data = f.read()
img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
h, w = img.shape[:2]
print(f"分辨率: {w} x {h}")

step = 100
for x in range(0, w, step):
    cv2.line(img, (x, 0), (x, h), (128, 128, 128), 1)
for y in range(0, h, step):
    cv2.line(img, (0, y), (w, y), (128, 128, 128), 1)

font = cv2.FONT_HERSHEY_SIMPLEX
for x in range(0, w, step):
    for y in range(0, h, step):
        cv2.putText(img, f"({x},{y})", (x + 3, y + 15), font, 0.3, (0, 255, 0), 1)

cv2.line(img, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)
cv2.line(img, (0, h // 2), (w, h // 2), (255, 0, 0), 2)

out = os.path.join(LOG_DIR, "_tie2_grid_overlay.png")
cv2.imwrite(out, img)
print(f"网格图: {out}")
os.startfile(out)
print("已弹出网格图")
