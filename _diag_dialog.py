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

frame = np.array(Image.open(r"E:\DATA\xunqinol_script\_dialog_watch\dialog_025719.png"))[:, :, :3]
h, w = frame.shape[:2]
print("截图尺寸:", (w, h))

reader = get_ocr_client()
res = reader.readtext(frame)
print(f"共{len(res)}条:")
for r in sorted(res, key=lambda r: r[0][0][1]):
    box = r[0]
    xs = [p[0] for p in box]; ys = [p[1] for p in box]
    print(f"  conf={r[2]:.2f}  x[{int(min(xs))},{int(max(xs))}] y[{int(min(ys))},{int(max(ys))}]  {r[1]!r}")
