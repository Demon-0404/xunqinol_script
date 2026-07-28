"""副本自动任务 —— 90/100副本 固定点击流程 + OCR战斗监控"""
import time
import os
import re
import numpy as np
from PIL import Image
from airtest.core.api import touch, snapshot, keyevent
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 坐标配置 (1080x1920) ──────────────────────
# 90副本和100副本共用入口流程，仅第4步选择不同

DUNGEON_CONFIG = {
    90: {
        "name": "90青丘境",
        "select_pos": (250, 550),       # 第4步: 选中 [90]青丘境
    },
    100: {
        "name": "100副本",
        "select_pos": (250, 700),       # 第4步: 选中 [100]副本（往下一点）
    },
}

# 通用流程坐标（90/100共用）
STEP_MEMO = (1000, 1200)       # 1. 备忘
STEP_DUNGEON_TAB = (750, 200)  # 2. 副本标签
STEP_NEXT_PAGE = (520, 1340)   # 3. 下一页
STEP_CONFIRM = (100, 1450)     # 5. 确认
STEP_TELEPORT = (500, 730)     # 6. 瞬间传送 → 到NPC
STEP_NPC_DIALOG = (500, 750)   # 7. NPC对话(数字键5)
STEP_AUTO_ACCEPT = (150, 1780) # 8. 一键领任务(*号)
STEP_CONFIRM2 = (100, 1590)    # 9. 确认(数字键5)
STEP_ENTER_CONFIRM = (100, 1200)  # 10/11. 确认进入/缴费进入
STEP_AUTO_COMBAT = (950, 1590) # 12. 自动遇怪(数字键0)

# 战斗监控
COMBAT_COUNTER = (500, 1250)   # "剩XX场" 文字区域
COUNTER_RANGE = 150            # 检测范围

# 战后流程
QUEST_BTN = (950, 200)         # 任务按钮
QUEST_TRACK = (500, 660)       # 追踪/寻路按钮
CONFIRM_KEY5 = (100, 1600)     # 确认键(数字5)
BOSS_ENTER = (500, 600)        # Boss进入战斗
DUNGEON_EXIT = (500, 800)      # 退出副本/结算

# 等待时间
WAIT_CLICK = 0.3               # 点击后等待
WAIT_PAGE = 0.8                # 页面切换等待
WAIT_TELEPORT = 3.0            # 传送等待
WAIT_DIALOG = 1.0              # 对话框等待
WAIT_COMBAT_CHECK = 0.5        # 战斗状态检测间隔
WAIT_POST_COMBAT = 2.0         # 战斗结束后等待
WAIT_QUEST = 1.5               # 任务追踪等待


class DungeonTask(BaseTask):
    """副本自动任务 —— 90或100副本"""

    def __init__(self, dungeon_id: int = 90, rounds: int = 3):
        """
        dungeon_id: 90 或 100
        rounds: 每个副本刷几次（默认3次）
        """
        cfg = DUNGEON_CONFIG.get(dungeon_id, DUNGEON_CONFIG[90])
        super().__init__(f"刷副本{dungeon_id}")
        self.dungeon_id = dungeon_id
        self.dungeon_name = cfg["name"]
        self.select_pos = cfg["select_pos"]
        self.total_rounds = rounds
        self._round = 0
        self._ocr = None

    # ── OCR ────────────────────────────────────

    def _get_ocr(self):
        if self._ocr is None:
            import easyocr
            self.log("加载OCR模型...")
            self._ocr = easyocr.Reader(['ch_sim'], gpu=False, verbose=False)
            self.log("OCR模型就绪")
        return self._ocr

    # ── 截图 ───────────────────────────────────

    def _screenshot_arr(self) -> np.ndarray:
        import subprocess
        adb = os.environ.get("ANDROID_ADB", "adb")
        tmp = os.path.join(LOG_DIR, "_dungeon_tmp.png")
        try:
            subprocess.run([adb, "shell", "screencap", "-p", "/sdcard/sc.png"],
                          capture_output=True, timeout=5)
            subprocess.run([adb, "pull", "/sdcard/sc.png", tmp],
                          capture_output=True, timeout=5)
            return np.array(Image.open(tmp))[:, :, :3]
        except Exception:
            try:
                filename = snapshot()
                if filename is None:
                    raise RuntimeError("snapshot returned None")
                return np.array(Image.open(filename))[:, :, :3]
            except Exception:
                return np.array(Image.open(tmp))[:, :, :3]

    def _ocr_region(self, center: tuple, spread: int) -> str:
        """OCR 指定区域，返回所有识别文字拼接"""
        try:
            arr = self._screenshot_arr()
        except Exception:
            return ""
        h, w = arr.shape[:2]
        cx, cy = center
        y1, y2 = max(0, cy - spread), min(h, cy + spread)
        x1, x2 = max(0, cx - spread), min(w, cx + spread)
        crop = arr[y1:y2, x1:x2, :]
        reader = self._get_ocr()
        try:
            results = reader.readtext(crop)
        except Exception:
            return ""
        return "".join(r[1] for r in results if r[2] >= 0.05)

    def _check_text_at(self, keyword: str, center: tuple, spread: int) -> bool:
        """检查指定区域是否包含关键词"""
        text = self._ocr_region(center, spread)
        return keyword in text

    # ── 点击辅助 ────────────────────────────────

    def _tap(self, pos: tuple, desc: str = "", wait: float = None):
        if wait is None:
            wait = WAIT_CLICK
        x, y = pos
        label = f"{desc}({x},{y})" if desc else f"({x},{y})"
        self.log(f"  点击 {label}")
        touch(pos)
        time.sleep(wait)

    def _tap_key5(self):
        """点击确认键(数字5位置)"""
        self._tap(CONFIRM_KEY5, "确认(5)", WAIT_DIALOG)

    # ── 主流程 ─────────────────────────────────

    def run(self):
        self.log(f"副本{dungeon_id} 自动任务启动，共 {self.total_rounds} 轮")

        for r in range(self.total_rounds):
            if not self._running:
                break
            self._round = r + 1
            self.log(f"══════ 第 {self._round}/{self.total_rounds} 轮 ══════")
            try:
                self._do_one_round()
            except Exception as e:
                self.log(f"第{self._round}轮异常: {e}")
                import traceback
                self.log(traceback.format_exc())

        if self._running:
            self.log(f"副本{dungeon_id} 全部完成! 共 {self.total_rounds} 轮")

    def _do_one_round(self):
        """执行一轮完整副本"""
        self._enter_dungeon()       # 步骤 1-11
        self._auto_combat_loop()    # 步骤 12-13
        self._kill_boss()           # 步骤 14a: Boss
        self._exit_dungeon()        # 步骤 14b: 退出结算

    # ── 步骤 1-11: 进入副本 ─────────────────────

    def _enter_dungeon(self):
        """固定坐标流程：备忘→副本列表→选副本→传送→领任务→进入"""
        self.log("── 进入副本 ──")

        # 1. 打开备忘
        self._tap(STEP_MEMO, "备忘", WAIT_PAGE)

        # 2. 点击副本标签
        self._tap(STEP_DUNGEON_TAB, "副本", WAIT_PAGE)

        # 3. 翻到下一页（90/100副本在第二页）
        self._tap(STEP_NEXT_PAGE, "下一页", WAIT_PAGE)

        # 4. 选中副本 [90]青丘境 或 [100]
        self._tap(self.select_pos, f"选中{self.dungeon_name}", WAIT_PAGE)

        # 5. 确认
        self._tap(STEP_CONFIRM, "确认", WAIT_PAGE)

        # 6. 瞬间传送
        self._tap(STEP_TELEPORT, "瞬间传送", WAIT_TELEPORT)

        # 7. NPC对话框，按数字键5
        self._tap(STEP_NPC_DIALOG, "NPC对话(5)", WAIT_DIALOG)

        # 8. 一键领任务(*号)
        self._tap(STEP_AUTO_ACCEPT, "一键领任务(*)", WAIT_DIALOG)

        # 9. 再按5确认
        self._tap(STEP_CONFIRM2, "确认(5)", WAIT_DIALOG)

        # 10. 确认进入
        self._tap(STEP_ENTER_CONFIRM, "确认进入", WAIT_PAGE)

        # 11. 缴费进入（通常同一位置再点一次）
        time.sleep(0.5)
        self._tap(STEP_ENTER_CONFIRM, "缴费进入", WAIT_TELEPORT)

        self.log("  已进入副本 ✓")

    # ── 步骤 12-13: 自动遇怪 + 监控 ─────────────

    def _auto_combat_loop(self):
        """按数字键0开启自动遇怪，OCR监控剩余场数，归零后继续"""
        self.log("── 自动遇怪 ──")

        # 12. 按数字键0 开启自动遇怪
        self._tap(STEP_AUTO_COMBAT, "自动遇怪(0)", WAIT_COMBAT_CHECK)

        # 13. OCR监控 "剩XX场"
        self._monitor_combat_counter()

    def _monitor_combat_counter(self, timeout: float = 600.0):
        """OCR监控战斗计数器，检测"剩"字存在→战斗进行中，消失→战斗结束"""
        self.log("  开始监控战斗计数器...")
        start = time.time()
        last_text = ""
        miss_count = 0

        while time.time() - start < timeout and self._running:
            text = self._ocr_region(COMBAT_COUNTER, COUNTER_RANGE)

            if text != last_text:
                self.log(f"  [OCR] 计数器: '{text}'")
                last_text = text

            # 检测"剩"字 —— 表示还在战斗中
            if "剩" in text:
                miss_count = 0
                # 尝试提取数字
                nums = re.findall(r'\d+', text)
                if nums:
                    remaining = int(nums[0])
                    if remaining <= 3:
                        self.log(f"  ⚠ 剩余 {remaining} 场，即将结束!")
            else:
                miss_count += 1
                if miss_count >= 6:  # 连续3秒没有"剩"字
                    self.log("  战斗计数消失，所有怪物已清除 ✓")
                    break

            time.sleep(WAIT_COMBAT_CHECK)

        # 等战斗完全结束
        time.sleep(WAIT_POST_COMBAT)

        # 如果有结算弹窗，按5确认
        for _ in range(3):
            if self._check_text_at("按5键继续", (500, 950), 200):
                self._tap_key5()
                time.sleep(0.5)
            else:
                break

        self.log("  自动遇怪阶段完成 ✓")

    # ── 步骤 14: Boss ──────────────────────────

    def _kill_boss(self):
        """任务列表→寻路Boss→击杀→结算"""
        self.log("── Boss战 ──")

        # 打开任务列表
        self._tap(QUEST_BTN, "任务", WAIT_PAGE)

        # 追踪副本任务 → 自动寻路到Boss
        self._tap(QUEST_TRACK, "追踪任务", WAIT_QUEST)
        time.sleep(WAIT_TELEPORT)  # 等寻路

        # 进入Boss战斗（可能需要多次确认弹窗）
        for _ in range(5):
            self._tap_key5()
            time.sleep(0.5)

        # 等待进入战斗
        self.log("  等待Boss战...")
        for _ in range(10):
            time.sleep(0.5)
            if self._check_text_at("回合", (500, 200), 200):
                self.log("  进入Boss战!")
                break

        # 战斗中自动打，等待结算弹窗
        for _ in range(120):  # 最多等60秒
            if not self._running:
                return
            if self._check_text_at("胜利", (500, 500), 200):
                self.log("  战斗胜利!")
                break
            time.sleep(0.5)

        # 结算弹窗循环确认
        for _ in range(8):
            self._tap_key5()
            time.sleep(0.8)
            if not self._check_text_at("按5键继续", (500, 950), 200):
                break

        self.log("  Boss战完成 ✓")

    def _exit_dungeon(self):
        """退出副本，结算"""
        self.log("── 退出副本 ──")

        # 可能有退出确认按钮
        for _ in range(5):
            self._tap_key5()
            time.sleep(0.8)
            # 检查是否还在副本里（有"退出"按钮）
            if self._check_text_at("退出", (500, 800), 200):
                self._tap(DUNGEON_EXIT, "退出副本", WAIT_PAGE)
                break

        # 最终结算弹窗
        for _ in range(5):
            self._tap_key5()
            time.sleep(0.5)

        self.log("  副本完成 ✓")
