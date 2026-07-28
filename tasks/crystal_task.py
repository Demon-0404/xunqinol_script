"""水晶刷怪任务 —— 检测"备忘"文字判断自动遇怪状态，消失=战斗中，持续可见=已停止"""
import time
import os
import subprocess
import numpy as np
from PIL import Image
from airtest.core.api import touch, snapshot
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 坐标配置 (1080x1920) ──────────────────────
KEY0 = (950, 1590)              # 数字键0 —— 开启/关闭自动遇怪

# 战斗检测: (1000,1200) 左右1格 上下1格 → (900,1100)-(1100,1300)
#   "备忘"可见 → 非战斗 | 不可见 → 战斗中
MEMO_REGION = (900, 1100, 1100, 1300)
MEMO_KEYWORD = "备忘"

# ── 等待/间隔 ─────────────────────────────────
CHECK_INTERVAL = 2.0            # OCR检测间隔（2秒一次）
KEY0_COOLDOWN = 3.0             # KEY0按下后冷却期
CONSECUTIVE_LIMIT = 30          # 连续30次(=60s)检测到备忘 → 自动遇怪已停


class CrystalTask(BaseTask):
    """水晶刷怪 —— 备忘持续可见40s → 按KEY0重开"""

    def __init__(self, serial: str = ""):
        super().__init__("水晶刷怪")
        self._ocr = None
        self._serial = serial
        self._adb = os.environ.get("ANDROID_ADB", "adb")
        self._round_count = 0

    # ── OCR引擎 ────────────────────────────────

    def _get_ocr(self):
        if self._ocr is None:
            import easyocr
            self.log("[初始化] 加载OCR模型...")
            self._ocr = easyocr.Reader(['ch_sim'], gpu=False, verbose=False)
            self.log("[初始化] OCR模型就绪")
        return self._ocr

    # ── 截图 ───────────────────────────────────

    def _screenshot_arr(self) -> np.ndarray | None:
        tmp = os.path.join(LOG_DIR, "_crystal_tmp.png")
        adb_args = [self._adb]
        if self._serial:
            adb_args += ["-s", self._serial]
        try:
            subprocess.run(
                adb_args + ["shell", "screencap", "-p", "/sdcard/sc.png"],
                capture_output=True, timeout=5
            )
            subprocess.run(
                adb_args + ["pull", "/sdcard/sc.png", tmp],
                capture_output=True, timeout=5
            )
            return np.array(Image.open(tmp))[:, :, :3]
        except Exception:
            try:
                filename = snapshot()
                if filename:
                    return np.array(Image.open(filename))[:, :, :3]
            except Exception:
                pass
        return None

    # ── 检测备忘 ────────────────────────────────

    def _is_memo_visible(self) -> bool:
        """OCR检测"备忘"是否可见。True=可见(非战斗), False=不可见(战斗中)"""
        arr = self._screenshot_arr()
        if arr is None:
            return False

        h, w = arr.shape[:2]
        reader = self._get_ocr()

        dx1, dy1, dx2, dy2 = MEMO_REGION
        dy1c, dy2c = max(0, dy1), min(h, dy2)
        dx1c, dx2c = max(0, dx1), min(w, dx2)
        if dy2c <= dy1c or dx2c <= dx1c:
            return False

        d_crop = arr[dy1c:dy2c, dx1c:dx2c, :]
        try:
            for r in reader.readtext(d_crop, mag_ratio=2):
                if r[2] >= 0.1 and MEMO_KEYWORD in r[1]:
                    return True
        except Exception:
            pass
        return False

    # ── 主循环 ─────────────────────────────────

    def run(self):
        self.log("=" * 40)
        self.log("水晶刷怪任务启动")
        self.log(f"  检测区域: {MEMO_REGION}")
        self.log(f"  关键词: \"{MEMO_KEYWORD}\"")
        self.log(f"  逻辑: 连续{CONSECUTIVE_LIMIT}次({CONSECUTIVE_LIMIT * CHECK_INTERVAL:.0f}s)可见 → 按KEY0")
        self.log(f"  KEY0: {KEY0}")
        self.log("=" * 40)

        self.log("[初始化] 预热OCR模型...")
        self._get_ocr()
        self.log("[初始化] 开始监控")
        time.sleep(1.0)

        consecutive = 0

        while self._running:
            visible = self._is_memo_visible()

            if visible:
                consecutive += 1
                self.log(f"[#{consecutive}] 备忘可见 (非战斗) | 轮:{self._round_count}")

                if consecutive >= CONSECUTIVE_LIMIT:
                    self.log(f"  → 连续{CONSECUTIVE_LIMIT}次({CONSECUTIVE_LIMIT * CHECK_INTERVAL:.0f}s)可见，自动遇怪已停!")
                    self._round_count += 1
                    self.log(f"  → 按KEY0 开启第{self._round_count}轮自动遇怪")
                    touch(KEY0)
                    time.sleep(KEY0_COOLDOWN)
                    consecutive = 0
            else:
                if consecutive > 0:
                    self.log(f"  → 备忘消失，进入战斗! (之前连续{consecutive}次可见)")
                consecutive = 0

            time.sleep(CHECK_INTERVAL)

        self.log(f"水晶刷怪结束，共完成 {self._round_count} 轮")
