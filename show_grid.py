"""给截图打上坐标网格，保存为新图片，方便人工对照"""
import sys, os, io, numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = sys.argv[1] if len(sys.argv) > 1 else None
if not path or not os.path.exists(path):
    # 找最新的截图
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    candidates = [f for f in os.listdir(log_dir) if f.startswith("screenshot_") and f.endswith(".png")]
    if candidates:
        candidates.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)), reverse=True)
        path = os.path.join(log_dir, candidates[0])
        print(f"使用最新截图: {candidates[0]}")
    else:
        print("没有找到截图"); sys.exit(1)

# 中文路径兜底
import cv2
with open(path, "rb") as f:
    data = f.read()
img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
h, w = img.shape[:2]
print(f"分辨率: {w} x {h}")
print()

# 画网格和坐标
step = 100
for x in range(0, w, step):
    cv2.line(img, (x, 0), (x, h), (128, 128, 128), 1)
for y in range(0, h, step):
    cv2.line(img, (0, y), (w, y), (128, 128, 128), 1)

# 在交叉点标注坐标
font = cv2.FONT_HERSHEY_SIMPLEX
for x in range(0, w, step):
    for y in range(0, h, step):
        label = f"({x},{y})"
        cv2.putText(img, label, (x + 3, y + 15), font, 0.3, (0, 255, 0), 1)

# 标出常用参考线
cv2.line(img, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)  # 垂直中线
cv2.line(img, (0, h // 2), (w, h // 2), (255, 0, 0), 2)  # 水平中线

out_path = os.path.join(os.path.dirname(path), "_grid_overlay.png")
cv2.imwrite(out_path, img)
print(f"已保存网格图: {out_path}")
print()
print("参考坐标（1080x1920）：")
print(f"  屏幕中心: ({w // 2}, {h // 2})")
print(f"  中心偏上: ({w // 2}, {h // 3})")
print(f"  中心偏下: ({w // 2}, {h * 2 // 3})")
print(f"  对话框第二个选项通常在屏幕中下部")
