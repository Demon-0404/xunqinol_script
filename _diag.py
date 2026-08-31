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

# 1) 视频流状态
try:
    from core.screen_stream import get_stream
    st = get_stream(SERIAL)
    print("video alive:", st.is_alive())
    f, ts = st.get_frame()
    print("frame:", None if f is None else f.shape, "ts_age:", round(time.time() - ts, 2) if ts else None)
except Exception as e:
    print("video diag err:", e)

# 2) 当前截图全屏 OCR
r = subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                   capture_output=True, timeout=8)
img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
arr = np.asarray(img)
print("screen shape:", arr.shape)

from core.ocr_client import get_ocr_client
reader = get_ocr_client()
res = reader.readtext(arr, mag_ratio=2)
lines = []
for it in res:
    box, text, conf = it[0], it[1], it[2]
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    cx = int(sum(xs) / len(xs))
    cy = int(sum(ys) / len(ys))
    lines.append((cy, cx, text, conf))
lines.sort()
for cy, cx, text, conf in lines:
    print(f"({cx},{cy}) conf={conf:.2f}  {text}")
