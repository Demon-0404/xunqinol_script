# -*- coding: utf-8 -*-
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, r"E:\DATA\xunqinol_script")

import subprocess, io, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
SERIAL = "127.0.0.1:16416"

r = subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                   capture_output=True, timeout=8)
img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
arr = np.asarray(img)
W, H = img.size
print("size:", W, H)

# 1) 全屏 OCR 找传送门标记
from core.ocr_client import get_ocr_client
reader = get_ocr_client()
res = reader.readtext(arr, mag_ratio=2)
print("--- OCR ---")
for it in res:
    box, text, conf = it[0], it[1], it[2]
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    cx = int(sum(xs) / len(xs))
    cy = int(sum(ys) / len(ys))
    if conf >= 0.4:
        print(f"({cx},{cy}) conf={conf:.2f}  {text}")

# 2) 生成坐标网格图
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)
step = 100
for x in range(0, W + 1, step):
    od.line([(x, 0), (x, H)], fill=(0, 255, 255, 110), width=1)
for y in range(0, H + 1, step):
    od.line([(0, y), (W, y)], fill=(0, 255, 255, 110), width=1)

try:
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 22)
except Exception:
    font = ImageFont.load_default()

od.rectangle([0, 0, W, 30], fill=(0, 0, 0, 180))
od.rectangle([0, 0, 58, H], fill=(0, 0, 0, 180))
for x in range(0, W + 1, step):
    od.text((x + 3, 4), str(x), fill=(255, 255, 0, 255), font=font)
for y in range(0, H + 1, step):
    od.text((3, y + 4), str(y), fill=(255, 255, 0, 255), font=font)

img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
out = r"E:\DATA\xunqinol_script\logs\_grid.png"
img.save(out)
print("saved:", out)

try:
    os.startfile(out)
    print("opened via os.startfile")
except Exception as e:
    print("startfile failed:", e)
