"""自动遇怪N场 —— 独立验证脚本

用法:
  python test_auto_battle.py [serial] [场数] [设备名]

默认: 天音 (127.0.0.1:16384) 遇怪2场

流程: 按键0开启自动遇怪 → 检测到N场战斗(视频流优先) → 按键0取消
"""
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)

SERIAL = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:16384"
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 2
DEVICE_NAME = sys.argv[3] if len(sys.argv) > 3 else "天音"

# 注册设备，使 _safe_touch 能通过 device_name 拿到 serial
from core import device as devmod
devmod._devices[DEVICE_NAME] = {"serial": SERIAL, "connected": True}

from tasks.dungeon_tie1_task import DungeonTie1Task

task = DungeonTie1Task(serial=SERIAL)
task.device_name = DEVICE_NAME
task._running = True

print(f"== 自动遇怪验证: {DEVICE_NAME} ({SERIAL}) 目标{COUNT}场 ==")

# 预热视频流，确认帧健康
frame = None
for _ in range(60):
    frame = task._stream_frame()
    if frame is not None:
        break
    time.sleep(0.1)
if frame is None:
    print("[错误] 视频流无帧，战斗检测将退化到 screencap")
else:
    print(f"流帧正常: shape={frame.shape} mean={frame.mean():.1f}")

print(f"初始战斗状态: {'战斗中' if task._is_in_battle() else '非战斗'}")

task._auto_battle_phase(COUNT)

task._running = False
print("== 完成 ==")
