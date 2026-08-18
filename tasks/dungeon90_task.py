"""90副本(青丘境)任务 —— 步骤0传送 + 青丘入口/灵隐绝境/禁忌古道/迷影禁地 多地图流转

断点续跑: 每个 Phase 完成后写状态文件 logs/dungeon90_state_{serial}.json
手动/自动: start_phase=None 自动续跑; =0 从头开始; =N 手动从 Phase N 开始
"""
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
# 步骤0: 备忘→副本→翻页→OCR找青丘境→瞬间传送
MEMO = (1000, 1200)              # 备忘
DUNGEON_TAB = (750, 200)         # 副本标签
KEY3 = (730, 1590)               # 数字键3 翻页
KEY0 = (950, 1590)               # 数字键0 自动遇怪
KEY5 = (150, 1590)               # 数字键5 确认/对话
KEY_STAR = (150, 1790)           # *号键 一键领/交
ENTER_CONFIRM = (100, 1200)      # 确认进入/缴费进入

# 走路传送门 (检测地图名变化即停)
LEFT_DOWN = (20, 1100)           # 左下角
LEFT_UP = (20, 400)              # 左上角
RIGHT_DOWN = (1050, 1100)        # 右下角
RIGHT_UP = (1050, 400)           # 右上角
PORTAL_50 = (50, 600)            # 禁忌古道传送门

# NPC列表 (复用100副本坐标)
NEARBY_BTN = (350, 1780)         # 周围列表按钮
NPC_TAB = (750, 250)             # NPC标签
ROW_X = 180                      # 点击行内X位置
ROW_Y_START = 450                # 第一行Y
ROW_SPACING = 120                # 行间距
ROW_COUNT = 7                    # 一页最多行数
NEXT_PAGE = (520, 1330)          # 翻页按钮
AUTO_PATHFIND = (500, 660)       # 自动寻路按钮
CANCEL_PANELS = [(950, 1200), (950, 1450)]
PANEL_TITLE_CHECK = (500, 100)   # "周围列表"检测
PANEL_TITLE_SPREAD = 200

# 战斗检测 (round不可靠须0.85, manual可靠0.7)
ROUND_CHECK = (500, 200)
ROUND_RANGE = 80
ROUND_THRESHOLD = 0.85
MANUAL_CHECK = (1000, 1450)
MANUAL_RANGE = 80
MANUAL_THRESHOLD = 0.7

# 地图名检测 crop: y1,y2,x1,x2
MAP_NAME_CROP = (50, 200, 830, 1040)

# 间隔
WAIT_CLICK = 0.3                 # 点击后等待
WAIT_STEP = 3.0                  # 走路每步间隔
BATTLE_CHECK_INTERVAL = 0.5      # 战斗检测频率


class Dungeon90Task(BaseTask):
    """90副本自动任务 — 青丘境 12 Phase 完整流程"""

    def __init__(self, serial: str = "", start_phase: int = None):
        super().__init__("90副本")
        self._serial = serial
        self._reader = None
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
        import shutil
        if not shutil.which(adb):
            adb = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
        tmp = os.path.join(LOG_DIR, f"_dungeon90_tmp_{os.getpid()}.png")
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

    # ── 战斗检测 (模板匹配) ─────────────────────

    _tpl_round = None
    _tpl_manual = None

    def _load_templates(self):
        if self._tpl_round is None:
            tpl_dir = os.path.join(BASE_DIR, "templates", "tianyuan")
            self._tpl_round = cv2.imread(os.path.join(tpl_dir, "round.png"))
            self._tpl_manual = cv2.imread(os.path.join(tpl_dir, "manual.png"))

    def _match_template(self, arr, tpl, cx, cy, spread, threshold=0.7) -> bool:
        h, w = arr.shape[:2]
        y1, y2 = max(0, cy - spread), min(h, cy + spread)
        x1, x2 = max(0, cx - spread), min(w, cx + spread)
        if y2 <= y1 or x2 <= x1:
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
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        self._load_templates()
        if self._match_template(arr, self._tpl_round,
                                ROUND_CHECK[0], ROUND_CHECK[1], ROUND_RANGE, ROUND_THRESHOLD):
            return True
        if self._match_template(arr, self._tpl_manual,
                                MANUAL_CHECK[0], MANUAL_CHECK[1], MANUAL_RANGE, MANUAL_THRESHOLD):
            return True
        return False

    def _wait_battle_end(self, is_boss: bool = False):
        miss = 0
        t0 = time.time()
        while self._running and time.time() - t0 < 60:
            time.sleep(0.3)
            if self._is_in_battle():
                miss = 0
            else:
                miss += 1
                if miss >= 2 and time.time() - t0 >= 3.0:  # 最短3s，过滤开场过渡误判
                    break
        if not self._running:
            return
        time.sleep(12.0 if is_boss else 0.2)

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

    # ── 地图名 ──────────────────────────────────

    def _get_map_name(self) -> str:
        arr = self._stream_frame()
        if arr is None:
            arr = self._screenshot_arr()
        if arr is None:
            return ""
        y1, y2, x1, x2 = MAP_NAME_CROP
        crop = arr[y1:y2, x1:x2, :]
        reader = self._get_reader()
        try:
            results = reader.readtext(crop, mag_ratio=1)
        except Exception:
            return ""
        return "".join(r[1] for r in results if r[2] >= 0.2)

    # ── OCR 全图找文字 (步骤0用) ─────────────────

    def _find_text_in_area(self, keyword, y_start, y_end, x_start=0, x_end=540):
        arr = self._screenshot_arr()
        if arr is None:
            return None
        reader = self._get_reader()
        try:
            res = reader.readtext(arr, mag_ratio=1)
        except Exception:
            return None
        for r in sorted(res, key=lambda r: (r[0][0][1], r[0][0][0])):
            bbox, text, conf = r
            if conf < 0.3 or keyword not in text:
                continue
            cx = int((bbox[0][0] + bbox[2][0]) / 2)
            cy = int((bbox[0][1] + bbox[2][1]) / 2)
            if x_start <= cx <= x_end and y_start <= cy <= y_end:
                return (cx, cy)
        return None

    # ── Phase 0: 步骤0传送 + 第一大步进入副本 ──────

    def _handle_vip_teleport_popup(self):
        """点击瞬间传送后，vip3会弹'是否传送'确认框，需多按一次数字键5；无弹窗(高vip)则跳过"""
        if self._check_text_at("是否传送", (540, 700), 300):
            self.log_key("  检测到vip免费传送弹窗，多按一次5确认")
            self._tap_key5()
            time.sleep(1.0)

    def _step0_memo_enter(self):
        self.log_key("── 步骤0: 备忘→副本→翻页→OCR找青丘境→瞬间传送 ──")
        self._tap(MEMO, "备忘", 1.2)
        self._tap(DUNGEON_TAB, "副本标签", 1.2)
        self._tap(KEY3, "数字键3翻页", 1.5)
        pos = self._find_text_in_area("青丘境", 380, 1250)
        if pos is None:
            pos = self._find_text_in_area("青丘", 380, 1250)
        if pos is None:
            self.log_key("  [失败] 未找到青丘境行")
            return False
        self.log_key(f"  找到青丘境 @ {pos}")
        self._safe_touch((250, pos[1])); time.sleep(1.0)
        self._safe_touch((250, pos[1])); time.sleep(1.0)
        tp = self._find_text_in_area("瞬间传送", 400, 1200, 0, 1080)
        if tp is None:
            self.log_key("  [失败] 未找到瞬间传送")
            return False
        self.log_key(f"  找到瞬间传送 @ {tp}")
        self._safe_touch(tp); time.sleep(3.0)
        self._handle_vip_teleport_popup()
        self.log_key("  步骤0完成，已传送到副本入口")
        return True

    def _enter_dungeon(self):
        self.log_key("── 第一大步: NPC对话进入副本 ──")
        self._safe_touch(KEY5); time.sleep(1.0)
        self._safe_touch(KEY5); time.sleep(1.0)
        self._safe_touch(KEY_STAR); time.sleep(1.0)
        self._safe_touch(KEY5); time.sleep(1.0)
        self._safe_touch(ENTER_CONFIRM); time.sleep(0.8)
        self._safe_touch(ENTER_CONFIRM); time.sleep(3.0)
        self.log_key(f"  进入后地图: '{self._get_map_name()}'")

    # ── 走路阶段 (检测地图名变化即停) ─────────────

    def _walk_phase(self, desc, pos, target_check, times=3):
        self.log_key(f"── {desc} 点 {times} 次 ──")
        for i in range(times):
            if not self._running:
                return False
            if self._is_in_battle():
                self.log_key(f"  第{i + 1}次前遇怪! 等待战斗结束...")
                self._wait_battle_end()
            self._safe_touch(pos)
            # 点击后立即轮询地图名(视频流快), 地图名横幅一出现就停, 避免等 WAIT_STEP 错过
            t0 = time.time()
            name = ""
            while time.time() - t0 < WAIT_STEP and self._running:
                time.sleep(0.4)
                name = self._get_map_name()
                if target_check(name):
                    self.log_key(f"  第{i + 1}次后 地图: '{name}' [地图已变!]")
                    return True
            self.log_key(f"  第{i + 1}次后 地图: '{name}'")
        return False

    # ── 自动遇怪 ────────────────────────────────

    def _auto_battle_phase(self, count=2):
        if self._is_in_battle() and self._running:
            self.log_key("  开启自动遇怪前遇怪! 等待战斗结束...")
            self._wait_battle_end()
        self.log_key(f"  按键0 开启自动遇怪 (目标{count}场)...")
        self._safe_touch(KEY0); time.sleep(1.0)
        battles = 0
        t0 = time.time()
        while battles < count and time.time() - t0 < 300 and self._running:
            if self._is_in_battle():
                battles += 1
                self.log_key(f"  [战斗] 第{battles}场开始...")
                self._wait_battle_end()
                self.log_key(f"  [战斗] 第{battles}场结束")
            time.sleep(0.3)
        self.log_key(f"  按键0 取消自动遇怪 (共{battles}场)")
        self._safe_touch(KEY0); time.sleep(0.5)

    def _boss_battle(self):
        self.log_key("  等待 Boss 战触发...")
        t0 = time.time()
        triggered = False
        while time.time() - t0 < 30 and self._running:
            if self._is_in_battle():
                triggered = True
                self.log_key("  检测到 Boss 战!")
                break
            time.sleep(0.5)
        if not triggered:
            self.log_key("  [警告] 30s 未检测到 Boss 战")
        self._wait_battle_end(is_boss=True)
        self.log_key("  Boss 战结束!")

    # ── NPC扫描阶段 (复用100副本) ────────────────

    def _check_text_at(self, keyword, center, spread) -> bool:
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
                self.log(f"  检测到误开面板 @({cx},{cy})，点击取消关闭")
                self._safe_touch((cx, cy))
                time.sleep(0.5)
                return True
        return False

    def _open_npc_list(self):
        for retry in range(3):
            self.log(f"  打开周围列表... (尝试{retry + 1}/3)")
            # 点击前检查战斗：战斗状态下点击会无效
            if self._is_in_battle():
                self.log("  打开列表前遇怪! 等待战斗结束...")
                self._wait_battle_end()
                time.sleep(0.5)
            self._safe_touch(NEARBY_BTN)
            time.sleep(1.5)
            if self._check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
                self.log("  '周围列表'已打开")
            else:
                self.log("  未检测到'周围列表'，尝试关闭误开面板...")
                self._dismiss_panels()
                time.sleep(0.5)
                continue
            # 点击NPC标签前检查战斗
            if self._is_in_battle():
                self.log("  打开NPC标签前遇怪! 等待战斗结束...")
                self._wait_battle_end()
            self._safe_touch(NPC_TAB)
            time.sleep(1.2)
            return True
        self.log("  NPC面板多次重试失败")
        return False

    def _scan_npc_page(self) -> list:
        arr = self._screenshot_arr()
        if arr is None:
            return []
        h, w = arr.shape[:2]
        reader = self._get_reader()
        results_list = []
        ts = time.strftime("%H%M%S")
        try:
            Image.fromarray(arr).save(os.path.join(LOG_DIR, f"_dungeon90_npc_{ts}.png"))
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
                    text, conf = r[1], r[2]
                    if conf < 0.05:
                        continue
                    self.log(f"    Row{i} Y={yc}: OCR='{text}' conf={conf:.2f}")
                    results_list.append((text, yc))
                    break
                break
        self.log(f"  [扫描NPC] 完成: {len(results_list)} 条")
        return results_list

    def _find_npc(self, target):
        for page in range(1, 5):
            self.log(f"  查找'{target}' — 第{page}页...")
            self._open_npc_list()
            npcs = self._scan_npc_page()
            for name, y in npcs:
                if target in name or name in target:
                    self.log(f"  找到: '{name}' @ Y={y}")
                    return (name, y)
                common = sum(1 for ch in name if ch in target)
                if common >= 2:
                    self.log(f"  模糊匹配: '{name}' ~ '{target}' @ Y={y}")
                    return (name, y)
            if page < 4:
                self.log(f"  第{page}页未找到，翻页...")
                if self._is_in_battle():
                    self.log("  翻页前遇怪! 等待战斗结束...")
                    self._wait_battle_end()
                self._safe_touch(NEXT_PAGE)
                time.sleep(0.8)
            else:
                self.log(f"  翻页{page}次仍未找到'{target}'")
        return None

    def _npc_phase(self, target_npc) -> bool:
        if self._is_in_battle():
            self.log_key("  找NPC前遇怪! 等待战斗结束...")
            self._wait_battle_end()
        result = self._find_npc(target_npc)
        if result is None:
            self.log_key(f"  [失败] 未找到{target_npc}，跳过")
            return False
        name, y = result
        # 点击NPC行前检查战斗(_find_npc 期间可能遇怪)
        if self._is_in_battle():
            self.log_key("  点击NPC前遇怪! 等待战斗结束...")
            self._wait_battle_end()
        self.log_key(f"  点击NPC: '{name}' @ Y={y}")
        self._safe_touch((ROW_X, y))
        time.sleep(0.5)
        if y == ROW_Y_START:
            self._safe_touch(KEY5)
        else:
            # 点击自动寻路前检查战斗
            if self._is_in_battle():
                self.log_key("  点击自动寻路前遇怪! 等待战斗结束...")
                self._wait_battle_end()
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
                    self.log_key(f"  寻路中遇怪! (第{attempt + 1}次)")
                    self._wait_battle_end()
                    self.log_key("  继续寻路...")
                    break
                time.sleep(0.3)
                elapsed += 0.3
            else:
                self.log("  寻路完成")
                break
        if self._is_in_battle():
            self._wait_battle_end()
        self.log_key(f"  到达 {target_npc}")
        return True

    def _submit_quest(self):
        self.log_key("  提交任务: 5→5→*...")
        self._tap_key5()
        time.sleep(0.8)
        self._tap_key5()
        time.sleep(0.8)
        self._safe_touch(KEY_STAR)
        self.log_key("  *号提交，等待12s结算...")
        time.sleep(12.0)

    def _accept_quest(self):
        self.log_key("  接取任务: 5→5→*...")
        self._tap_key5()
        time.sleep(0.8)
        self._tap_key5()
        time.sleep(0.8)
        self._safe_touch(KEY_STAR)
        self.log_key("  *号接取完成")
        time.sleep(3.0)

    # ── 断点续跑 (状态文件) ──────────────────────

    @property
    def _state_file(self) -> str:
        safe = self._serial.replace(":", "_").replace("/", "_") if self._serial else "default"
        return os.path.join(LOG_DIR, f"dungeon90_state_{safe}.json")

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
            self.log_key(f"[进度] Phase {phase}/11 完成")
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
        self.log_key(f"══ Phase {n}/12: {desc} ══")

    # ── 主流程 ─────────────────────────────────

    def run(self):
        self.log_key("90副本启动")

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

        # Phase 0: 步骤0 传送 (备忘→副本→翻页→青丘境→瞬间传送)
        if start_phase <= 0:
            self._log_phase(0, "传送(备忘→副本→青丘境→瞬间传送)")
            self._step0_memo_enter()
            self._save_progress(0)

        # Phase 1: 第一大步 进入副本 (NPC对话)
        if start_phase <= 1:
            self._log_phase(1, "进入副本(NPC对话)")
            self._enter_dungeon()
            self._save_progress(1)

        # Phase 2: 青丘入口 遇怪2次 → 进灵隐绝境
        if start_phase <= 2:
            self._log_phase(2, "青丘入口 遇怪2次→进灵隐绝境")
            self._auto_battle_phase(2)
            if not self._walk_phase("左下角", LEFT_DOWN, lambda n: "灵隐" in n):
                self._walk_phase("左上角", LEFT_UP, lambda n: "灵隐" in n)
            self._save_progress(2)

        # Phase 3: 灵隐绝境 找瑞南羽 → 交 → 接 (触发Boss)
        if start_phase <= 3:
            self._log_phase(3, "灵隐绝境 找瑞南羽→交→接")
            if self._npc_phase("瑞南羽"):
                self._submit_quest()
                self._accept_quest()
            self._save_progress(3)

        # Phase 4: 瑞南羽Boss战 → 交 → 接
        if start_phase <= 4:
            self._log_phase(4, "瑞南羽Boss战→交→接")
            self._boss_battle()
            self._submit_quest()
            self._accept_quest()
            self._save_progress(4)

        # Phase 5: 回青丘入口
        if start_phase <= 5:
            self._log_phase(5, "回青丘入口")
            if not self._walk_phase("右下角", RIGHT_DOWN, lambda n: "青丘" in n):
                self._walk_phase("右上角", RIGHT_UP, lambda n: "青丘" in n)
            self._save_progress(5)

        # Phase 6: 青丘入口 遇怪2次 → 进灵隐绝境
        if start_phase <= 6:
            self._log_phase(6, "青丘入口 遇怪2次→进灵隐绝境")
            self._auto_battle_phase(2)
            if not self._walk_phase("左下角", LEFT_DOWN, lambda n: "灵隐" in n):
                self._walk_phase("左上角", LEFT_UP, lambda n: "灵隐" in n)
            self._save_progress(6)

        # Phase 7: 灵隐绝境 找瑞南羽 → 交 → 接
        if start_phase <= 7:
            self._log_phase(7, "灵隐绝境 找瑞南羽→交→接")
            if self._npc_phase("瑞南羽"):
                self._submit_quest()
                self._accept_quest()
            self._save_progress(7)

        # Phase 8: 进禁忌古道 → 遇怪2次 → 回灵隐
        if start_phase <= 8:
            self._log_phase(8, "进禁忌古道→遇怪2次→回灵隐")
            self._safe_touch(PORTAL_50); time.sleep(3.0)
            self._auto_battle_phase(2)
            if not self._walk_phase("右下角", RIGHT_DOWN, lambda n: "灵隐" in n):
                self._walk_phase("右上角", RIGHT_UP, lambda n: "灵隐" in n)
            self._save_progress(8)

        # Phase 9: 灵隐绝境 找瑞南羽 → 交 → 接
        if start_phase <= 9:
            self._log_phase(9, "灵隐绝境 找瑞南羽→交→接")
            if self._npc_phase("瑞南羽"):
                self._submit_quest()
                self._accept_quest()
            self._save_progress(9)

        # Phase 10: 进禁忌古道 → 进迷影禁地
        if start_phase <= 10:
            self._log_phase(10, "进禁忌古道→进迷影禁地")
            self._safe_touch(PORTAL_50); time.sleep(3.0)
            if not self._walk_phase("右下角", RIGHT_DOWN, lambda n: "迷影" in n):
                self._walk_phase("左下角", LEFT_DOWN, lambda n: "迷影" in n)
            self._save_progress(10)

        # Phase 11: 迷影禁地 找九尾异兽 → 交 → 接 (触发Boss)
        if start_phase <= 11:
            self._log_phase(11, "迷影禁地 找九尾异兽→交→接")
            if self._npc_phase("九尾异兽"):
                self._submit_quest()
                self._accept_quest()
            self._save_progress(11)

        # Phase 12: 九尾异兽Boss战 → 交 → 接 → 交
        if start_phase <= 12:
            self._log_phase(12, "九尾异兽Boss战→交→接→交")
            self._boss_battle()
            self._submit_quest()
            self._accept_quest()
            self._submit_quest()
            self._save_progress(12)

        self._clear_progress()
        self.log_key("90副本流程完成!")
