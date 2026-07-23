"""玄兵塔任务 —— 模板匹配找怪 + 战斗流程，7层通关"""
import time
import os
import sys
from airtest.core.api import touch, exists, Template
from core.actions import screenshot
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(BASE_DIR, "templates", "tower")
NAME_DIR = os.path.join(TPL_DIR, "names")


def _name_tpl(filename: str, threshold: float = 0.6) -> Template:
    """加载怪物名字模板"""
    return Template(os.path.join(NAME_DIR, filename), threshold=threshold, rgb=True)


def _ui_tpl(filename: str, threshold: float = 0.75) -> Template:
    """加载 UI 模板"""
    return Template(os.path.join(TPL_DIR, filename), threshold=threshold)


class TowerTask(BaseTask):
    """玄兵塔自动清怪 —— 模板匹配怪物名字"""

    TOTAL_FLOORS = 7
    BATTLE_TIMEOUT = 35
    WALK_WAIT = 2.5
    SEARCH_SCAN_DELAY = 0.5

    def __init__(self):
        super().__init__("玄兵塔")
        self._floor = 0
        self._cleared = 0

    # ── 主循环 ────────────────────────────────

    def run(self):
        for floor in range(1, self.TOTAL_FLOORS + 1):
            if not self._running:
                break
            self._floor = floor
            self.log(f"══════ 第 {floor} 层 ══════")
            self._clear_floor(floor)

            if not self._running:
                break
            self._go_next_floor()

        if self._running:
            self.log(f"玄兵塔全部通关! 共击败 {self._cleared} 个怪物")

    def _clear_floor(self, floor: int):
        """按顺序匹配怪物模板，逐个击杀"""
        monsters = list(range(1, 10))  # 最多9只普通怪
        for idx in monsters:
            if not self._running:
                break

            name_file = f"monster_floor{floor}_{idx:02d}.png"
            tpl_path = os.path.join(NAME_DIR, name_file)
            if not os.path.exists(tpl_path):
                # 试 boss 模板
                boss_file = f"monster_floor{floor}_boss.png"
                if os.path.exists(os.path.join(NAME_DIR, boss_file)):
                    self.log(f"  普通怪模板已用完 ({idx-1}只)，开始打boss")
                    self._engage_by_template(boss_file)
                    break
                else:
                    self.log(f"  缺少模板 {name_file}，本层结束")
                    break

            self.log(f"  搜索 {name_file} ...")
            if self._engage_by_template(name_file):
                self._cleared += 1
                time.sleep(1.5)
            else:
                self.log(f"  未找到 {name_file}，可能已阵亡或模板有问题")
                # 继续尝试下一只

    # ── 单只怪物战斗流程 ───────────────────────

    def _find_and_tap(self, tpl: Template, timeout: float = 3.0,
                      interval: float = 0.3) -> bool:
        """轮询查找模板并点击，返回是否找到"""
        elapsed = 0.0
        while elapsed < timeout:
            if not self._running:
                return False
            pos = exists(tpl)
            if pos:
                touch(pos)
                return True
            time.sleep(interval)
            elapsed += interval
        return False

    def _engage_by_template(self, name_file: str) -> bool:
        """用名字模板找怪、走过去、交战"""
        tpl = _name_tpl(name_file)

        # 第一步：找到并走过去
        self.log(f"    寻找 {name_file} ...")
        pos = exists(tpl)
        if not pos:
            self.log(f"    屏幕内未找到 {name_file}")
            return False

        self.log(f"    找到位置={pos}，走过去...")
        touch(pos)
        time.sleep(self.WALK_WAIT)

        # 第二步：再次点击触发对话
        pos2 = exists(tpl)
        if pos2:
            touch(pos2)
        else:
            # 可能已经走到附近，直接点原位置
            touch(pos)
        time.sleep(0.8)

        # 第三步：检查"进入战斗"
        enter = exists(_ui_tpl("enter_battle.png"))
        if not enter:
            self.log(f"    未弹出'进入战斗'，可能不是怪物")
            return False

        touch(enter)
        time.sleep(0.5)

        # 第四步：确认对话
        dialog = exists(_ui_tpl("battle_dialog.png"))
        if dialog:
            touch(dialog)
            time.sleep(0.3)

        # 第五步：等战斗界面 + 点"自动"
        self.log("    战斗中...")
        for _ in range(10):
            if not self._running:
                return True
            auto = exists(_ui_tpl("auto_btn.png"))
            if auto:
                touch(auto)
                break
            time.sleep(0.5)

        # 第六步：等待战斗结束
        self._wait_battle_end()
        return True

    def _wait_battle_end(self):
        """轮询等待战斗结束"""
        waited = 0
        while waited < self.BATTLE_TIMEOUT and self._running:
            end = exists(_ui_tpl("battle_end.png"))
            if end:
                touch(end)
                time.sleep(0.3)
                return
            time.sleep(1.0)
            waited += 1
        # 超时兜底
        end = exists(_ui_tpl("battle_end.png"))
        if end:
            touch(end)

    # ── 去下一层 ───────────────────────────────

    def _go_next_floor(self):
        """打完之后，找传送NPC去下一层"""
        tpl_path = os.path.join(TPL_DIR, "next_floor.png")
        if not os.path.exists(tpl_path):
            self.log("  (缺少 next_floor.png 模板，请手动去下一层)")
            return

        self.log("  寻找传送NPC...")
        tpl = _ui_tpl("next_floor.png")
        for _ in range(8):
            if not self._running:
                return
            pos = exists(tpl)
            if pos:
                touch(pos)
                self.log("  已进入下一层")
                time.sleep(3)
                return
            time.sleep(0.8)
        self.log("  未找到传送NPC")
