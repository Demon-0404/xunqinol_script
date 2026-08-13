"""任务工作进程 —— 每个任务在独立 Python 进程中运行，避免 GIL 卡 UI。

协议:
  stdin:  第 1 行 = JSON 任务规格；之后发送 "STOP" 停止任务
  stdout: 每行一条日志（由 BaseTask.log() 输出）
"""
import sys
import os
import json
import threading
import time

# 强制 utf-8 + 行缓冲（Windows 管道默认 GBK/块缓冲会导致乱码和延迟）
# 用 reconfigure 而不是重新包一层 TextIOWrapper，避免双重包装同一缓冲区导致 stdout 损坏
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def build_task(spec: dict):
    """根据任务规格构造任务实例"""
    t = spec["task_type"]
    serial = spec.get("serial", "")
    p = spec.get("params", {})

    if t == "walk":
        from tasks.walk_demo import WalkDemo
        return WalkDemo(**p)
    if t == "quest":
        from tasks.flow_task import FlowTask
        return FlowTask("跑环", p["steps"], loop=p["loop"])
    if t == "pet":
        from tasks.flow_task import FlowTask
        return FlowTask("抓宠物", p["steps"], loop=p["loop"])
    if t == "dungeon":
        from tasks.dungeon_task import DungeonTask
        return DungeonTask(dungeon_id=p["dungeon_id"], rounds=p["rounds"], serial=serial)
    if t == "dungeon100":
        from tasks.dungeon100_task import Dungeon100Task
        return Dungeon100Task(serial=serial)
    if t == "crystal":
        from tasks.crystal_task import CrystalTask
        return CrystalTask(serial=serial)
    if t == "tower":
        from tasks.tower_task import TowerTask
        return TowerTask(serial=serial)
    if t == "chumo":
        from tasks.chumo_task import ChumoTask
        return ChumoTask(serial=serial)
    if t == "smith":
        from tasks.smith_task import SmithTask
        task = SmithTask()
        task.WAIT_ROUND = p.get("interval", 1.2)
        return task
    if t == "monkey":
        from tasks.monkey_task import MonkeyTask
        task = MonkeyTask()
        task.WAIT_BATTLE = p.get("wait_battle", 4.4)
        return task
    raise ValueError(f"unknown task_type: {t}")


def main():
    spec_line = sys.stdin.readline()
    if not spec_line:
        return
    spec = json.loads(spec_line)
    device_name = spec.get("device_name", "")
    serial = spec.get("serial", "")

    from core.device import connect_device_by_serial
    if serial:
        connect_device_by_serial(device_name, serial)

    task = build_task(spec)
    task.device_name = device_name

    # 不设 log 回调：BaseTask.log() 内部已 print 到 stdout
    finished = threading.Event()
    task.set_finish_callback(finished.set)
    task.start()

    def monitor():
        for line in sys.stdin:
            cmd = line.strip().upper()
            if cmd == "STOP":
                task.stop()
                break

    threading.Thread(target=monitor, daemon=True).start()

    while not finished.is_set():
        time.sleep(0.1)

    # 等 daemon 任务线程把最后几行日志刷完
    time.sleep(0.3)


if __name__ == "__main__":
    main()
