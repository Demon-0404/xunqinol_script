"""走路 Demo 任务"""
import time
from tasks.base_task import BaseTask
from core.actions import walk as do_walk


class WalkDemo(BaseTask):
    def __init__(self, direction: str = "right", steps: int = 5,
                 joy_x: int = 100, joy_y: int = 1600):
        super().__init__(name="走路Demo")
        self.direction = direction
        self.steps = steps
        self.joy_x = joy_x
        self.joy_y = joy_y

    def run(self):
        self.log(f"开始走路: 方向={self.direction}, 步数={self.steps}")
        while self._running:
            do_walk(self.direction, steps=self.steps,
                    center_x=self.joy_x, center_y=self.joy_y)
            time.sleep(0.5)
