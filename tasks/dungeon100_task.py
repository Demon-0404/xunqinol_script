"""100副本任务 —— 惊凡渊走路+传送门，OCR实时战斗检测 + 裂影渊NPC扫描"""
import time
import os
import json
import subprocess
import numpy as np
import cv2
from PIL import Image
from tasks.base_task import BaseTask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 坐标配置 (1080x1920) ──────────────────────
WALK_POS = (900, 1000)           # 走路点击(往右下)
PORTAL_POS = (350, 1100)         # 传送门(裂影渊)
MAP_NAME_POS = (950, 110)        # 地图名检测
MAP_NAME_RANGE = 80

# 战斗检测区域
ROUND_CHECK = (500, 200)         # "回合"文字
ROUND_RANGE = 200
BATTLE_MODE_CHECK = (1000, 1450) # "自动"/"手动"按钮
BATTLE_MODE_RANGE = 100

# 结算检测
SETTLE_CHECK = (800, 950)        # "按5键继续"
SETTLE_RANGE = 200

# 确认键
KEY5 = (150, 1590)

# NPC列表 (裂影渊阶段，复用玄兵塔坐标)
NEARBY_BTN = (350, 1780)         # 周围列表按钮
NPC_TAB = (750, 250)             # NPC标签
ROW_X = 180                      # 点击行内X位置
ROW_Y_START = 450                # 第一行Y
ROW_SPACING = 120                # 行间距
ROW_COUNT = 7                    # 一页最多行数
NEXT_PAGE = (520, 1330)          # 翻页按钮
AUTO_PATHFIND = (500, 660)       # 自动寻路按钮
CANCEL_BTN = (974, 1215)         # 取消按钮(弹窗关闭)
PANEL_TITLE_CHECK = (500, 100)   # "周围列表"检测
PANEL_TITLE_SPREAD = 200
CANCEL_PANELS = [
    (950, 1200),                 # 进入战斗面板
    (950, 1450),                 # 聊天记录面板
]
TARGET_NPC = "洞渊战魂"           # 目标NPC名(裂影渊)
TARGET_NPC2 = "百鬼之王"          # 目标NPC名(陨仙渊)

# 任务传送 (参考90副本dungeon_task.py)
KEY1 = (350, 1590)               # 数字键1 -&gt; 打开任务列表
QUEST_TRACK = (521, 671)         # 追踪任务/自动寻路
STEP_CONFIRM = (100, 1450)       # 确认按钮

# 入口流程坐标 (Phase 0: NPC-&gt;副本)
STEP_AUTO_ACCEPT = (150, 1780)   # 一键领任务(*号)
STEP_ENTER_CONFIRM = (100, 1200) # 确认进入/缴费进入

# 间隔
BATTLE_CHECK_INTERVAL = 0.3      # 战斗检测频率
WAIT_CLICK = 0.3                 # 点击后等待
WAIT_PAGE = 0.8                  # 页面切换等待
WAIT_TELEPORT = 3.0              # 传送等待
WAIT_DIALOG = 1.0                # 对话框等待
WAIT_STEP = 3.0                  # 走路/传送门每步间隔
MAX_STEPS_WALK = 5               # 走路点击次数
MAX_STEPS_PORTAL = 8             # 传送门点击次数
MAX_BATTLES = 2                  # 累计战斗次数


class Dungeon100Task(BaseTask):
    """100副本自动任务 — 惊凡渊 -&gt; 裂影渊"""

    def __init__(self, serial: str = "", start_phase: int = None):
        super().__init__("100副本")
        self._serial = serial
        self._reader = None
        self._battle_count = 0
        self._start_phase = start_phase

    # ── OCR ────────────────────────────────────

    def _get_reader(self):
        if self._reader is None:
            self.log_key("连接OCR共享服务...")
            from core.ocr_client import get_ocr_client
            self._reader = get_ocr_client()
            self.log_key("OCR服务就绪")
        return self._reader

    def _screenshot_arr(self) -> np.ndarray:
        adb = os.environ.get("ANDROID_ADB", "adb")
        # Fallback to MuMu adb if system adb not available
        import shutil
        if not shutil.which(adb):
            adb = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
        tmp = os.path.join(LOG_DIR, f"_dungeon100_tmp_{os.getpid()}.png")
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

    # ── 战斗检测 (模板匹配，复用天渊40) ──────────

    _tpl_round = None
    _tpl_manual = None

    def _load_templates(self):
        if self._tpl_round is None:
            tpl_dir = os.path.join(BASE_DIR, "templates", "tianyuan")
            self._tpl_round = cv2.imread(os.path.join(tpl_dir, "round.png"))
            self._tpl_manual = cv2.imread(os.path.join(tpl_dir, "manual.png"))

    def _match_template(self, arr, tpl, cx, cy, spread) -> bool:
        h, w = arr.shape[:2]
        y1, y2 = max(0, cy - spread), min(h, cy + spread)
        x1, x2 = max(0, cx - spread), min(w, cx + spread)
        if y2 <= y1 or x2 <= x1:
            return False
        roi = arr[y1:y2, x1:x2, :]
        result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return max_val > 0.7

    def _is_in_battle(self) -> bool:
        arr = self._screenshot_arr()
        if arr is None:
            return False
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        self._load_templates()
        if self._match_template(arr, self._tpl_round, 500, 200, 80):
            return True
        if self._match_template(arr, self._tpl_manual, 1000, 1450, 80):
            return True
        return False

    def _has_settlement(self) -> bool:
        arr = self._screenshot_arr()
        if arr is None:
            return False
        h, w = arr.shape[:2]
        cx, cy = SETTLE_CHECK
        s = SETTLE_RANGE
        y1, y2 = max(0, cy - s), min(h, cy + s)
        x1, x2 = max(0, cx - s), min(w, cx + s)
        crop = arr[y1:y2, x1:x2, :]
        reader = self._get_reader()
        try:
            results = reader.readtext(crop)
        except Exception:
            return False
        for r in results:
            if r[2] >= 0.1 and "按5键继续" in r[1]:
                return True
        return False

    # ── 点击辅助 ────────────────────────────────

    def _tap(self, pos: tuple, desc: str = "", wait: float = None):
        if wait is None:
            wait = WAIT_CLICK
        self.log(f"  点击 {desc}{pos}")
        self._safe_touch(pos)
        time.sleep(wait)

    def _tap_key5(self):
        self._safe_touch(KEY5)
        time.sleep(0.3)

    # ── 战斗循环 ────────────────────────────────

    def _wait_battle_end(self, is_boss: bool = False):
        self.log_key(f"  检测到战斗! 等待结束... (第{self._battle_count + 1}场)")
        miss = 0
        while self._running:
            if self._is_in_battle():
                miss = 0
            else:
                miss += 1
                if miss >= 2:
                    if is_boss:
                        self.log_key("  Boss战结束!")
                    else:
                        self._battle_count += 1
                        self.log_key(f"  战斗结束! 累计 {self._battle_count}/{MAX_BATTLES} 场")
                    break
            time.sleep(BATTLE_CHECK_INTERVAL)

        if is_boss:
            # Boss战结束不点结算弹窗，避免打乱后续流程，只延时
            time.sleep(12.0)
            return

        # 结算弹窗
        time.sleep(1.0)
        for _ in range(5):
            if self._has_settlement():
                self._tap_key5()
                time.sleep(0.5)
            else:
                break

    def _ensure_not_in_battle(self, tag=""):
        """关键点击前确保非战斗：先等战斗结束，再清残留结算弹窗"""
        if self._is_in_battle():
            self.log(f"  [{tag}] 检测到战斗，先等待结束...")
            self._wait_battle_end()
        # 兜底清理残留结算弹窗（战斗UI已消失但结算页还在）
        time.sleep(0.5)
        for _ in range(3):
            if self._has_settlement():
                self.log(f"  [{tag}] 残留结算弹窗，按5关闭...")
                self._tap_key5()
                time.sleep(0.5)
            else:
                break

    # ── Phase 0: 进入副本 (阳谷-&gt;惊凡渊) ──────────

    def _enter_dungeon(self):
        """NPC对话-&gt;领任务-&gt;进入副本（角色需已在NPC面前）"""
        self.log_key("── Phase 0: 进入副本 ──")

        self._tap(KEY5, "NPC对话(5)", WAIT_DIALOG)
        self._tap(KEY5, "进入领任务(5)", WAIT_DIALOG)
        self._tap(STEP_AUTO_ACCEPT, "一键领任务(*)", WAIT_DIALOG)
        self._tap(KEY5, "确认(5)", WAIT_DIALOG)
        self._tap(STEP_ENTER_CONFIRM, "确认进入", WAIT_PAGE)
        time.sleep(0.5)
        self._tap(STEP_ENTER_CONFIRM, "缴费进入", WAIT_TELEPORT)

        self.log_key("已进入100副本")

    # ── 走路阶段 ────────────────────────────────

    def _walk_phase(self):
        """走路到右下角"""
        self.log_key("── 走路阶段: 往右下角 ──")
        clicks = 0
        while clicks < MAX_STEPS_WALK and self._running:
            if self._is_in_battle():
                self._wait_battle_end()
                continue

            self._tap(WALK_POS, f"走路({clicks + 1}/{MAX_STEPS_WALK})")
            time.sleep(WAIT_STEP - WAIT_CLICK)
            clicks += 1

    # ── 传送门阶段 ──────────────────────────────

    def _get_map_name(self) -> str:
        arr = self._screenshot_arr()
        if arr is None:
            return ""
        h, w = arr.shape[:2]
        cx, cy = MAP_NAME_POS
        y1, y2 = max(0, cy - MAP_NAME_RANGE), min(h, cy + MAP_NAME_RANGE)
        x1, x2 = max(0, cx - MAP_NAME_RANGE), min(w, cx + MAP_NAME_RANGE)
        crop = arr[y1:y2, x1:x2, :]
        reader = self._get_reader()
        try:
            results = reader.readtext(crop)
        except Exception:
            return ""
        return "".join(r[1] for r in results if r[2] >= 0.05)

    def _portal_phase(self):
        """点击传送门进入裂影渊，检测地图名变化停止"""
        self.log_key("── 传送门阶段: 前往裂影渊 ──")
        clicks = 0
        original_map = self._get_map_name()
        self.log(f"  当前地图: '{original_map}'")
        while clicks < MAX_STEPS_PORTAL and self._running:

            if self._is_in_battle():
                self._wait_battle_end()
                continue

            self._tap(PORTAL_POS, f"传送门({clicks + 1}/{MAX_STEPS_PORTAL})")
            time.sleep(WAIT_STEP - WAIT_CLICK)
            clicks += 1

            if clicks >= 3:
                current_map = self._get_map_name()
                if current_map and current_map != original_map:
                    self.log(f"  地图已切换: '{original_map}' -> '{current_map}'")
                    return
                if current_map and not original_map:
                    self.log(f"  检测到地图: '{current_map}'")
                    return

    # ── NPC扫描阶段 (裂影渊) ─────────────────────

    def _check_text_at(self, keyword: str, center: tuple, spread: int) -> bool:
        """检查指定坐标周围是否存在指定文字"""
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
        """检测并关闭误打开的面板，返回是否关闭了面板"""
        for cx, cy in CANCEL_PANELS:
            if self._check_text_at("取消", (cx, cy), 100) or \
               self._check_text_at("关闭", (cx, cy), 100):
                self.log(f"  检测到误开面板 @({cx},{cy})，点击关闭")
                self._safe_touch((cx, cy))
                time.sleep(0.5)
                return True
        return False

    def _verify_npc_panel(self) -> bool:
        """检查NPC列表面板是否已正确打开"""
        if self._check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            self.log("  [面板] '周围列表'已打开")
            return True
        if self._check_text_at("聊天记录", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            self.log("  [面板] 误开'聊天记录'，尝试关闭...")
            if not self._dismiss_panels():
                # 兜底：直接点聊天记录面板关闭位置
                self.log("  [面板] 未识别到取消键，直接点关闭位置兜底")
                self._safe_touch((950, 1450))
                time.sleep(0.5)
            return False
        self.log("  [面板] 未检测到面板标题")
        return False

    def _open_npc_list(self):
        """打开周围列表-&gt;NPC标签（非战斗状态下才点击）"""
        for retry in range(3):
            self._ensure_not_in_battle("打开列表")
            self.log(f"  打开周围列表... (尝试{retry + 1}/3)")
            self._safe_touch(NEARBY_BTN)
            time.sleep(1.5)
            if self._check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
                self.log("  '周围列表'已打开")
            else:
                self.log("  未检测到'周围列表'，尝试关闭误开面板...")
                self._dismiss_panels()
                time.sleep(0.5)
                continue
            self._safe_touch(NPC_TAB)
            time.sleep(1.2)
            if self._verify_npc_panel():
                return
            self.log(f"  NPC面板未正确打开，重试...")
        self.log("  NPC面板多次重试失败")

    def _scan_npc_page(self) -> list:
        """OCR扫描NPC列表每一行，返回 [(name, y), ...]"""
        self.log("  [扫描NPC] 开始...")
        arr = self._screenshot_arr()
        if arr is None:
            return []
        h, w = arr.shape[:2]
        reader = self._get_reader()
        results_list = []

        # 保存调试截图
        ts = time.strftime("%H%M%S")
        debug_path = os.path.join(LOG_DIR, f"_dungeon_npc_{ts}.png")
        try:
            Image.fromarray(arr).save(debug_path)
            self.log(f"  [扫描NPC] 调试截图: {debug_path}")
        except Exception:
            pass

        for i in range(ROW_COUNT):
            yc = ROW_Y_START + i * ROW_SPACING
            y1, y2 = max(0, yc - 45), min(h, yc + 45)
            row = arr[y1:y2, 0:540, :]
            gray = np.mean(row, axis=2)
            dark_ratio = (gray < 80).mean()

            if dark_ratio < 0.02:
                continue

            for mag in [1, 3]:
                try:
                    results = reader.readtext(row, mag_ratio=mag)
                except Exception:
                    continue
                if not results:
                    continue
                for r in sorted(results, key=lambda r: r[2], reverse=True):
                    text = r[1]
                    conf = r[2]
                    if conf < 0.05:
                        continue
                    self.log(f"    Row{i} Y={yc}: OCR='{text}' conf={conf:.2f}")
                    results_list.append((text, yc))
                    break
                break  # mag=1 got results, skip mag=3

        self.log(f"  [扫描NPC] 完成: {len(results_list)} 条")
        return results_list

    def _find_npc(self, target: str) -> tuple | None:
        """在NPC列表中查找目标，返回 (name, y) 或 None，支持翻页"""
        for page in range(1, 5):
            self.log(f"  查找'{target}' — 第{page}页...")
            self._open_npc_list()
            npcs = self._scan_npc_page()

            for name, y in npcs:
                if target in name or name in target:
                    self.log(f"  找到: '{name}' @ Y={y}")
                    return (name, y)
                # 模糊匹配
                common = sum(1 for ch in name if ch in target)
                if common >= 2:
                    self.log(f"  模糊匹配: '{name}' ~ '{target}' @ Y={y}")
                    return (name, y)

            if page < 4:
                self.log(f"  第{page}页未找到，翻页...")
                self._safe_touch(NEXT_PAGE)
                time.sleep(0.8)
            else:
                self.log(f"  翻页{page}次仍未找到'{target}'")
        return None

    def _npc_phase(self, target_npc: str = None):
        """扫描NPC列表找目标NPC，自动寻路(带战斗监测)"""
        if target_npc is None:
            target_npc = TARGET_NPC
        result = self._find_npc(target_npc)
        if result is None:
            self.log(f"  未找到{target_npc}，跳过")
            return
        name, y = result
        self.log(f"  点击NPC: '{name}' @ Y={y}")
        self._ensure_not_in_battle("点击NPC")
        self._safe_touch((ROW_X, y))
        time.sleep(0.5)
        if y == ROW_Y_START:
            self._safe_touch(KEY5)
        else:
            self._safe_touch(AUTO_PATHFIND)
            time.sleep(0.3)
            self._safe_touch(KEY5)
        self.log("  自动寻路中(监测战斗)...")

        PATHFIND_WAIT = 8.0
        MAX_PATHFIND_ROUNDS = 4
        for attempt in range(MAX_PATHFIND_ROUNDS):
            elapsed = 0.0
            while elapsed < PATHFIND_WAIT and self._running:
                if self._is_in_battle():
                    self.log(f"  寻路中遇怪! (第{attempt + 1}次)")
                    self._wait_battle_end()
                    self.log(f"  继续寻路...")
                    break
                time.sleep(BATTLE_CHECK_INTERVAL)
                elapsed += BATTLE_CHECK_INTERVAL
            else:
                self.log(f"  寻路完成")
                break
        else:
            self.log(f"  寻路等待达上限({MAX_PATHFIND_ROUNDS}次)")

        if self._is_in_battle():
            self._wait_battle_end()
        self.log(f"  到达{target_npc}")

    def _submit_quest(self, check_battle: bool = True):
        """提交任务: 5-&gt;5-&gt;* -&gt; 等12s结算"""
        if check_battle:
            self._ensure_not_in_battle("提交任务")
        self.log("  提交任务: 5-&gt;5-&gt;*...")
        self._tap_key5()
        time.sleep(0.8)
        self._tap_key5()
        time.sleep(0.8)
        self._safe_touch((150, 1790))  # *号键
        self.log("  *号提交，等待12s结算...")
        time.sleep(12.0)

    def _accept_quest(self):
        """接取新任务: 5-&gt;5-&gt;*"""
        self._ensure_not_in_battle("接取任务")
        self.log("  接取任务: 5-&gt;5-&gt;*...")
        self._tap_key5()
        time.sleep(0.8)
        self._tap_key5()
        time.sleep(0.8)
        self._safe_touch((150, 1790))  # *号键一键接取
        self.log("  *号接取完成")
        time.sleep(3.0)

    def _auto_battle_phase(self, count: int = 2):
        """键0开启自动遇怪，等N场战斗后键0取消（0键是toggle，取消只按1次）"""
        self.log(f"  按键0 开启自动遇怪...")
        self._safe_touch((950, 1590))  # KEY0
        time.sleep(1.0)

        battles = 0
        while battles < count and self._running:
            if self._is_in_battle():
                battles += 1
                self.log(f"  第{battles}场战斗...")
                self._wait_battle_end()
                self.log(f"  第{battles}场结束!")
            time.sleep(BATTLE_CHECK_INTERVAL)

        # 取消前：确保战斗+结算彻底结束（0键落在战斗/结算界面会无效）
        self._ensure_not_in_battle("取消遇怪前")

        # 取消：只按1次（多按会把 toggle 重新切换为开启）
        self.log(f"  按键0 取消自动遇怪")
        self._safe_touch((950, 1590))
        time.sleep(1.0)

        # 取消后：角色可能已锁定下一只怪，最多等2场残留战斗结束（不再按0）
        for i in range(2):
            if not self._running:
                break
            time.sleep(2.0)
            if self._is_in_battle():
                self.log(f"  残留战斗(第{i + 1}场)，等待结束...")
                self._wait_battle_end()
            else:
                break
        self.log(f"  自动遇怪已取消")

    def _quest_teleport(self):
        """任务列表-&gt;确认-&gt;瞬间传送-&gt;提交任务"""
        self.log_key("── 任务传送阶段 ──")
        self._tap(KEY1, "任务列表(1)", WAIT_PAGE)
        self._tap(STEP_CONFIRM, "确认", WAIT_PAGE)
        self._tap((500, 790), "瞬间传送", WAIT_TELEPORT)
        self.log_key("  传送完成")
        time.sleep(2.0)
        # 传送出副本后已在安全区，不再做战斗检测（阳谷UI的"自动"按钮会误触发_is_in_battle）
        self._submit_quest(check_battle=False)
        self.log_key("  提交完成")

    # ── 断点续跑 (状态文件) ──────────────────────

    @property
    def _state_file(self) -> str:
        safe = self._serial.replace(":", "_").replace("/", "_") if self._serial else "default"
        return os.path.join(LOG_DIR, f"dungeon100_state_{safe}.json")

    def _load_progress(self) -> int:
        """返回已完成的 Phase 编号，-1 表示无记录"""
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
            self.log_key(f"[进度] Phase {phase}/9 完成")
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
        self.log_key(f"══ Phase {n}/9: {desc} ══")

    # ── 主流程 ─────────────────────────────────

    def run(self):
        self.log_key("100副本启动")
        self._battle_count = 0

        # 断点续跑: 确定起始 Phase
        if self._start_phase is None:
            done = self._load_progress()
            start_phase = done + 1
            if start_phase > 0:
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

        # Phase 0: 阳谷 -&gt; 惊凡渊 进入副本
        if start_phase <= 0:
            self._log_phase(0, "进入副本")
            self._enter_dungeon()
            self._save_progress(0)

        # Phase 1: 惊凡渊 -&gt; 裂影渊 走路+传送门
        if start_phase <= 1:
            self._log_phase(1, "惊凡渊→裂影渊 走路+传送门")
            self._walk_phase()
            self._portal_phase()
            self._save_progress(1)
            self.log_key(f"裂影渊到达! 累计 {self._battle_count} 场战斗")

        # Phase 2: 裂影渊 找洞渊战魂 -&gt; 交任务 -&gt; 接任务(触发Boss)
        if start_phase <= 2:
            self._log_phase(2, "裂影渊 找洞渊战魂→交任务→接任务")
            if self._battle_count < 2:
                remaining = 2 - self._battle_count
                self.log_key(f"战斗不足2场(当前{self._battle_count})，自动遇怪补{remaining}场")
                self._auto_battle_phase(remaining)
            self._npc_phase(TARGET_NPC)
            self._submit_quest()            # 5-&gt;5-&gt;* 交任务
            self._accept_quest()            # 5-&gt;5-&gt;* 接任务 (触发洞渊战魂Boss战)
            self._save_progress(2)

        # Phase 3: 裂影渊 洞渊战魂Boss战 -&gt; 交任务 -&gt; 接任务
        if start_phase <= 3:
            self._log_phase(3, "裂影渊 洞渊战魂Boss战→交任务→接任务")
            self.log_key("  等待洞渊战魂Boss战...")
            self._wait_battle_end(is_boss=True)   # 打洞渊战魂Boss
            self.log_key("  洞渊战魂击杀完成!")
            self._submit_quest()            # 5-&gt;5-&gt;* 交任务
            self._accept_quest()            # 5-&gt;5-&gt;* 接任务
            self._battle_count = 0          # 裂影渊boss完成，重置进入下一区域
            self._save_progress(3)

        # Phase 4: 裂影渊 -&gt; 泣魔渊 传送门
        if start_phase <= 4:
            self._log_phase(4, "裂影渊→泣魔渊 传送门")
            self._portal_phase()
            self._save_progress(4)
            self.log_key("泣魔渊到达!")

        # Phase 5: 泣魔渊 -&gt; 陨仙渊 走路+传送门
        if start_phase <= 5:
            self._log_phase(5, "泣魔渊→陨仙渊 走路+传送门")
            self._walk_phase()
            self._portal_phase()
            self._save_progress(5)
            self.log_key("陨仙渊到达!")

        # Phase 6: 陨仙渊 找百鬼之王 -&gt; 交任务 -&gt; 接任务
        if start_phase <= 6:
            self._log_phase(6, "陨仙渊 找百鬼之王→交任务→接任务")
            if self._battle_count < 2:
                remaining = 2 - self._battle_count
                self.log_key(f"战斗不足2场(当前{self._battle_count})，自动遇怪补{remaining}场")
                self._auto_battle_phase(remaining)
            self._npc_phase(TARGET_NPC2)
            self._submit_quest()            # 5-&gt;5-&gt;* 交任务
            self._accept_quest()            # 5-&gt;5-&gt;* 接任务
            self._battle_count = 0          # 重置，下一阶段重新累计
            self._save_progress(6)

        # Phase 7: 陨仙渊 遇怪2场 -&gt; 找百鬼之王 -&gt; 交任务 -&gt; 接任务(触发Boss)
        if start_phase <= 7:
            self._log_phase(7, "陨仙渊 遇怪2场→找百鬼之王→交任务→接任务")
            self._auto_battle_phase(2)
            self._npc_phase(TARGET_NPC2)
            self._submit_quest()            # 5-&gt;5-&gt;* 交任务
            self._accept_quest()            # 5-&gt;5-&gt;* 接任务 (触发Boss战)
            self._save_progress(7)

        # Phase 8: 陨仙渊 百鬼之王Boss战 -&gt; 交任务 -&gt; 接任务(x2)
        if start_phase <= 8:
            self._log_phase(8, "陨仙渊 百鬼之王Boss战→交任务→接任务×2")
            self.log_key("  等待Boss战...")
            self._wait_battle_end(is_boss=True)
            self.log_key("  Boss战结束!")
            self._submit_quest()            # 5-&gt;5-&gt;* 交任务
            self._accept_quest()            # 5-&gt;5-&gt;* 接任务
            self._submit_quest()            # 5-&gt;5-&gt;* 交任务(最后一轮)
            self._accept_quest()            # 5-&gt;5-&gt;* 接任务
            self._save_progress(8)

        # Phase 9: 陨仙渊 -&gt; 阳谷 传送出地图+提交任务
        if start_phase <= 9:
            self._log_phase(9, "陨仙渊→阳谷 传送出地图+提交任务")
            self._quest_teleport()
            self._save_progress(9)

        self._clear_progress()
        self.log_key(f"100副本流程完成! 累计 {self._battle_count} 场战斗")
