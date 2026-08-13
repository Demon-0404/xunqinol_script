"""名匠石磨兑换任务 —— 与NPC对话→选第3项→连点确认→循环"""
import time
from tasks.base_task import BaseTask


class SmithTask(BaseTask):
    """重复与名匠NPC对话，兑换石磨"""

    WAIT_CLICK = 0.3
    WAIT_ROUND = 1.2

    STEPS = [
        (150, 1590),   # 与NPC对话
        (750, 1590),   # 选择第3项
        (150, 1590),   # 数字键5
        (150, 1590),   # 数字键5确定
        (150, 1590),   # 确认兑换成功
    ]

    def __init__(self):
        super().__init__("名匠石磨")
        self._count = 0

    def run(self):
        while self._running:
            for i, (x, y) in enumerate(self.STEPS):
                if not self._running:
                    break
                self._safe_touch((x, y))
                time.sleep(self.WAIT_CLICK)

            self._count += 1
            self.log_key(f"第{self._count}轮完成")
            time.sleep(self.WAIT_ROUND)

        self.log_key(f"结束，共完成 {self._count} 轮")
