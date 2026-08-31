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
path = r"C:\Users\26378\Desktop\vip3跳转提示.png"
img = np.asarray(Image.open(path).convert("RGB"))
h, w = img.shape[:2]
print(f"=== vip3跳转提示 ({w}x{h}) ===")
res = reader.readtext(img)
for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
    bbox, text, conf = r
    cx = int((bbox[0][0] + bbox[2][0]) / 2)
    cy = int((bbox[0][1] + bbox[2][1]) / 2)
    print(f"({cx},{cy}) conf={conf:.2f}  {text!r}")
