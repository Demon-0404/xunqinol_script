# -*- coding: utf-8 -*-
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, r"E:\DATA\xunqinol_script")

import numpy as np
from PIL import Image
from core.ocr_client import get_ocr_client

reader = get_ocr_client()

for name in ["自动遇怪开启", "自动遇怪取消"]:
    img = np.asarray(Image.open(rf"C:\Users\26378\Desktop\{name}.png").convert("RGB"))
    h, w = img.shape[:2]
    scale = w / 1080.0
    cx, cy, spread = 540, 700, 200
    x1 = int(max(0, (cx - spread) * scale)); x2 = int(min(w, (cx + spread) * scale))
    y1 = int(max(0, (cy - spread) * scale)); y2 = int(min(h, (cy + spread) * scale))
    crop = img[y1:y2, x1:x2, :]
    print(f"=== {name} crop=({x1},{y1})-({x2},{y2}) ===")
    res = reader.readtext(crop)
    for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
        bbox, text, conf = r
        cx2 = int((bbox[0][0] + bbox[2][0]) / 2) + x1
        cy2 = int((bbox[0][1] + bbox[2][1]) / 2) + y1
        kw = "状态取消"
        hit = kw in text
        print(f"({cx2},{cy2}) conf={conf:.2f} {text!r} 含'{kw}'={hit}")
    print()
