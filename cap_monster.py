"""单怪名字采集工具 —— 通过玩家绿色名字定位，找最近的黄色名字
用法: python cap_monster.py <楼层>-<序号> [设备名]
例如: python cap_monster.py 1-01 猛士
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
    print("用法: python cap_monster.py <楼层>-<序号> [设备名]")
    sys.exit(1)

label = sys.argv[1]
want_device = sys.argv[2] if len(sys.argv) > 2 else None

# 连接设备
import subprocess
adb = os.environ.get("ANDROID_ADB", "adb")
r = subprocess.run([adb, "devices"], capture_output=True, text=True, encoding="utf-8", errors="replace")
online = [l.split("\t")[0] for l in r.stdout.strip().split("\n")[1:] if "\tdevice" in l]

devices = scan_available_devices()
if not devices:
    print("未发现设备！")
    sys.exit(1)

target = None
if want_device:
    for d in devices:
        if d["name"] == want_device:
            # 优先用7555
            port = "127.0.0.1:7555" if "127.0.0.1:7555" in online else d["serial"]
            target = {"name": d["name"], "serial": port}
            break
    if not target:
        print(f"未找到设备 '{want_device}'，可用: {[d['name'] for d in devices]}")
        sys.exit(1)
else:
    port = online[0] if online else "127.0.0.1:7555"
    target = {"name": "设备", "serial": port}

ok = connect_device_by_serial(target["name"], target["serial"])
switch_device(target["name"])
print(f"已连接 {target['name']}")

# 截图
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
tmp = os.path.join(BASE_DIR, "logs", "_monster_tmp.png")
screenshot(tmp)

img = cv2.imread(tmp)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# ── 找玩家绿色名字 ──────────────────────
green_lower = np.array([35, 80, 80])
green_upper = np.array([85, 255, 255])
green_mask = cv2.inRange(hsv, green_lower, green_upper)
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)

g_contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
player_pos = None
if g_contours:
    best_g = max(g_contours, key=cv2.contourArea)
    gx, gy, gw, gh = cv2.boundingRect(best_g)
    player_pos = (gx + gw // 2, gy + gh // 2)
    print(f"玩家位置: ({player_pos[0]}, {player_pos[1]})")
else:
    # 绿色没找到，用屏幕中心兜底
    player_pos = (img.shape[1] // 2, img.shape[0] // 2)
    print(f"未检测到绿色名字，用屏幕中心兜底")

# ── 找黄色怪物/NPC名字 ──────────────────
yellow_lower = np.array([18, 80, 120])
yellow_upper = np.array([35, 255, 255])
yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
yellow_mask = cv2.morphologyEx(yellow_mask, cv2.MORPH_CLOSE, kernel)
yellow_mask = cv2.morphologyEx(yellow_mask, cv2.MORPH_OPEN, kernel)

y_contours, _ = cv2.findContours(yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

if not y_contours:
    print("未检测到黄色名字!")
    sys.exit(1)

# 合并去重，按距离玩家位置排序
def merge_targets(contours, threshold=50):
    rects = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 50:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        rects.append({"x": x, "y": y, "w": w, "h": h, "area": area,
                       "cx": x + w // 2, "cy": y + h // 2})
    rects.sort(key=lambda r: -r["area"])
    merged = []
    for r in rects:
        too_close = False
        for m in merged:
            if abs(r["cx"] - m["cx"]) < threshold and abs(r["cy"] - m["cy"]) < 30:
                too_close = True
                break
        if not too_close:
            merged.append(r)
    # 按离玩家距离排序
    px, py = player_pos
    merged.sort(key=lambda r: abs(r["cx"] - px) + abs(r["cy"] - py))
    return merged

targets = merge_targets(y_contours)

save_dir = os.path.join(BASE_DIR, "templates", "tower", "names")
os.makedirs(save_dir, exist_ok=True)

print(f"\n检测到 {len(targets)} 个黄色名字 (按离玩家距离排序):")
for i, t in enumerate(targets):
    x, y, w, h = t["x"] - 6, t["y"] - 3, t["w"] + 12, t["h"] + 6
    x = max(0, x); y = max(0, y)
    crop = img[y:y+h, x:x+w]

    if i == 0:
        fname = f"{label}.png"
    else:
        fname = f"{label}_{i+1}.png"

    path = os.path.join(save_dir, fname)
    cv2.imwrite(path, crop)
    dist = abs(t["cx"] - player_pos[0]) + abs(t["cy"] - player_pos[1])
    print(f"  [{i}] {fname}  距离玩家={dist}")

print(f"\n[{0}] 是离玩家最近的，应该是你当前面对的怪物")
