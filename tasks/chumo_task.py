"""仗剑除魔任务 —— 20轮跑环，固定坐标 + OCR找大使 + 战斗检测"""
import time
import os
import subprocess
import numpy as np
from PIL import Image
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 坐标配置 (1080x1920) ──────────────────────
KEY7 = (350, 1780)            # 数字键7 → 打开周围列表
NPC_TAB = (750, 250)          # NPC标签
KEY3_FLIP = (730, 1590)       # 数字键3 → 翻下一页
CONFIRM = (100, 1450)         # 确认
CONFIRM_ACCEPT = (100, 1220)  # 确认接任务/提交任务
KEY5 = (150, 1590)            # 数字键5
KEY0_ENTER = (950, 1590)      # 数字键0 → 进入仗剑除魔
KEY1 = (350, 1590)            # 数字键1
KEY2 = (550, 1590)            # 数字键2 → 瞬间传送
KEY_STAR = (150, 1790)        # *号键 → 提交任务

# NPC列表OCR
ROW_X = 180
ROW_Y_START = 450
ROW_SPACING = 120
ROW_COUNT = 7
AMBASSADOR_KEYWORD = "日常活动大使"

# 战斗检测(复用玄兵塔方案)
ROUND_CHECK = (500, 200)
ROUND_RANGE = 200
BATTLE_MODE_CHECK = (1000, 1450)
BATTLE_MODE_RANGE = 100

# 等待时间
WAIT_CLICK = 1.0              # 点击间隔(用户要求1s)
WAIT_TELEPORT = 3.0           # 传送等待
BATTLE_CHECK_INTERVAL = 0.5
MOVE_AROUND_TIMEOUT = 5.0     # 5s没检测到战斗就按0键


class ChumoTask(BaseTask):
    """仗剑除魔 20轮跑环"""

    TOTAL_ROUNDS = 20

    def __init__(self, serial: str = ""):
        super().__init__("仗剑除魔")
        self._serial = serial
        self._reader = None
        self._round = 0

    # ── 可中断的 sleep ───────────────────────────

    def _sleep(self, seconds: float):
        """可中断的sleep，每0.1s检查一次_running"""
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(0.1)
            elapsed += 0.1

    # ── 工具方法 ────────────────────────────────

    def _adb(self) -> str:
        return os.environ.get("ANDROID_ADB", "adb")

    def _touch(self, pos: tuple, desc: str = ""):
        if not self._running:
            return
        x, y = pos
        label = f"{desc}({x},{y})" if desc else f"({x},{y})"
        self.log(f"  点击 {label}")
        args = [self._adb()]
        if self._serial:
            args += ["-s", self._serial]
        subprocess.run(
            args + ["shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5)
        self._sleep(WAIT_CLICK)

    def _screenshot_arr(self) -> np.ndarray:
        adb = self._adb()
        tmp = os.path.join(LOG_DIR, "_chumo_tmp.png")
        args = [adb]
        if self._serial:
            args += ["-s", self._serial]
        try:
            with open(tmp, "wb") as f:
                subprocess.run(
                    args + ["exec-out", "screencap", "-p"],
                    stdout=f, capture_output=True, timeout=5)
            return np.array(Image.open(tmp))[:, :, :3]
        except Exception:
            subprocess.run(
                args + ["shell", "screencap", "-p", "/sdcard/sc.png"],
                capture_output=True, timeout=5)
            subprocess.run(
                args + ["pull", "/sdcard/sc.png", tmp],
                capture_output=True, timeout=5)
            return np.array(Image.open(tmp))[:, :, :3]

    def _get_reader(self):
        if self._reader is None:
            import easyocr
            self.log("加载OCR模型...")
            self._reader = easyocr.Reader(['ch_sim'], gpu=False, verbose=False)
            self.log("OCR模型就绪")
        return self._reader

    # ── OCR 辅助 ────────────────────────────────

    def _check_text_at(self, keyword: str, center: tuple, spread: int) -> bool:
        try:
            arr = self._screenshot_arr()
        except Exception:
            return False
        h, w = arr.shape[:2]
        cx, cy = center
        y1, y2 = max(0, cy - spread), min(h, cy + spread)
        x1, x2 = max(0, cx - spread), min(w, cx + spread)
        try:
            for r in self._get_reader().readtext(arr[y1:y2, x1:x2, :]):
                if r[2] >= 0.1 and keyword in r[1]:
                    return True
        except Exception:
            pass
        return False

    def _check_panel_title(self, keyword: str) -> bool:
        return self._check_text_at(keyword, (500, 100), 200)

    def _fuzzy_match(self, ocr_text: str) -> bool:
        """模糊匹配：必须包含'日'或'常'（排除休闲活动大使），且与目标有足够重叠"""
        target = AMBASSADOR_KEYWORD
        # 精确/子串匹配
        if target in ocr_text or ocr_text in target:
            return True
        # 必须包含"日"或"常"（区分"休闲活动大使"）
        if "日" not in ocr_text and "常" not in ocr_text:
            return False
        # 字符重叠 >= 3 且包含"大使"
        common = sum(1 for ch in ocr_text if ch in target)
        if common >= 3 and "大使" in ocr_text:
            return True
        return False

    # ── 面板操作 ────────────────────────────────

    def _open_npc_list(self):
        """打开周围列表→NPC标签，验证面板正确打开，失败则重试"""
        for retry in range(3):
            if not self._running:
                return False
            self.log(f"  打开周围列表... (尝试{retry+1}/3)")
            self._touch(KEY7, "数字键7")
            self._sleep(1.0)

            if self._check_panel_title("周围列表"):
                self.log("  '周围列表'已打开 ✓")
            else:
                self.log("  未检测到'周围列表'，检查是否误开面板...")
                found_cancel = False
                for cx, cy in [(950, 1200), (950, 1450)]:
                    if self._check_text_at("取消", (cx, cy), 100):
                        self.log(f"  关闭误开面板 @({cx},{cy})")
                        self._touch((cx, cy), "取消")
                        self._sleep(0.5)
                        found_cancel = True
                        break
                if not found_cancel:
                    self._touch(KEY7, "数字键7重试")
                    self._sleep(0.5)
                continue

            # NPC标签
            self._touch(NPC_TAB, "NPC标签")
            self._sleep(1.0)

            if self._check_panel_title("周围列表"):
                self.log("  NPC列表已打开 ✓")
                return True
            self.log(f"  NPC标签点击后标题消失，重试...")

        self.log("  ⚠ NPC面板多次重试失败")
        return False

    # ── OCR 找大使 ──────────────────────────────

    def _scan_page_for_ambassador(self) -> int | None:
        """扫描当前NPC列表页，找到'日常活动大使'的行Y坐标，没找到返回None"""
        self.log("  OCR扫描当前页找大使...")
        try:
            arr = self._screenshot_arr()
        except Exception:
            return None
        h, w = arr.shape[:2]
        reader = self._get_reader()

        for i in range(ROW_COUNT):
            yc = ROW_Y_START + i * ROW_SPACING
            y1, y2 = max(0, yc - 45), min(h, yc + 45)
            row = arr[y1:y2, 0:540, :]
            gray = np.mean(row, axis=2)
            if (gray < 80).mean() < 0.02:
                continue

            for mag in [1, 3]:
                try:
                    results = reader.readtext(row, mag_ratio=mag)
                except Exception:
                    continue
                for r in results:
                    text, conf = r[1], r[2]
                    if conf >= 0.05 and self._fuzzy_match(text):
                        self.log(f"  找到: '{text}' conf={conf:.2f} Y={yc}")
                        return yc
        return None

    def _find_ambassador_y(self) -> int | None:
        """在当前页/翻页后找大使，返回行Y坐标，找不到返回None（不点击）"""
        y = self._scan_page_for_ambassador()
        if y is not None:
            return y

        self.log("  当前页没找到，点击数字键3翻页...")
        self._touch(KEY3_FLIP, "数字键3翻页")

        y = self._scan_page_for_ambassador()
        if y is not None:
            return y

        self.log("  ⚠ 两页都没找到大使")
        return None

    # ── 战斗检测(复用玄兵塔) ──────────────────────

    def _is_in_battle(self) -> bool:
        try:
            arr = self._screenshot_arr()
        except Exception:
            return False
        h, w = arr.shape[:2]
        reader = self._get_reader()

        checks = [
            ("回合", ROUND_CHECK, ROUND_RANGE),
            ("自动", BATTLE_MODE_CHECK, BATTLE_MODE_RANGE),
            ("手动", BATTLE_MODE_CHECK, BATTLE_MODE_RANGE),
        ]
        for keyword, (cx, cy), spread in checks:
            y1, y2 = max(0, cy - spread), min(h, cy + spread)
            x1, x2 = max(0, cx - spread), min(w, cx + spread)
            try:
                for r in reader.readtext(arr[y1:y2, x1:x2, :]):
                    if r[2] >= 0.1 and keyword in r[1]:
                        return True
            except Exception:
                continue
        return False

    def _wait_battle(self, timeout: float = 300.0):
        self.log("  等待进入战斗...")
        start = time.time()
        move_triggered = False
        while time.time() - start < 30 and self._running:
            if self._is_in_battle():
                self.log("  进入战斗!")
                break
            # 5s 没检测到战斗 → 点击数字键0
            if not move_triggered and time.time() - start >= MOVE_AROUND_TIMEOUT:
                self.log("  5s未遇怪，点击数字键0")
                self._touch(KEY0_ENTER, "数字键0")
                move_triggered = True
            self._sleep(BATTLE_CHECK_INTERVAL)

        self.log("  战斗中...")
        miss_count = 0
        while time.time() - start < timeout and self._running:
            if not self._is_in_battle():
                miss_count += 1
                if miss_count >= 2:
                    self.log("  战斗结束!")
                    return
            else:
                miss_count = 0
            self._sleep(BATTLE_CHECK_INTERVAL)
        self.log("  战斗超时或已停止")

    # ── 流程步骤 ────────────────────────────────

    def _accept_quest(self):
        """接取任务: 打开NPC列表 → 找大使 → 确认寻路 → 对话 → 进入"""
        self.log("── 接取任务 ──")

        # 打开NPC列表(带验证)
        if not self._open_npc_list():
            return False

        # OCR找大使(当前页→翻页)
        y = self._find_ambassador_y()
        if y is None:
            self.log("  ⚠ 未找到大使，尝试Y=904")
            y = 904

        is_first_row = (y == ROW_Y_START)
        if is_first_row:
            # 已在第一位，省略"选中大使"这一步
            self.log("  大实在第一位，跳过选中")
        else:
            self._touch((ROW_X, y), "日常活动大使")

        # 确认选择 → 确认寻路
        self._touch(CONFIRM, "确认选择")
        self._touch(CONFIRM, "确认寻路")
        self._sleep(2.0)

        # 键5 → 对话大使
        self._touch(KEY5, "数字键5对话")

        # 键0 → 进入仗剑除魔
        self._touch(KEY0_ENTER, "数字键0进入")

        # 键1 → 再次选中仗剑除魔
        self._touch(KEY1, "数字键1选中")

        # 确认接任务
        self._touch(CONFIRM_ACCEPT, "确认接任务")
        return True

    def _teleport_to_monster(self):
        """传送: 任务列表 → 确认 → 传送 → 确认"""
        self.log("── 传送 ──")
        self._touch(KEY1, "数字键1任务")
        self._touch(CONFIRM, "确认")
        self._touch(KEY2, "数字键2传送")
        self._touch(CONFIRM, "确认传送")
        self._sleep(WAIT_TELEPORT)

    def _submit_quest(self):
        """战后: 任务列表 → 传送回大使 → 交任务"""
        self.log("── 战后传送+交任务 ──")
        # 打开任务列表传送回大使身边
        self._touch(KEY1, "数字键1任务")
        self._touch(CONFIRM, "确认")
        self._touch(KEY2, "数字键2传送")
        self._touch(CONFIRM, "确认传送")
        self._sleep(WAIT_TELEPORT)

        # 键5对话 → 确认 → *号提交 → 等1s → 键5跳过结算
        self._touch(KEY5, "数字键5对话大使")
        self._touch(CONFIRM_ACCEPT, "确认提交")
        self._touch(KEY_STAR, "*号提交任务")
        self._sleep(1.0)
        self._touch(KEY5, "数字键5跳过结算")

    # ── 主循环 ──────────────────────────────────

    def run(self):
        self.log(f"仗剑除魔启动，共 {self.TOTAL_ROUNDS} 轮")

        for r in range(1, self.TOTAL_ROUNDS + 1):
            if not self._running:
                break
            self._round = r
            self.log(f"══════ 第 {r}/{self.TOTAL_ROUNDS} 轮 ══════")

            try:
                self._accept_quest()
                self._teleport_to_monster()
                self._wait_battle()
                self._submit_quest()

                self.log(f"第{r}轮完成 ✓")
            except Exception as e:
                self.log(f"第{r}轮异常: {e}")
                import traceback
                self.log(traceback.format_exc())

        if self._running:
            self.log(f"仗剑除魔全部完成! 共 {self.TOTAL_ROUNDS} 轮")
