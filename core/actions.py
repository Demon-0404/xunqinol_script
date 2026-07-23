"""基础操作封装"""
import time
from airtest.core.api import touch, swipe, snapshot, text


def tap_pos(x: int, y: int, duration: float = 0.1):
    """点击屏幕坐标"""
    touch((x, y), duration=duration)


def walk(direction: str, steps: int = 3, center_x: int = 100, center_y: int = 1600):
    """
    模拟摇杆走路，默认摇杆位置在屏幕左下区域。
    参数:
        direction: 'up' / 'down' / 'left' / 'right'
        steps: 走几步（每步约 0.3 秒）
        center_x, center_y: 摇杆中心坐标（绝对坐标，需要根据屏幕分辨率调整）
    """
    step_len = 80  # 摇杆拖动距离
    step_dur = 0.3  # 每步持续时间

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
        time.sleep(0.2)


def screenshot(filename: str = None):
    """截屏并保存"""
    return snapshot(filename=filename)


def wait_and_tap(template, timeout: float = 10, interval: float = 0.5):
    """等待图像出现在屏幕上，然后点击。需要提前截好的模板图。"""
    from airtest.core.api import wait, exists

    pos = wait(template, timeout=timeout, interval=interval)
    if pos:
        touch(pos)
        return True
    return False
