"""战魔神任务 —— 日常任务合集之一，汉中行政区找日常活动大使

寻路优化：OCR 只扫列表区(缩小区域) + 翻页等待缩短到0.4s + 识别即点(零间隔)，
规避「周围列表超时自动回第一页」导致点击落空的问题。
"""
import time
import os
import subprocess
import numpy as np
from PIL import Image
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 坐标配置 (1080x1920) ──────────────────────
# 传送
MENU = (100, 1200)               # 菜单
KEY9_MAP = (733, 1773)           # 数字键9 打开地图
MAP_HANZHONG = (100, 800)        # 地图"汉中郡"
MAP_DISTRICT = (620, 620)        # 地图"汉中行政区"
MAP_NAME_CHECK = (500, 100)      # 顶部地图名检测(判断当前地图)
MAP_NAME_SPREAD = 200

# 寻路
NEARBY_BTN = (350, 1780)         # 数字键7 打开周围列表
NPC_TAB = (750, 250)             # NPC标签
KEY3_FLIP = (730, 1590)          # 数字键3 翻页
ROW_X = 180                      # 点击行内X
AMBASSADOR_KEYWORD = "日常活动大使"

# 寻路优化参数
FLIP_WAIT = 0.4                  # 翻页后等待(原1.0s，缩短防列表超时回第一页)
OCR_LIST_CROP = (400, 1350, 0, 560)  # OCR只扫列表区 (y1,y2,x1,x2)


class ZhanMoTask(BaseTask):
    """战魔神 日常任务"""

    def __init__(self, serial: str = ""):
        super().__init__("战魔神")
        self._serial = serial
        self._reader = None

    # ── 基础设施 ────────────────────────────────

    def _adb(self) -> str:
        adb = os.environ.get("ANDROID_ADB", "adb")
        import shutil
        if not shutil.which(adb):
            adb = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
        return adb

    def _sleep(self, seconds: float):
        """可中断sleep"""
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(0.1)
            elapsed += 0.1

    def _tap(self, pos, desc: str = "", wait: float = 0.0):
        """点击，wait>0 时才等待"""
        if not self._running:
            return
        x, y = pos
        label = f"{desc}({x},{y})" if desc else f"({x},{y})"
        self.log(f"  点击 {label}")
        args = [self._adb()]
        if self._serial:
            args += ["-s", self._serial]
        subprocess.run(
            args + ["shell", "input", "tap", str(int(x)), str(int(y))],
            capture_output=True, timeout=5)
        if wait > 0:
            self._sleep(wait)

    def _screenshot_arr(self):
        adb = self._adb()
        tmp = os.path.join(LOG_DIR, f"_zhanmo_tmp_{os.getpid()}.png")
        args = [adb]
        if self._serial:
            args += ["-s", self._serial]
        try:
            with open(tmp, "wb") as f:
                subprocess.run(
                    args + ["exec-out", "screencap", "-p"],
                    stdout=f, stderr=subprocess.DEVNULL, timeout=5)
            return np.array(Image.open(tmp))[:, :, :3]
        except Exception:
            return None

    def _get_reader(self):
        if self._reader is None:
            self.log_key("连接OCR共享服务...")
            from core.ocr_client import get_ocr_client
            self._reader = get_ocr_client()
            self.log_key("OCR服务就绪")
        return self._reader

    def _check_text_at(self, keyword: str, center, spread: int) -> bool:
        arr = self._screenshot_arr()
        if arr is None:
            return False
        h, w = arr.shape[:2]
        cx, cy = center
        y1, y2 = max(0, cy - spread), min(h, cy + spread)
        x1, x2 = max(0, cx - spread), min(w, cx + spread)
        crop = arr[y1:y2, x1:x2, :]
        reader = self._get_reader()
        try:
            for r in reader.readtext(crop):
                if r[2] >= 0.1 and keyword in r[1]:
                    return True
        except Exception:
            pass
        return False

    # ── 模糊匹配 ────────────────────────────────

    def _fuzzy_match(self, ocr_text: str) -> bool:
        """匹配'日常活动大使'，排除'休闲活动大使'"""
        target = AMBASSADOR_KEYWORD
        if target in ocr_text or ocr_text in target:
            return True
        if "日" not in ocr_text and "常" not in ocr_text:
            return False
        common = sum(1 for ch in ocr_text if ch in target)
        if common >= 3 and "大使" in ocr_text:
            return True
        return False

    # ── 传送 ────────────────────────────────────

    def _teleport_to_district(self) -> bool:
        self.log_key("── 传送: 菜单→地图→汉中郡→汉中行政区 ──")
        self._tap(MENU, "菜单", 1.0)
        self._tap(KEY9_MAP, "数字键9打开地图", 1.0)
        self._tap(MAP_HANZHONG, "地图汉中郡", 1.0)
        # 顶部(500,100)显示当前地图名：已在汉中行政区则点1次，否则点2次(选中+传送)
        if self._check_text_at("汉中行政区", MAP_NAME_CHECK, MAP_NAME_SPREAD):
            self.log_key("  已在汉中行政区，点1次传送")
            self._tap(MAP_DISTRICT, "汉中行政区", 1.0)
        else:
            self.log_key("  不在汉中行政区，点2次(选中+传送)")
            self._tap(MAP_DISTRICT, "汉中行政区选中", 1.0)
            self._tap(MAP_DISTRICT, "汉中行政区传送", 1.0)
        return True

    # ── 寻路(优化) ──────────────────────────────

    def _scan_page_for_ambassador(self):
        """OCR只扫列表区，找到'日常活动大使'返回行Y坐标，否则None"""
        arr = self._screenshot_arr()
        if arr is None:
            return None
        y1, y2, x1, x2 = OCR_LIST_CROP
        crop = arr[y1:y2, x1:x2, :]
        reader = self._get_reader()
        try:
            results = reader.readtext(crop, mag_ratio=1)
        except Exception:
            return None
        for r in results:
            bbox, text, conf = r
            if conf < 0.3:
                continue
            if self._fuzzy_match(text):
                cy = int((bbox[0][1] + bbox[2][1]) / 2) + y1
                self.log(f"  找到: '{text}' conf={conf:.2f} Y={cy}")
                return cy
        return None

    def _find_and_click_ambassador(self) -> bool:
        """打开周围列表→NPC标签→OCR找大使→识别即点(零间隔，规避列表超时)"""
        self.log_key("── 寻路: 找日常活动大使 ──")
        self._tap(NEARBY_BTN, "数字键7", 0.5)
        self._tap(NPC_TAB, "NPC标签", 0.5)
        for page in range(2):
            y = self._scan_page_for_ambassador()
            if y is not None:
                self._tap((ROW_X, y), "日常活动大使", 0.3)  # 识别即点，零间隔
                return True
            if page == 0:
                self.log("  当前页未找到，翻页...")
                self._tap(KEY3_FLIP, "数字键3翻页", FLIP_WAIT)
        self.log_key("  [失败] 两页都没找到日常活动大使")
        return False

    # ── 主流程 ──────────────────────────────────

    def run(self):
        self.log_key("战魔神任务启动（传送+寻路，后续流程待补）")
        self._teleport_to_district()
        if self._find_and_click_ambassador():
            self.log_key("  已找到并点击日常活动大使")
        else:
            self.log_key("  寻路失败")
        self.log_key("战魔神任务结束")
