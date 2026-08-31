"""水晶刷怪任务 —— 点击坐标触发遇怪 + 模板匹配检测战斗，无限循环"""
import time
import os
import subprocess
import numpy as np
from PIL import Image
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 点击坐标序列 (1080x1920) ─────────────────
CLICK_POSITIONS = [(100, 200), (1000, 200), (200, 450), (200, 450)]
DEFAULT_GAPS = [0.1, 0.1, 0.4]   # 3 个点击间隔（第 4 次点击后直接战斗检测）

# ── 战斗检测（模板匹配，复用天渊模板）──────────
TPL_DIR = os.path.join(BASE_DIR, "templates", "tianyuan")
ROUND_CHECK = (500, 200)
ROUND_SPREAD = 80
MANUAL_CHECK = (1000, 1450)
MANUAL_SPREAD = 80
MATCH_THRESHOLD = 0.78   # 0.7 时天音主界面误匹配 round 到 0.722 误判战斗，调高避开

BATTLE_CHECK_INTERVAL = 0.5   # 战斗轮询间隔
ENTER_BATTLE_TIMEOUT = 30.0   # 等待进入战斗超时（秒）

# ── 停止遇怪按钮检测（模板匹配）────────────
TPL_STOP = os.path.join(BASE_DIR, "templates", "crystal", "stop_encounter.png")
STOP_ENCOUNTER_CENTER = (550, 1250)
STOP_ENCOUNTER_SPREAD_X = 100
STOP_ENCOUNTER_SPREAD_Y = 100
STOP_ENCOUNTER_THRESHOLD = 0.7


class CrystalTask(BaseTask):
    """水晶刷怪 —— 点坐标触发战斗 → 模板匹配等结束 → 无限循环"""

    def __init__(self, serial: str = "", gaps=None):
        super().__init__("水晶刷怪")
        self._serial = serial
        self._tpl_round = None
        self._tpl_manual = None
        self._tpl_stop = None
        self._round_count = 0
        # 构造点击序列：坐标 + 每次点击后的间隔
        gaps = gaps or DEFAULT_GAPS
        self._click_seq = [
            (CLICK_POSITIONS[0], gaps[0]),
            (CLICK_POSITIONS[1], gaps[1]),
            (CLICK_POSITIONS[2], gaps[2]),
            (CLICK_POSITIONS[3], 0.0),
        ]

    # ── 可中断 sleep ───────────────────────────

    def _sleep(self, seconds: float):
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(0.05)
            elapsed += 0.05

    # ── 触摸 / 截图 ────────────────────────────

    def _adb(self) -> str:
        return os.environ.get("ANDROID_ADB", "adb")

    def _touch(self, pos: tuple):
        if not self._running:
            return
        x, y = int(pos[0]), int(pos[1])
        self.log(f"  点击 ({x},{y})")
        args = [self._adb()]
        if self._serial:
            args += ["-s", self._serial]
        subprocess.run(args + ["shell", "input", "tap", str(x), str(y)],
                       capture_output=True, timeout=5)

    def _screenshot_arr(self):
        tmp = os.path.join(LOG_DIR, f"_crystal_tmp_{os.getpid()}.png")
        args = [self._adb()]
        if self._serial:
            args += ["-s", self._serial]
        try:
            with open(tmp, "wb") as f:
                subprocess.run(args + ["exec-out", "screencap", "-p"],
                               stdout=f, stderr=subprocess.DEVNULL, timeout=5)
            return np.array(Image.open(tmp))[:, :, :3]
        except Exception:
            try:
                subprocess.run(args + ["shell", "screencap", "-p", "/sdcard/sc.png"],
                               capture_output=True, timeout=5)
                subprocess.run(args + ["pull", "/sdcard/sc.png", tmp],
                               capture_output=True, timeout=5)
                return np.array(Image.open(tmp))[:, :, :3]
            except Exception:
                return None

    # ── 战斗检测（模板匹配，最快）──────────────

    def _load_templates(self):
        if self._tpl_round is None:
            import cv2
            self._tpl_round = cv2.imread(os.path.join(TPL_DIR, "round.png"))
            self._tpl_manual = cv2.imread(os.path.join(TPL_DIR, "manual.png"))
            self._tpl_stop = cv2.imread(TPL_STOP)

    def _match_template(self, arr, tpl, cx, cy, spread) -> bool:
        import cv2
        h, w = arr.shape[:2]
        y1, y2 = max(0, cy - spread), min(h, cy + spread)
        x1, x2 = max(0, cx - spread), min(w, cx + spread)
        if y2 - y1 < tpl.shape[0] or x2 - x1 < tpl.shape[1]:
            return False
        roi = arr[y1:y2, x1:x2, :]
        result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return max_val > MATCH_THRESHOLD

    def _is_in_battle(self, arr_bgr=None) -> bool:
        if arr_bgr is None:
            arr = self._screenshot_arr()
            if arr is None:
                return False
            import cv2
            arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        self._load_templates()
        if self._match_template(arr_bgr, self._tpl_round, ROUND_CHECK[0], ROUND_CHECK[1], ROUND_SPREAD):
            return True
        if self._match_template(arr_bgr, self._tpl_manual, MANUAL_CHECK[0], MANUAL_CHECK[1], MANUAL_SPREAD):
            return True
        return False

    def _match_stop_encounter(self, arr_bgr) -> bool:
        """检测 (550,1250) 处是否出现「停止遇怪」按钮（模板匹配，最快）"""
        import cv2
        tpl = self._tpl_stop
        if tpl is None:
            return False
        h, w = arr_bgr.shape[:2]
        cx, cy = STOP_ENCOUNTER_CENTER
        y1, y2 = max(0, cy - STOP_ENCOUNTER_SPREAD_Y), min(h, cy + STOP_ENCOUNTER_SPREAD_Y)
        x1, x2 = max(0, cx - STOP_ENCOUNTER_SPREAD_X), min(w, cx + STOP_ENCOUNTER_SPREAD_X)
        if y2 - y1 < tpl.shape[0] or x2 - x1 < tpl.shape[1]:
            return False
        roi = arr_bgr[y1:y2, x1:x2, :]
        result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return max_val > STOP_ENCOUNTER_THRESHOLD

    def _wait_battle_cycle(self):
        """等待进入战斗，然后等待战斗结束（期间检测并点击「停止遇怪」）"""
        # 等进入战斗
        start = time.time()
        while self._running and time.time() - start < ENTER_BATTLE_TIMEOUT:
            if self._is_in_battle():
                self.log_key("  进入战斗!")
                break
            self._sleep(BATTLE_CHECK_INTERVAL)

        # 等战斗结束（连续2次检测不到），战斗中持续检测「停止遇怪」按钮
        miss = 0
        while self._running:
            arr = self._screenshot_arr()
            if arr is None:
                import cv2
                arr_bgr = None
            else:
                import cv2
                arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                self._load_templates()

            in_battle = self._is_in_battle(arr_bgr) if arr_bgr is not None else False

            if in_battle:
                miss = 0
                # 检测到「停止遇怪」按钮 → 立即点击（不留延时）
                if self._match_stop_encounter(arr_bgr):
                    self.log_key("  检测到停止遇怪，立即点击!")
                    self._touch(STOP_ENCOUNTER_CENTER)
            else:
                miss += 1
                if miss >= 2:
                    self.log_key("  战斗结束!")
                    return
            self._sleep(BATTLE_CHECK_INTERVAL)

    # ── 主循环 ────────────────────────────────

    def run(self):
        self.log_key("水晶刷怪任务启动（点坐标方案）")
        self.log(f"  点击序列: {[p for p, _ in self._click_seq]}")
        self.log(f"  战斗检测: round@({ROUND_CHECK},±{ROUND_SPREAD}) + manual@({MANUAL_CHECK},±{MANUAL_SPREAD}) 阈值{MATCH_THRESHOLD}")

        while self._running:
            self._round_count += 1
            self.log_key(f"═══ 第 {self._round_count} 轮 ═══")

            for pos, interval in self._click_seq:
                if not self._running:
                    break
                self._touch(pos)
                self._sleep(interval)

            if not self._running:
                break

            self._wait_battle_cycle()

        self.log_key(f"水晶刷怪结束，共 {self._round_count} 轮")
