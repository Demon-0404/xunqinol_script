"""走路 Demo 任务"""
import time
from tasks.base_task import BaseTask
from core.actions import walk_tap, walk_joystick


class WalkDemo(BaseTask):
    def __init__(self, direction: str = "right", steps: int = 5,
                 tap_x: int = 540, tap_y: int = 960, spread: int = 300,
                 use_joystick: bool = False,
                 joy_x: int = 150, joy_y: int = 1400):
        super().__init__(name="走路Demo")
        self.direction = direction
        self.steps = steps
        self.tap_x = tap_x
        self.tap_y = tap_y
        self.spread = spread
        self.use_joystick = use_joystick
        self.joy_x = joy_x
        self.joy_y = joy_y

    def run(self):
        self.log(f"开始走路: 方向={self.direction}, 步数={self.steps}, 模式={'摇杆' if self.use_joystick else '点击地面'}")
        while self._running:
            if self.use_joystick:
                walk_joystick(self.direction, steps=self.steps,
                              center_x=self.joy_x, center_y=self.joy_y)
            else:
                walk_tap(self.direction, steps=self.steps,
                         tap_x=self.tap_x, tap_y=self.tap_y, spread=self.spread)
            time.sleep(0.5)
