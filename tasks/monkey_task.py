"""打泼猴任务 —— 点击泼猴→夺回玉帛→战斗→结算→循环"""
import time
from airtest.core.api import touch
from tasks.base_task import BaseTask


class MonkeyTask(BaseTask):
    """重复与泼猴对话，选择夺回玉帛，等待战斗结算"""

    WAIT_DIALOG = 0.5           # 点击泼猴后等对话框
    WAIT_CONFIRM = 0.1          # 夺回玉帛双击间隔
    WAIT_BATTLE = 4.4           # 战斗时间（避免误触）
    WAIT_SETTLE = 0.5           # 结算后等下一轮

    def __init__(self, monkey_pos=(500, 500), option_pos=(500, 700),
                 confirm_pos=(100, 1200)):
        super().__init__("打泼猴")
        self._monkey_pos = monkey_pos
        self._option_pos = option_pos
        self._confirm_pos = confirm_pos
        self._count = 0

    def run(self):
        self.log(f"泼猴:{self._monkey_pos} 夺回玉帛:{self._option_pos} 确认:{self._confirm_pos}")
        while self._running:
            # 1. 点击泼猴对话
            touch(self._monkey_pos)
            time.sleep(self.WAIT_DIALOG)

            # 2. 双击夺回玉帛确认
            touch(self._option_pos)
            time.sleep(self.WAIT_CONFIRM)
            touch(self._option_pos)
            self._count += 1

            # 3. 等待战斗 + 结算弹出
            time.sleep(self.WAIT_BATTLE)

            # 4. 点击确认关闭结算
            touch(self._confirm_pos)
            self.log(f"第{self._count}次完成，等待下一轮...")
            time.sleep(self.WAIT_SETTLE)

        self.log(f"结束，共完成 {self._count} 次")
