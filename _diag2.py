# -*- coding: utf-8 -*-
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

from core.ocr_client import get_ocr_client
reader = get_ocr_client()

for i in range(5):
    r = subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       capture_output=True, timeout=8)
    arr = np.asarray(Image.open(io.BytesIO(r.stdout)).convert("RGB"))
    h, w = arr.shape[:2]
    cx, cy, R = 950, 110, 120
    crop = arr[max(0, cy - R):min(h, cy + R), max(0, cx - R):min(w, cx + R)]
    rc = [(round(rr[2], 2), rr[1]) for rr in reader.readtext(crop, mag_ratio=1.0)]
    rf = reader.readtext(arr, mag_ratio=2)
    top = [(round(rr[2], 2), rr[1]) for rr in rf if rr[0][0][1] < 220 and rr[2] > 0.4]
    print(f"frame{i}: crop={rc}  top={top}")
    time.sleep(0.5)
