"""通用流程任务 —— 基于图片模板的步骤式自动化"""
import time
import os
from tasks.base_task import BaseTask
from airtest.core.api import touch, exists, Template


class FlowTask(BaseTask):
    """
    按顺序执行图片模板匹配+点击的流程任务。
    适用于：跑环、副本、抓宠等一切"找图→点击→等待→下一个图"的模式。

    用法：
        task = FlowTask(
            name="跑环",
            steps=[
                {"template": "templates/quest/accept.png", "wait": 2.0, "desc": "点接受任务"},
                {"template": "templates/quest/track.png",  "wait": 1.0, "desc": "点追踪"},
                {"template": "templates/quest/npc.png",    "wait": 3.0, "desc": "等到达NPC"},
                {"template": "templates/quest/done.png",   "wait": 1.0, "desc": "点完成"},
            ],
            loop=True
        )
    """

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def __init__(self, name: str, steps: list[dict], loop: bool = True):
        """
        steps: [{"template": "路径", "wait": 等待秒数, "desc": "描述"}, ...]
        loop: True 则循环执行
        """
        super().__init__(name=name)
        self.steps = steps
        self.loop = loop

    def run(self):
        self.log(f"{self.name} 启动，共 {len(self.steps)} 个步骤")
        while self._running:
            for i, step in enumerate(self.steps):
                if not self._running:
                    break
                tmpl_path = os.path.join(self.BASE_DIR, step["template"])
                wait_sec = step.get("wait", 2.0)
                desc = step.get("desc", f"步骤{i+1}")

                self.log(f"  [{i+1}/{len(self.steps)}] {desc} ...")

                if not os.path.exists(tmpl_path):
                    self.log(f"    模板不存在: {step['template']}，跳过")
                    time.sleep(wait_sec)
                    continue

                tmpl = Template(tmpl_path)
                pos = exists(tmpl)
                if pos:
                    touch(pos)
                    self.log(f"    点击 ({int(pos[0])}, {int(pos[1])})")
                else:
                    self.log(f"    未找到，等待 {wait_sec}s")

                time.sleep(wait_sec)

            if not self.loop:
                self.log(f"{self.name} 完成")
                break
