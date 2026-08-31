import time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.screen_stream import get_stream, ScreenStream
import numpy as np
import cv2

SERIAL = "127.0.0.1:16384"

st = get_stream(SERIAL)
print(f"alive={st.is_alive()} size={st.width}x{st.height}")

# 等第一帧
t0 = time.time()
while time.time() - t0 < 5:
    f, ts = st.get_frame()
    if f is not None:
        break
    time.sleep(0.05)
f, ts = st.get_frame()
print(f"first frame after {time.time()-t0:.2f}s, shape={None if f is None else f.shape}")

if f is None:
    print("NO FRAME")
    sys.exit(1)

# 测量帧率 (1s 内 seq 增量)
seq0 = st.get_frame_seq()
time.sleep(1.0)
seq1 = st.get_frame_seq()
print(f"fps ≈ {seq1 - seq0}")

# 测量 "拿最新帧" 耗时 (就是 get_frame 本身)
times = []
for _ in range(200):
    t = time.time()
    f, ts = st.get_frame()
    times.append(time.time() - t)
print(f"get_frame() 平均耗时: {np.mean(times)*1000:.3f}ms  max={max(times)*1000:.3f}ms")

# 测量 "拿一帧新帧" 耗时 (wait_fresh 后立即取帧)
times = []
for _ in range(50):
    seq = st.get_frame_seq()
    t = time.time()
    st.wait_fresh(seq, timeout=2.0)
    times.append(time.time() - t)
print(f"wait_fresh 新帧间隔: avg={np.mean(times)*1000:.1f}ms  max={max(times)*1000:.1f}ms")

# 端到端: 模拟 _is_in_battle 模板匹配
tpl = cv2.imread(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "tianyuan", "round.png"))
t = time.time()
f, ts = st.get_frame()
arr_bgr = cv2.cvtColor(f, cv2.COLOR_RGB2BGR)
cx, cy, spread = 500, 200, 80
h, w = arr_bgr.shape[:2]
y1, y2 = max(0, cy-spread), min(h, cy+spread)
x1, x2 = max(0, cx-spread), min(w, cx+spread)
roi = arr_bgr[y1:y2, x1:x2, :]
r = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
_, mv, _, _ = cv2.minMaxLoc(r)
print(f"取帧+cvtColor+matchTemplate 端到端: {(time.time()-t)*1000:.1f}ms  max_val={mv:.3f}")

# 保存一帧看内容
from PIL import Image
Image.fromarray(f).save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "_stream_frame.png"))
print("saved logs/_stream_frame.png")
print("=== done ===")
