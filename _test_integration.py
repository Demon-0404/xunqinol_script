"""冒烟测试：验证副本任务 _screenshot_arr 走流路径"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from tasks.dungeon_tie1_task import DungeonTie1Task

SERIAL = "127.0.0.1:16384"  # 天音

t = DungeonTie1Task(serial=SERIAL)

# 第一次调用：会启动流(约1-2s)，流首帧未到则回退 screencap
t0 = time.time()
arr = t._screenshot_arr()
print(f"第1次 _screenshot_arr: {time.time()-t0:.2f}s  shape={None if arr is None else arr.shape}")

# 等流首帧
time.sleep(2.0)

# 连续测 5 次耗时，应该都在毫秒级（走流缓存帧）
times = []
for i in range(5):
    t0 = time.time()
    arr = t._screenshot_arr()
    times.append(time.time() - t0)
print(f"流路径 _screenshot_arr 5次: avg={np.mean(times)*1000:.1f}ms  shape={None if arr is None else arr.shape}")

# 验证 _is_in_battle 走流
t0 = time.time()
in_battle = t._is_in_battle()
print(f"_is_in_battle: {(time.time()-t0)*1000:.1f}ms  result={in_battle}")

# 验证帧内容是 RGB（非 None、尺寸对）
if arr is not None:
    print(f"帧 shape={arr.shape} dtype={arr.dtype} R均值={arr[:,:,0].mean():.0f} G={arr[:,:,1].mean():.0f} B={arr[:,:,2].mean():.0f}")
print("=== done ===")
