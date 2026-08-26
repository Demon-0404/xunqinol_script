"""天渊40任务 —— 40层爬塔，流程待补充"""
import time
import os
import json
import numpy as np
from PIL import Image
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 坐标配置 (1080x1920) ──────────────────────
NEARBY_BTN = (350, 1780)         # 数字键7 → 周围列表
NPC_TAB = (750, 250)             # NPC标签
ROW_X = 180                      # 点击行内X位置
ROW_Y_START = 450                # 第一行Y
ROW_SPACING = 120                # 行间距
ROW_COUNT = 7                    # 一页最多行数
NEXT_PAGE = (520, 1330)          # 翻页按钮
AUTO_PATHFIND = (500, 660)       # 自动寻路按钮
KEY5 = (150, 1590)               # 数字键5确认
KEY0 = (950, 1590)               # 数字键0 → 自动遇怪
TARGET_NPC = "天渊使者"           # 目标NPC

# 面板检测
PANEL_TITLE_CHECK = (500, 100)
PANEL_TITLE_SPREAD = 200
CANCEL_PANELS = [
    (950, 1200),                 # 进入战斗面板
    (950, 1450),                 # 聊天记录面板
]

# 战斗检测 (右下角战斗模式按钮: 手动遇怪显'自动', 自动遇怪显'手动')
BATTLE_BTN = (976, 1450)
BATTLE_BTN_RANGE = 80
BATTLE_BTN_THRESHOLD = 0.7

# 地图名检测
MAP_NAME_POS = (950, 110)
MAP_NAME_RANGE = 80

# 楼层导航
MOVE_LEFT = (100, 1100)
MOVE_RIGHT = (1000, 1100)
MOVE_WAIT = 2.0

# ── 等待时间 ──────────────────────────────────
BATTLE_CHECK_INTERVAL = 0.2

# 每层阶段数
TOTAL_PHASES = 6


class TianyuanTask(BaseTask):
    """天渊40层自动任务"""

    def __init__(self, serial: str = "", start_phase: int = None, loop: int = 40):
        super().__init__("天渊40")
        self._serial = serial
        self._reader = None
        self._start_phase = start_phase
        self._loop = max(1, int(loop or 40))

    # ── OCR ────────────────────────────────────

    def _get_reader(self):
        if self._reader is None:
            self.log_key("连接OCR共享服务...")
            from core.ocr_client import get_ocr_client
            self._reader = get_ocr_client()
            self.log_key("OCR服务就绪")
        return self._reader

    def _screenshot_arr(self) -> np.ndarray:
        import subprocess
        adb = os.environ.get("ANDROID_ADB", "adb")
        tmp = os.path.join(LOG_DIR, f"_tianyuan_tmp_{os.getpid()}.png")
        adb_args = [adb]
        if self._serial:
            adb_args += ["-s", self._serial]
        try:
            with open(tmp, "wb") as f:
                subprocess.run(
                    adb_args + ["exec-out", "screencap", "-p"],
                    stdout=f, stderr=subprocess.DEVNULL, timeout=5)
            return np.array(Image.open(tmp))[:, :, :3]
        except Exception:
            return None

    # ── 战斗检测 (模板匹配) ────────────────────

    _tpl_auto = None
    _tpl_manual = None

    def _load_templates(self):
        if self._tpl_auto is None:
            import cv2
            tpl_dir = os.path.join(BASE_DIR, "templates", "tianyuan")
            self._tpl_auto = cv2.imread(os.path.join(tpl_dir, "auto.png"))
            self._tpl_manual = cv2.imread(os.path.join(tpl_dir, "manual.png"))

    def _match_template(self, arr, tpl, cx, cy, spread, threshold=0.7) -> bool:
        import cv2
        h, w = arr.shape[:2]
        y1, y2 = max(0, cy - spread), min(h, cy + spread)
        x1, x2 = max(0, cx - spread), min(w, cx + spread)
        if y2 - y1 < tpl.shape[0] or x2 - x1 < tpl.shape[1]:
            return False
        roi = arr[y1:y2, x1:x2, :]
        result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return max_val > threshold

    def _is_in_battle(self) -> bool:
        arr = self._stream_frame()
        if arr is None:
            arr = self._screenshot_arr()
        if arr is None:
            return False
        import cv2
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        self._load_templates()
        if self._match_template(arr, self._tpl_auto, BATTLE_BTN[0], BATTLE_BTN[1], BATTLE_BTN_RANGE, BATTLE_BTN_THRESHOLD):
            return True
        if self._match_template(arr, self._tpl_manual, BATTLE_BTN[0], BATTLE_BTN[1], BATTLE_BTN_RANGE, BATTLE_BTN_THRESHOLD):
            return True
        return False

    def _wait_battle_end(self):
        miss = 0
        t0 = time.time()
        miss_need = 2
        min_battle = 3.0
        while self._running and time.time() - t0 < 60:
            time.sleep(0.3)
            if self._is_in_battle():
                miss = 0
            else:
                miss += 1
                if miss >= miss_need and time.time() - t0 >= min_battle:
                    break
        self.log_key("  战斗结束!")

    # ── NPC列表 ────────────────────────────────

    def _check_text_at(self, keyword: str, center: tuple, spread: int) -> bool:
        arr = self._screenshot_arr()
        if arr is None:
            return False
        h, w = arr.shape[:2]
        x, y = center
        y1, y2 = max(0, y - spread), min(h, y + spread)
        x1, x2 = max(0, x - spread), min(w, x + spread)
        crop = arr[y1:y2, x1:x2, :]
        reader = self._get_reader()
        try:
            results = reader.readtext(crop)
        except Exception:
            return False
        for r in results:
            if r[2] >= 0.1 and keyword in r[1]:
                return True
        return False

    def _dismiss_panels(self) -> bool:
        for cx, cy in CANCEL_PANELS:
            if self._check_text_at("取消", (cx, cy), 100):
                self.log(f"  误开面板，点取消关闭 @({cx},{cy})")
                self._safe_touch((cx, cy))
                time.sleep(0.5)
                return True
        return False

    def _open_npc_list(self):
        for retry in range(3):
            self.log(f"  打开周围列表... ({retry + 1}/3)")
            self._safe_touch(NEARBY_BTN)
            time.sleep(1.5)
            if not self._check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
                self.log("  未检测到'周围列表'，尝试关闭误开面板...")
                self._dismiss_panels()
                time.sleep(0.5)
                continue
            self._safe_touch(NPC_TAB)
            time.sleep(1.2)
            if self._check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
                self.log("  NPC面板已打开")
                return
            self.log(f"  NPC面板未正确打开，重试...")
        self.log("  NPC面板多次重试失败")

    def _scan_npc_page(self) -> list:
        """扫描NPC列表，返回 [(name, y), ...]"""
        arr = self._screenshot_arr()
        if arr is None:
            return []
        h, w = arr.shape[:2]
        reader = self._get_reader()
        results_list = []
        for i in range(ROW_COUNT):
            yc = ROW_Y_START + i * ROW_SPACING
            y1, y2 = max(0, yc - 45), min(h, yc + 45)
            row = arr[y1:y2, 0:540, :]
            gray = np.mean(row, axis=2)
            if (gray < 80).mean() < 0.02:
                continue
            best_result = None
            best_conf = 0
            for mag in [1, 3]:
                try:
                    results = reader.readtext(row, mag_ratio=mag)
                except Exception:
                    continue
                if not results:
                    continue
                r = max(results, key=lambda r: r[2])
                if r[2] > best_conf:
                    best_result = r
                    best_conf = r[2]
            if best_result and best_conf >= 0.05:
                self.log(f"    Row{i} Y={yc}: '{best_result[1]}' ({best_conf:.2f})")
                results_list.append((best_result[1], yc))
        self.log(f"  扫描完成: {len(results_list)} 条")
        return results_list

    def _find_npc(self, target: str) -> tuple | None:
        """在NPC列表中查找目标，支持翻页，返回 (name, y) 或 None"""
        for page in range(1, 5):
            self.log(f"  查找'{target}' — 第{page}页...")
            self._open_npc_list()
            npcs = self._scan_npc_page()

            # 1. 优先精确匹配
            for name, y in npcs:
                if target in name or name in target:
                    self.log(f"  精确匹配: '{name}' @ Y={y}")
                    return (name, y)

            # 2. 模糊匹配：选共同字最多的
            best = None
            best_common = 0
            for name, y in npcs:
                common = sum(1 for ch in name if ch in target)
                if common > best_common:
                    best_common = common
                    best = (name, y)
            if best and best_common >= 2:
                self.log(f"  模糊匹配: '{best[0]}' @ Y={best[1]} (共同{best_common}字)")
                return best

            if page < 4:
                self.log(f"  第{page}页未找到，翻页...")
                self._safe_touch(NEXT_PAGE)
                time.sleep(0.8)
        return None

    def _find_and_pathfind(self, target_npc: str = None):
        """找到NPC并自动寻路，带战斗监测"""
        if target_npc is None:
            target_npc = TARGET_NPC
        result = self._find_npc(target_npc)
        if result is None:
            self.log(f"  未找到{target_npc}")
            return False
        name, y = result
        self.log(f"  点击NPC: '{name}' @ Y={y}")
        self._safe_touch((ROW_X, y))
        time.sleep(0.5)
        if y == ROW_Y_START:
            self._safe_touch(KEY5)
        else:
            self._safe_touch(AUTO_PATHFIND)
            time.sleep(0.3)
            self._safe_touch(KEY5)
        self.log("  自动寻路中(监测战斗)...")
        PATHFIND_WAIT = 3.0
        MAX_PATHFIND_ROUNDS = 4
        for attempt in range(MAX_PATHFIND_ROUNDS):
            elapsed = 0.0
            while elapsed < PATHFIND_WAIT and self._running:
                if self._is_in_battle():
                    self.log(f"  寻路中遇怪! (第{attempt + 1}次)")
                    self._wait_battle_end()
                    self.log("  继续寻路...")
                    break
                time.sleep(BATTLE_CHECK_INTERVAL)
                elapsed += BATTLE_CHECK_INTERVAL
            else:
                self.log("  寻路完成")
                break
        else:
            self.log(f"  寻路等待达上限")
        if self._is_in_battle():
            self._wait_battle_end()
        self.log(f"  到达{target_npc}")
        return True

    # ── 楼层导航 ─────────────────────────────

    def _battle_aware_click(self, pos: tuple, wait: float):
        """点击并等待，期间监测战斗（战斗时暂停计时）"""
        if self._is_in_battle():
            self.log("  点击前检测到战斗，等待结束...")
            self._wait_battle_end()
        self._safe_touch(pos)
        elapsed = 0.0
        while elapsed < wait and self._running:
            if self._is_in_battle():
                self.log("  移动中遇怪，等待战斗结束...")
                self._wait_battle_end()
                self.log("  继续移动...")
            time.sleep(BATTLE_CHECK_INTERVAL)
            elapsed += BATTLE_CHECK_INTERVAL

    # 中文数字字符集
    CN_NUMS = set("一二三四五六七八九十")

    def _extract_floor_num(self, text: str) -> str:
        """从地图名中提取楼层数字，如 '天渊一层' → '一'"""
        nums = [ch for ch in text if ch in self.CN_NUMS]
        return nums[-1] if nums else ""

    def _check_floor_num(self) -> str:
        """读取当前地图楼层数字，返回如 '一'、'二'，失败返回空"""
        arr = self._screenshot_arr()
        if arr is None:
            return ""
        h, w = arr.shape[:2]
        y1, y2 = max(0, MAP_NAME_POS[1] - MAP_NAME_RANGE), min(h, MAP_NAME_POS[1] + MAP_NAME_RANGE)
        x1, x2 = max(0, MAP_NAME_POS[0] - MAP_NAME_RANGE), min(w, MAP_NAME_POS[0] + MAP_NAME_RANGE)
        crop = arr[y1:y2, x1:x2, :]
        reader = self._get_reader()
        try:
            results = reader.readtext(crop)
        except Exception:
            return ""
        if results:
            text = max(results, key=lambda r: r[2])[1]
            return self._extract_floor_num(text)
        return ""

    def _navigate_next_floor(self):
        """左右移动进入下一层，通过楼层数字变化判断是否进入"""
        before = self._check_floor_num()
        self.log(f"  当前楼层: {before}")

        moves = [
            ("左1", MOVE_LEFT),
            ("左2", MOVE_LEFT),
            ("右1", MOVE_RIGHT),
            ("右2", MOVE_RIGHT),
        ]
        for name, pos in moves:
            self.log(f"  向{name}移动 ({pos[0]},{pos[1]})...")
            self._battle_aware_click(pos, MOVE_WAIT)
            time.sleep(0.5)
            after = self._check_floor_num()
            self.log(f"  {name}后: {after}")
            if after and before and after != before:
                self.log_key(f"  楼层变化: {before} → {after}!")
                return

        self.log("  楼层未变化")

    # ── 自动战斗 ─────────────────────────────

    def _auto_battle(self):
        """按0开启自动遇怪，等战斗开始→结束→再按0关闭，只打1场"""
        self.log("  开启自动遇怪(键0)...")
        self._safe_touch(KEY0)
        time.sleep(0.5)

        # 等待战斗开始
        self.log("  等待遇怪...")
        while self._running:
            if self._is_in_battle():
                self.log_key("  进入战斗!")
                break
            time.sleep(BATTLE_CHECK_INTERVAL)

        # 等待战斗结束
        self._wait_battle_end()

        # 战斗结束后关闭自动遇怪
        self.log("  关闭自动遇怪(键0)...")
        self._safe_touch(KEY0)
        time.sleep(0.5)

        # 检查是否有残留战斗
        if self._is_in_battle():
            self.log("  检测到残留战斗，等待结束...")
            self._wait_battle_end()

    # ── 断点续跑 (状态文件) ──────────────────────

    @property
    def _state_file(self) -> str:
        safe = self._serial.replace(":", "_").replace("/", "_") if self._serial else "default"
        return os.path.join(LOG_DIR, f"tianyuan_state_{safe}.json")

    def _load_progress(self) -> int:
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                return int(json.load(f).get("last_done_phase", -1))
        except Exception:
            return -1

    def _save_progress(self, phase: int):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump({"last_done_phase": phase}, f)
            self.log_key(f"[进度] Phase {phase}/{TOTAL_PHASES} 完成")
        except Exception as e:
            self.log(f"  [进度] 保存失败: {e}")

    def _clear_progress(self):
        try:
            if os.path.exists(self._state_file):
                os.remove(self._state_file)
                self.log_key("[进度] 已重置进度记录")
        except Exception:
            pass

    def _log_phase(self, n: int, desc: str):
        self.log_key(f"══ Phase {n}/{TOTAL_PHASES}: {desc} ══")

    # ── 主流程 ─────────────────────────────────

    def run(self):
        self.log_key("天渊40启动")

        if self._start_phase is None:
            done = self._load_progress()
            if done >= 0:
                start_phase = done + 1
                if start_phase >= TOTAL_PHASES:
                    start_phase = 0
                self.log_key(f"[进度] 上次完成 Phase {done}，自动续跑 Phase {start_phase}")
            else:
                start_phase = 0
        elif self._start_phase == 0:
            self._clear_progress()
            start_phase = 0
            self.log_key("[进度] 已重置，从 Phase 0 开始")
        else:
            start_phase = self._start_phase
            self.log_key(f"[进度] 手动从 Phase {start_phase} 开始")

        for floor in range(1, self._loop + 1):
            if not self._running:
                break
            self.log_key(f"════ 第 {floor}/{self._loop} 层 ════")
            self._run_floor(start_phase, is_last=(floor == self._loop))
            start_phase = 0

        self._clear_progress()
        self.log_key("天渊40流程完成!")

    def _run_floor(self, start_phase: int, is_last: bool = False):
        """单层 6 个 phase；is_last=True(最后一层)时跳过'去下一层'"""
        if start_phase <= 0:
            self._log_phase(0, "找天渊使者→寻路")
            self._find_and_pathfind(TARGET_NPC)
            self._save_progress(0)

        if start_phase <= 1:
            self._log_phase(1, "接任务")
            self._quest_accept()
            self._save_progress(1)

        if start_phase <= 2:
            self._log_phase(2, "自动遇怪打1场")
            self._auto_battle()
            self._save_progress(2)

        if start_phase <= 3:
            self._log_phase(3, "找天渊使者→寻路")
            self._find_and_pathfind(TARGET_NPC)
            self._save_progress(3)

        if start_phase <= 4:
            self._log_phase(4, "交任务")
            self._quest_submit()
            self._save_progress(4)

        if start_phase <= 5 and not is_last:
            self._log_phase(5, "去下一层")
            self._navigate_next_floor()
            self._save_progress(5)
