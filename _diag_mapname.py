# -*- coding: utf-8 -*-
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, r"E:\DATA\xunqinol_script")

import subprocess, io
import numpy as np
from PIL import Image

ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
SERIAL = "127.0.0.1:16416"

r = subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                   capture_output=True, timeout=8)
arr = np.asarray(Image.open(io.BytesIO(r.stdout)).convert("RGB"))
h, w = arr.shape[:2]
print("screen:", w, h)

from core.ocr_client import get_ocr_client
reader = get_ocr_client()

cx, cy = 950, 110
for R in (80, 120, 160):
    y1, y2 = max(0, cy - R), min(h, cy + R)
    x1, x2 = max(0, cx - R), min(w, cx + R)
    crop = arr[y1:y2, x1:x2]
    Image.fromarray(crop).save(rf"E:\DATA\xunqinol_script\logs\_crop_R{R}.png")
    for mag in (1.0, 2.0, 3.0):
        try:
            res = reader.readtext(crop, mag_ratio=mag)
        except Exception as e:
            print(f"R={R} mag={mag} ERR {e}")
            continue
        texts = [(round(r[2], 2), r[1]) for r in res]
        print(f"R={R} mag={mag} -> {texts}")
