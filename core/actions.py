"""基础操作封装"""
import time
import random
from airtest.core.api import touch, swipe, snapshot


def tap_pos(x: int, y: int, duration: float = 0.05):
    """点击屏幕坐标"""
    touch((x, y), duration=duration)


def walk_joystick(direction: str, steps: int = 3,
                  center_x: int = 150, center_y: int = 1400):
    """模拟摇杆走路（备用方案）"""
    step_len = 80
    step_dur = 0.3
    offsets = {
        "up": (0, -step_len),
        "down": (0, step_len),
        "left": (-step_len, 0),
        "right": (step_len, 0),
    }
    if direction not in offsets:
        raise ValueError(f"direction 必须是 {list(offsets.keys())} 之一")
    dx, dy = offsets[direction]
    for _ in range(steps):
        end_x = center_x + dx
        end_y = center_y + dy
        swipe((center_x, center_y), (end_x, end_y), duration=step_dur)
        time.sleep(0.3)


def walk_tap(direction: str, steps: int = 3,
             tap_x: int = 540, tap_y: int = 960,
             spread: int = 300):
    """
    点击地面走路：在目标方向区域点击，角色自动寻路过去。
    direction: 'up'/'down'/'left'/'right'
    tap_x, tap_y: 屏幕中心点（默认 540,960 是 1080x1920 的中心）
    spread: 偏移距离（离中心多远点击）
    """
    offsets = {
        "up": (0, -spread),
        "down": (0, spread),
        "left": (-spread, 0),
        "right": (spread, 0),
    }
    if direction not in offsets:
        raise ValueError(f"direction 必须是 {list(offsets.keys())} 之一")

    dx, dy = offsets[direction]

    for i in range(steps):
        # 加一点随机偏移，避免点在同一位置
        rx = random.randint(-40, 40)
        ry = random.randint(-40, 40)
        target_x = tap_x + dx + rx
        target_y = tap_y + dy + ry
        touch((target_x, target_y))
        time.sleep(1.5)  # 等角色走到目标点


def screenshot(filename: str = None):
    """截屏并保存"""
    return snapshot(filename=filename)


def wait_and_tap(template, timeout: float = 10, interval: float = 0.5):
    """等待图像出现在屏幕上，然后点击"""
    from airtest.core.api import wait
    pos = wait(template, timeout=timeout, interval=interval)
    if pos:
        touch(pos)
        return True
    return False
