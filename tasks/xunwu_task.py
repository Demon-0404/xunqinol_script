"""帮派寻物任务 —— 20环跑环，红色字体识别帮贡物，仅目标(残魄石/精魄石/溟晶碎粒)才领取"""
import time
import os
import subprocess
import numpy as np
from PIL import Image
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 坐标配置 (1080x1920) ──────────────────────
KEY5 = (150, 1590)            # 数字键5 → 对话/领取/进入提交
KEY1 = (350, 1590)            # 数字键1 → 选中菜单第1项(帮派寻物/帮派悬赏)
KEY2 = (550, 1590)            # 数字键2 → 帮派菜单第一栏是"祈福"时选"帮派悬赏"
KEY_STAR = (150, 1790)        # *号键 → 提交任务
CANCEL_BTN = (974, 1215)      # 取消按钮(非目标帮贡物时)

# 菜单OCR区域(帮派悬赏菜单 / 帮派寻物菜单)
MENU_Y_START = 380
MENU_Y_END = 1100
MENU_X_START = 150
MENU_X_END = 700

# 帮贡物红色字体区域(对话"帮里需要的是 XX")
# 实测帮贡物名约在 x=450~604 y=1028~1079(3字)，4字"溟晶碎粒"更宽，故留余量
ITEM_Y1, ITEM_Y2 = 1000, 1110
ITEM_X1, ITEM_X2 = 400, 700

# 等待
WAIT_CLICK = 1.5             # 点击/菜单切换等待
WAIT_DIALOG = 1.5            # 对话加载等待

# 目标帮贡物（每个物品的匹配关键词）
ALL_ITEMS = ["残魄石", "精魄石", "溟晶碎粒"]
ITEM_KEYWORDS = {
    "残魄石": ["残魄石", "残魄"],
    "精魄石": ["精魄石", "精魄"],
    "溟晶碎粒": ["溟晶碎粒", "溟晶", "碎粒", "晶碎"],
}


class XunWuTask(BaseTask):
    """帮派寻物 20环"""

    TOTAL_ROUNDS = 20

    def __init__(self, serial: str = "", target_items=None):
        super().__init__("帮派寻物")
        self._serial = serial
        self._reader = None
        self._round = 0
        self._target_items = target_items or list(ALL_ITEMS)
        self._menu_is_qifu = None   # 缓存帮派菜单第一栏是否"祈福"(对同一号固定)

    # ── 基础工具 ────────────────────────────────

    def _sleep(self, seconds: float):
        """可中断的sleep，每0.1s检查一次_running"""
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(0.1)
            elapsed += 0.1

    def _adb(self) -> str:
        adb = os.environ.get("ANDROID_ADB", "adb")
        import shutil
        if not shutil.which(adb):
            adb = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
        return adb

    def _touch(self, pos: tuple, desc: str = "", wait: float = WAIT_CLICK):
        if not self._running:
            return
        x, y = int(pos[0]), int(pos[1])
        label = f"{desc}({x},{y})" if desc else f"({x},{y})"
        self.log(f"  点击 {label}")
        args = [self._adb()]
        if self._serial:
            args += ["-s", self._serial]
        subprocess.run(
            args + ["shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5)
        self._sleep(wait)

    def _screenshot_arr(self) -> np.ndarray:
        adb = self._adb()
        tmp = os.path.join(LOG_DIR, f"_xunwu_tmp_{os.getpid()}.png")
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

    # ── OCR 辅助 ────────────────────────────────

    def _find_menu_row(self, keywords: list, y_start=MENU_Y_START, y_end=MENU_Y_END):
        """在菜单区域OCR找含关键词的行，返回(cx,cy)或None。放大2倍提高识别率"""
        arr = self._screenshot_arr()
        if arr is None:
            return None
        h, w = arr.shape[:2]
        y_start = max(0, y_start)
        y_end = min(h, y_end)
        crop = arr[y_start:y_end, MENU_X_START:MENU_X_END, :]
        mag = 2
        big = np.array(Image.fromarray(crop).resize(
            (crop.shape[1] * mag, crop.shape[0] * mag), Image.LANCZOS))
        reader = self._get_reader()
        try:
            res = reader.readtext(big)
        except Exception:
            return None
        for bbox, text, conf in sorted(res, key=lambda r: r[0][0][1]):
            if conf < 0.3:
                continue
            if not any(kw in text for kw in keywords):
                continue
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            cx = MENU_X_START + int(sum(xs) / 4 / mag)
            cy = y_start + int(sum(ys) / 4 / mag)
            self.log(f"  找到 '{text}' (conf={conf:.2f}) @({cx},{cy})")
            return (cx, cy)
        return None

    def _menu_first_is_qifu(self) -> bool:
        """识别帮派菜单第一栏是否为'帮派祈福'（祈福档位需点键2选悬赏）。
        结果对同一号固定，首次成功检测后缓存，后续直接复用省去每次 OCR。"""
        if self._menu_is_qifu is not None:
            return self._menu_is_qifu
        arr = self._screenshot_arr()
        if arr is None:
            return False
        h, w = arr.shape[:2]
        y1, y2 = max(0, MENU_Y_START), min(h, MENU_Y_START + 120)
        x1, x2 = MENU_X_START, min(w, 800)
        crop = arr[y1:y2, x1:x2, :]
        mag = 2
        big = np.array(Image.fromarray(crop).resize(
            (crop.shape[1] * mag, crop.shape[0] * mag), Image.LANCZOS))
        reader = self._get_reader()
        try:
            res = reader.readtext(big)
        except Exception:
            return False
        text_all = "".join(t for _, t, c in res if c >= 0.3)
        self._menu_is_qifu = "祈福" in text_all
        self.log(f"  帮派菜单第一栏{'是' if self._menu_is_qifu else '否'}祈福(已缓存)")
        return self._menu_is_qifu

    def _recognize_item_once(self) -> str:
        """红色提取识别帮贡物名，返回文本；无红色字/识别失败返回空串"""
        arr = self._screenshot_arr()
        if arr is None:
            return ""
        h, w = arr.shape[:2]
        y1, y2 = max(0, ITEM_Y1), min(h, ITEM_Y2)
        x1, x2 = max(0, ITEM_X1), min(w, ITEM_X2)
        crop = arr[y1:y2, x1:x2, :]
        R = crop[:, :, 0].astype(int)
        G = crop[:, :, 1].astype(int)
        B = crop[:, :, 2].astype(int)
        mask = (R > 120) & ((R - G) > 50) & ((R - B) > 50)
        if not mask.any():
            return ""
        # 保留红色像素 R 通道亮度(而非纯白二值化)，避免"魄"等复杂字笔画细节丢失
        red = np.where(mask, R, 0).astype(np.uint8)
        big = np.array(Image.fromarray(red).resize(
            (red.shape[1] * 2, red.shape[0] * 2), Image.LANCZOS))
        big_rgb = np.stack([big] * 3, axis=-1)
        reader = self._get_reader()
        try:
            res = reader.readtext(big_rgb)
        except Exception:
            return ""
        parts = [r[1] for r in res if r[2] >= 0.05]
        return "".join(parts)

    def _recognize_item(self, max_retry: int = 3) -> str:
        for _ in range(max_retry):
            if not self._running:
                return ""
            text = self._recognize_item_once()
            if text:
                return text
            self._sleep(1.0)
        return ""

    def _match_target(self, text: str) -> bool:
        if not text:
            return False
        for item in self._target_items:
            for kw in ITEM_KEYWORDS.get(item, []):
                if kw in text:
                    return True
        return False

    # ── 单环流程 ────────────────────────────────

    def _do_one_round(self, r: int) -> bool:
        """返回 True=正常完成一环"""
        # 领取任务：非目标帮贡物则取消并刷新，直到刷出目标
        while self._running:
            # ① 数字键5 对话内务总管 → 帮派悬赏菜单
            self._touch(KEY5, "数字键5对话内务总管", WAIT_DIALOG)

            # ② 选中帮派悬赏：菜单第一栏是"帮派祈福"则点键2，否则点键1
            if self._menu_first_is_qifu():
                self._touch(KEY2, "数字键2选中帮派悬赏", WAIT_DIALOG)
            else:
                self._touch(KEY1, "数字键1选中帮派悬赏", WAIT_DIALOG)

            # ③ 数字键1 选中第1项(帮派寻物)
            self._touch(KEY1, "数字键1选中帮派寻物", WAIT_DIALOG)

            # ④ 红色提取识别帮贡物
            item = self._recognize_item()
            self.log(f"  识别帮贡物: '{item}'")
            if self._match_target(item):
                self.log_key(f"  是目标帮贡物，数字键5领取")
                self._touch(KEY5, "数字键5领取", WAIT_CLICK)
                break
            else:
                self.log_key(f"  非目标帮贡物，点取消刷新")
                self._touch(CANCEL_BTN, "取消", WAIT_CLICK)
                continue

        # ⑤ 数字键5 再对话 → "(帮)帮派寻物(已完成)"
        self._touch(KEY5, "数字键5再对话", WAIT_DIALOG)
        # ⑥ 数字键5 进入提交界面
        self._touch(KEY5, "数字键5进入提交", WAIT_DIALOG)
        # ⑦ *号键 提交 → 3秒内点数字键5跳过奖励结算
        self._touch(KEY_STAR, "*号键提交", 1.0)
        self._touch(KEY5, "数字键5跳过结算", WAIT_CLICK)
        return True

    # ── 主循环 ──────────────────────────────────

    def run(self):
        self.log_key(f"帮派寻物启动，共 {self.TOTAL_ROUNDS} 环")

        for r in range(1, self.TOTAL_ROUNDS + 1):
            if not self._running:
                break
            self._round = r
            self.log_key(f"══════ 第 {r}/{self.TOTAL_ROUNDS} 环 ══════")
            try:
                if not self._do_one_round(r):
                    self.log_key("今日帮派寻物已跑满，结束")
                    break
                self.log_key(f"第{r}环完成 ✓")
            except Exception as e:
                self.log(f"第{r}环异常: {e}")
                import traceback
                self.log(traceback.format_exc())

        if self._running:
            self.log_key(f"帮派寻物全部完成! 共 {self.TOTAL_ROUNDS} 环")
