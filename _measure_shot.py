import subprocess, time, os, sys
import numpy as np
from PIL import Image
import cv2

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "_measure_tmp.png")

def shot():
    args = [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"]
    with open(TMP, "wb") as f:
        subprocess.run(args, stdout=f, stderr=subprocess.DEVNULL, timeout=10)

# 1. 纯 screencap 耗时（写文件）
times = []
for _ in range(5):
    t = time.time()
    shot()
    times.append(time.time() - t)
print(f"screencap 纯截图 (5次): avg={np.mean(times):.3f}s  min={min(times):.3f}s  max={max(times):.3f}s")

# 2. 完整 _screenshot_arr 流程（截图 + PIL读 + 转numpy）
def full():
    shot()
    return np.array(Image.open(TMP))[:, :, :3]

times = []
for _ in range(5):
    t = time.time()
    arr = full()
    times.append(time.time() - t)
print(f"screencap+PIL+numpy (5次): avg={np.mean(times):.3f}s  shape={arr.shape}")

# 3. matchTemplate 在 ROI 上的耗时
arr = full()
arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
tpl = cv2.imread(r"E:\DATA\xunqinol_script\templates\tianyuan\round.png")
cx, cy, spread = 500, 200, 80
h, w = arr_bgr.shape[:2]
y1, y2 = max(0, cy-spread), min(h, cy+spread)
x1, x2 = max(0, cx-spread), min(w, cx+spread)
roi = arr_bgr[y1:y2, x1:x2, :]
times = []
for _ in range(20):
    t = time.time()
    r = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
    _, mv, _, _ = cv2.minMaxLoc(r)
    times.append(time.time() - t)
print(f"matchTemplate ROI(160x160)+tpl(120x120) (20次): avg={np.mean(times)*1000:.2f}ms  max_val={mv:.3f}")

# 4. cvtColor 全图耗时
times = []
for _ in range(20):
    t = time.time()
    cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    times.append(time.time() - t)
print(f"cvtColor 全图(1080x1920) (20次): avg={np.mean(times)*1000:.2f}ms")
