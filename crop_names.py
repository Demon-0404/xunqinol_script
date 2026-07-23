"""黄色名字裁剪工具 —— 从截图中提取所有黄色名字区域
用法: python crop_names.py <楼层号>
例如: python crop_names.py 1
"""
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
from core.device import scan_available_devices, connect_device_by_serial, switch_device
from core.actions import screenshot

if len(sys.argv) < 2:
    print("用法: python crop_names.py <楼层号>")
    sys.exit(1)

floor = sys.argv[1]

# 连接设备
devices = scan_available_devices()
if not devices:
    print("未发现设备！")
    sys.exit(1)
target = devices[0]
ok = connect_device_by_serial(target["name"], target["serial"])
if not ok:
    print("连接失败！")
    sys.exit(1)
switch_device(target["name"])
print(f"已连接 {target['name']}")

# 截图
tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", f"_crop_tmp.png")
screenshot(tmp)

# 分析黄色区域
img = cv2.imread(tmp)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
lower = np.array([18, 80, 120])
upper = np.array([35, 255, 255])
mask = cv2.inRange(hsv, lower, upper)

kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# 保存每个黄色区域
save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "tower", f"floor{floor}")
os.makedirs(save_dir, exist_ok=True)

# 合并相近区域
rects = []
for cnt in contours:
    area = cv2.contourArea(cnt)
    if area < 60:
        continue
    x, y, w, h = cv2.boundingRect(cnt)
    # 稍微扩展边距
    x = max(0, x - 6)
    y = max(0, y - 4)
    w += 12
    h += 8
    rects.append((x, y, w, h))

# 按位置去重合并
def merge_rects(rects, threshold=40):
    if not rects:
        return []
    rects = sorted(rects, key=lambda r: (r[1], r[0]))
    merged = []
    used = [False] * len(rects)
    for i, (x, y, w, h) in enumerate(rects):
        if used[i]:
            continue
        mx, my, mw, mh = x, y, x + w, y + h
        for j in range(i + 1, len(rects)):
            if used[j]:
                continue
            x2, y2, w2, h2 = rects[j]
            if abs(y2 - y) < threshold and abs(x2 - x) < 100:
                mx = min(mx, x2)
                my = min(my, y2)
                mw = max(mw, x2 + w2)
                mh = max(mh, y2 + h2)
                used[j] = True
        merged.append((mx, my, mw - mx, mh - my))
    return merged

rects = merge_rects(rects)

print(f"\n发现 {len(rects)} 个黄色名字区域，已保存到: {save_dir}")
print("文件列表:")
for i, (x, y, w, h) in enumerate(rects):
    crop = img[y:y+h, x:x+w]
    fname = f"name_{i:02d}.png"
    cv2.imwrite(os.path.join(save_dir, fname), crop)
    print(f"  [{i}] {fname} 位置=({x},{y}) 尺寸={w}x{h}")

print(f"\n请根据游戏画面，按击杀顺序告诉我每个编号对应的怪物名。")
print(f"例如: [0]=散瘟鞭 [1]=离火剑 [3]=xxx(boss)")
