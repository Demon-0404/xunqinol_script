"""坐标拾取器 —— 点击图片任意位置，输出像素坐标"""
import cv2
import sys
import os

path = sys.argv[1] if len(sys.argv) > 1 else "logs/monkey_screen.png"
if not os.path.exists(path):
    print(f"文件不存在: {path}")
    sys.exit(1)

img = cv2.imread(path)
if img is None:
    # 中文路径兜底
    import numpy as np
    with open(path, "rb") as f:
        data = f.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

print(f"图片尺寸: {img.shape[1]} x {img.shape[0]}")
print("在图片上点击任意位置，按 ESC 退出")

def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"  坐标: ({x}, {y})")

cv2.namedWindow("pick", cv2.WINDOW_NORMAL)
cv2.resizeWindow("pick", 540, 960)
cv2.setMouseCallback("pick", on_mouse)

while True:
    cv2.imshow("pick", img)
    key = cv2.waitKey(20) & 0xFF
    if key == 27:
        break

cv2.destroyAllWindows()
