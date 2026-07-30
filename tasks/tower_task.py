"""玄兵塔任务 —— OCR识别NPC列表 + 回合检测战斗 + 名单模糊匹配"""
import time
import os
import numpy as np
from PIL import Image, ImageDraw
from airtest.core.api import touch as _air_touch, exists, Template, snapshot
from airtest.core.settings import Settings as ST
from tasks.base_task import BaseTask

ST.CVSTRATEGY = ["tpl"]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ── 坐标配置 (1080x1920) ──────────────────────
NEARBY_BTN = (350, 1780)       # 周围列表按钮(数字键7位置，避开聊天框)
NPC_TAB = (750, 250)           # NPC标签
ROW_X = 180                    # 点击行内X位置
ROW_Y_START = 450              # 第一行Y
ROW_SPACING = 120              # 行间距
ROW_COUNT = 7                  # 一页最多行数
NEXT_PAGE = (520, 1330)        # 翻页按钮
AUTO_PATHFIND = (500, 660)     # 自动寻路按钮(弹出对话框后)
TELEPORTER_KEY = "传送师"

# 战斗检测坐标
ROUND_CHECK = (500, 200)       # 回合文字区域(战斗中可见)
ROUND_RANGE = 200              # 检测范围±200px
BATTLE_MODE_CHECK = (1000, 1450)  # 自动/手动按钮区域(战斗中可见)
BATTLE_MODE_RANGE = 100           # 检测范围±100px
SETTLE_CHECK = (800, 950)      # "按5键继续"区域(结算弹窗)
SETTLE_RANGE = 200             # 检测范围±200px
CONFIRM_BTN = (150, 1600)      # 确认键(数字5)
CANCEL_BTN = (974, 1215)      # 取消按钮(弹窗关闭)
POPUP_KEYWORDS = ["进入战", "以后再"]  # 弹窗关键词

# 误开面板关闭坐标（需OCR确认"取消"存在后才点击）
CANCEL_PANELS = [
    (950, 1200),   # 进入战斗面板
    (950, 1450),   # 聊天记录面板
]

# NPC列表面板验证坐标
PANEL_TITLE_CHECK = (500, 100)   # 顶部中央，检测"周围列表"标题
PANEL_TITLE_SPREAD = 200          # 检测范围

# Boss弹窗坐标
BOSS_ENTER_BATTLE = (500, 600) # 进入战斗
BOSS_NEXT_FLOOR = (500, 730)   # 跳转下一层

# ── 等待时间 ──────────────────────────────────
WAIT_PATHFIND = 4.0            # 寻路等待
BATTLE_CHECK_INTERVAL = 0.5    # 战斗检测间隔
SETTLE_CHECK_INTERVAL = 0.5    # 结算检测间隔

# ── 7层怪物名单 ──────────────────────────────
FLOOR_MONSTERS = {
    1: ["离火剑", "散瘟鞭", "落宝金钱", "列瘟印", "紫金铃", "撞心杵",
        "风火轮", "酱油瓶", "乾坤针", "斩仙飞刀"],
    2: ["风袋", "梅花镖", "六根清净竹", "雾露乾坤网", "戳目珠", "照妖鉴",
        "长生根", "伤不旗", "逆鳞枪", "宝莲灯"],
    3: ["万里起云烟", "钻心钉", "万鸦壶", "紫金钵", "定风珠", "鬼神甲",
        "穿天弩", "咆哮梯", "金光锉", "五行旗"],
    4: ["乱心尘", "阴阳二气瓶", "劈地珠", "杏黄旗", "阴阳刃", "穿心锁",
        "三尖两刃枪", "浮云", "金霞冠", "伏羲琴"],
    5: ["落魂钟", "焰光旗", "化血神刀", "日月珠", "定海珠", "破军",
        "开天珠", "火星帖", "混元锤", "翻天印"],
    6: ["四象塔", "天荡", "降魔杵", "乾坤圈", "如意乾坤袋", "捆仙绳",
        "招妖幡", "杯具", "水火锋", "苍刑逆天枪"],
    7: ["黑砂", "混元幡", "乾坤弓", "落魄镜", "听谛印", "照天印",
        "遁龙桩", "鸭梨", "缚龙索", "混沌钟"],
}


def _fuzzy_match(ocr_text: str, candidates: list[str]) -> str | None:
    """OCR文字模糊匹配已知名单，返回最佳匹配或None"""
    if not ocr_text:
        return None
    if ocr_text in candidates:
        return ocr_text
    for c in candidates:
        if ocr_text in c or c in ocr_text:
            return c
    for c in candidates:
        common = sum(1 for ch in ocr_text if ch in c)
        if common >= 1 and common >= len(c) * 0.5:
            return c
    return None


class TowerTask(BaseTask):
    """玄兵塔自动清怪"""

    TOTAL_FLOORS = 7
    DEBUG_CLICK = True  # 调试模式：每次点击后截图标注红圈

    def __init__(self, serial: str = ""):
        super().__init__("玄兵塔")
        self._reader = None
        self._cleared = 0
        self._known_names = []
        self._click_seq = 0
        self._serial = serial

    def _get_reader(self):
        if self._reader is None:
            import easyocr
            self.log("加载OCR模型...")
            self._reader = easyocr.Reader(['ch_sim'], gpu=False, verbose=False)
            self.log("OCR模型就绪")
        return self._reader

    # ── 调试触摸 ────────────────────────────────

    def _touch(self, pos: tuple, label: str = ""):
        """带红圈标注的触摸"""
        x, y = pos
        desc = f"{label}({x},{y})" if label else f"({x},{y})"
        self._click_seq += 1
        self.log(f"  [点击#{self._click_seq}] {desc}")

        if self.DEBUG_CLICK:
            try:
                screen = self._screenshot_arr()
                img = Image.fromarray(screen)
                draw = ImageDraw.Draw(img)
                r = 30
                # 画红色同心圆
                for w in [4, 2]:
                    draw.ellipse([x - r, y - r, x + r, y + r], outline="red", width=w)
                # 画十字线
                draw.line([(x - r, y), (x + r, y)], fill="red", width=2)
                draw.line([(x, y - r), (x, y + r)], fill="red", width=2)
                # 序号
                draw.text((x + 35, y - 10), f"#{self._click_seq}", fill="red")
                os.makedirs(LOG_DIR, exist_ok=True)
                ts = time.strftime("%H%M%S")
                fn = os.path.join(LOG_DIR,
                    f"click_{self._click_seq:02d}_{desc}_{ts}.png")
                img.save(fn)
            except Exception:
                pass

        _air_touch(pos)

    # ── 楼层检测 ────────────────────────────────

    def _detect_current_floor(self) -> int | None:
        """扫描NPC列表第一个怪物，反查属于哪一层，用于断点续打"""
        self.log("  检测当前所在层...")
        all_names = [n for names in FLOOR_MONSTERS.values() for n in names]
        saved = self._known_names
        self._known_names = all_names
        try:
            self._open_npc_list()
            monsters = self._scan_npc_page()
        finally:
            self._known_names = saved

        for name, y in monsters:
            if TELEPORTER_KEY in name:
                continue
            for floor, names in FLOOR_MONSTERS.items():
                if name in names:
                    self.log(f"  检测到: {name} → 第{floor}层")
                    return floor

        self.log("  无法检测当前层，从第1层开始")
        return None

    # ── 主循环 ────────────────────────────────

    def run(self):
        start_floor = self._detect_current_floor() or 1
        for floor in range(start_floor, self.TOTAL_FLOORS + 1):
            if not self._running:
                break
            self.log(f"══════ 第 {floor} 层 ══════")
            self._known_names = FLOOR_MONSTERS.get(floor, [])
            self._clear_floor(floor)
            if not self._running:
                break
            if floor < self.TOTAL_FLOORS:
                self._go_next_floor(floor)
        if self._running:
            self.log(f"玄兵塔全部通关! 共击败 {self._cleared} 个怪物")

    def _clear_floor(self, floor: int):
        page = 1
        while self._running:
            self.log(f"  ── 第{floor}层 第{page}页 ──")
            self._open_npc_list()
            result = self._scan_and_kill(floor)

            if result == "boss":
                self.log(f"  ✓ 本层Boss已击杀")
                break

            if not result:
                self.log(f"  第{page}页无怪物，翻页...")
                self._touch(NEXT_PAGE, "翻页")
                time.sleep(0.5)
                page += 1
                result2 = self._scan_and_kill(floor)
                if result2 == "boss":
                    self.log(f"  ✓ 本层Boss已击杀")
                    break
                if not result2:
                    self.log(f"  第{page}页也无怪物 → 本层已清完")
                    break

    def _scan_and_kill(self, floor: int):
        monsters = self._scan_npc_page()
        valid = [(name, y) for name, y in monsters
                 if TELEPORTER_KEY not in name]

        self.log(f"  怪物: {[m[0] for m in valid]}, "
                 f"传送师={'有' if any(TELEPORTER_KEY in m[0] for m in monsters) else '无'}")

        if not valid:
            return False

        name, y = valid[0]
        self.log(f"  >>> {name} (Y={y})")

        boss_name = FLOOR_MONSTERS[floor][-1]
        is_boss = _fuzzy_match(name, [boss_name]) is not None
        self._engage_monster(name, y, is_boss=is_boss)
        self._cleared += 1
        return "boss" if is_boss else True

    # ── NPC列表 ────────────────────────────────

    def _dismiss_panels(self) -> bool:
        """检测并关闭误打开的面板（进入战斗/聊天记录），返回是否关闭了面板"""
        for cx, cy in CANCEL_PANELS:
            if self._check_text_at("取消", (cx, cy), 100):
                self.log(f"  检测到误开面板 @({cx},{cy})，点击取消关闭")
                self._touch((cx, cy), "关闭误开面板")
                time.sleep(0.5)
                return True
        return False

    def _verify_npc_panel(self) -> bool:
        """检查NPC列表面板是否已正确打开（顶部中央应有'周围列表'字样）"""
        # 先检测正确的NPC列表标题
        if self._check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            self.log("  [面板验证] '周围列表'已打开 ✓")
            return True

        # 不是周围列表 —— 检查是不是误开面板（有关闭按钮）
        wrong_type = None
        if self._check_text_at("聊天记录", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            wrong_type = "聊天记录"
        elif self._check_text_at("备忘", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
            wrong_type = "备忘"

        if wrong_type:
            self.log(f"  [面板验证] 检测到'{wrong_type}'，非NPC列表!")
            # 尝试找取消按钮关闭
            dismissed = self._dismiss_panels()
            if dismissed:
                self.log(f"  [面板验证] 已关闭'{wrong_type}'面板")
            else:
                self.log(f"  [面板验证] 未找到取消按钮，无法关闭")
            return False

        # 没检测到任何标题，可能是加载中/其他状态
        self.log("  [面板验证] 未检测到面板标题")
        return False

    def _open_npc_list(self):
        for retry in range(3):
            self.log(f"  打开周围列表... (尝试{retry+1}/3)")
            self._touch(NEARBY_BTN, "周围列表")
            time.sleep(1.5)

            if self._check_text_at("周围列表", PANEL_TITLE_CHECK, PANEL_TITLE_SPREAD):
                self.log("  '周围列表'已打开 ✓")
            else:
                self.log("  未检测到'周围列表'，寻找取消关闭误开面板...")
                self._dismiss_panels()
                time.sleep(0.5)
                continue

            self._touch(NPC_TAB, "NPC标签")
            time.sleep(1.2)

            if self._verify_npc_panel():
                return
            self.log(f"  NPC面板未正确打开，重试...")

        self.log("  ⚠ NPC面板多次重试失败，继续尝试扫描")

    def _screenshot_arr(self) -> np.ndarray:
        import subprocess
        adb = os.environ.get("ANDROID_ADB", "adb")
        tmp = os.path.join(LOG_DIR, "_tower_tmp.png")
        adb_args = [adb]
        if self._serial:
            adb_args += ["-s", self._serial]
        try:
            subprocess.run(
                adb_args + ["shell", "screencap", "-p", "/sdcard/sc.png"],
                capture_output=True, timeout=5)
            subprocess.run(
                adb_args + ["pull", "/sdcard/sc.png", tmp],
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

    def _auto_correct_floor(self, monsters: list) -> int | None:
        """统计怪物属于哪层最多，若与当前层不同则自动纠正"""
        floor_votes = {}
        # 对每个OCR识别到的名字，找最佳匹配的楼层
        for ocr_name, y in monsters:
            if TELEPORTER_KEY in ocr_name:
                continue
            best_floor = None
            best_score = 0
            for floor, names in FLOOR_MONSTERS.items():
                # 严格匹配：exact > substring > 字符重叠（需更高阈值）
                score = 0
                if ocr_name in names:
                    score = 3  # 精确匹配
                else:
                    for c in names:
                        if ocr_name in c or c in ocr_name:
                            score = 2  # 子串匹配
                            break
                    if score == 0:
                        for c in names:
                            common = sum(1 for ch in ocr_name if ch in c)
                            if common >= 2 and common >= len(c) * 0.6:
                                score = 1  # 字符重叠（弱匹配）
                                break
                if score > best_score:
                    best_score = score
                    best_floor = floor
            if best_floor and best_score >= 1:
                floor_votes[best_floor] = floor_votes.get(best_floor, 0) + 1

        if not floor_votes:
            return None

        best_floor = max(floor_votes, key=floor_votes.get)
        best_count = floor_votes[best_floor]
        total = len([m for m in monsters if TELEPORTER_KEY not in m[0]])

        self.log(f"    [楼层投票] {dict(sorted(floor_votes.items()))}  total={total}")

        # 需要绝对多数（>50%）才纠正
        if best_count > total // 2:
            current = None
            for f, names in FLOOR_MONSTERS.items():
                if names == self._known_names:
                    current = f
                    break
            if current is not None and best_floor != current:
                self.log(f"    [楼层纠正] 第{current}层 → 第{best_floor}层 (投票{best_count}/{total})")
                self._known_names = FLOOR_MONSTERS.get(best_floor, self._known_names)
                return best_floor
        return None

    def _scan_npc_page(self) -> list:
        self.log(f"    [扫描NPC] 开始...")
        for retry in range(3):
            try:
                arr = self._screenshot_arr()
            except Exception as e:
                self.log(f"    [扫描NPC] 截图失败: {e}")
                return []

            # 检测画面过暗（加载/黑屏），等0.5秒重试
            mean_bright = float(np.mean(arr))
            if mean_bright < 100 and retry < 2:
                self.log(f"    [扫描NPC] 画面过暗(mean={mean_bright:.0f})，等待重试({retry+1}/2)...")
                time.sleep(0.5)
                continue
            break

        # 保存截图供调试
        ts = time.strftime("%H%M%S")
        debug_path = os.path.join(LOG_DIR, f"_npc_scan_{ts}.png")
        try:
            Image.fromarray(arr).save(debug_path)
        except Exception:
            pass

        reader = self._get_reader()
        monsters = []
        h, w = arr.shape[:2]
        self.log(f"    [扫描NPC] 截图成功 {w}x{h}, 逐行扫描...")

        for i in range(ROW_COUNT):
            yc = ROW_Y_START + i * ROW_SPACING
            y1, y2 = max(0, yc - 45), min(h, yc + 45)
            row = arr[y1:y2, 0:540, :]
            gray = np.mean(row, axis=2)
            dark_ratio = (gray < 80).mean()
            bright_mean = gray.mean()

            if dark_ratio < 0.02:
                self.log(f"    Row{i} Y={yc}: 空白 (dark={dark_ratio:.3f}) → 跳过")
                continue

            # 多种 mag_ratio 尝试，避免某个 ratio 对特定文字置信度极低
            all_results = []
            for mag in [1, 3]:
                try:
                    all_results.extend(reader.readtext(row, mag_ratio=mag))
                except Exception:
                    pass

            if not all_results:
                self.log(f"    Row{i} Y={yc}: dark={dark_ratio:.3f} bright={bright_mean:.0f} 有像素但OCR无结果 → 跳过")
                continue

            # 按置信度降序排列，逐个尝试模糊匹配
            results_sorted = sorted(all_results, key=lambda r: r[2], reverse=True)
            matched = None
            best_text = ""
            best_conf = 0.0

            for r in results_sorted:
                text = r[1]
                conf = r[2]

                # 弹窗关键词检测
                if any(kw in text for kw in POPUP_KEYWORDS):
                    self.log(f"    ⚠ 弹窗检测 [{text}]，点取消关闭")
                    self._touch(CANCEL_BTN, "取消弹窗")
                    time.sleep(0.5)
                    return []

                # 极低置信度跳过（但对有 dark 像素的行放低门槛）
                min_conf = 0.01 if dark_ratio >= 0.02 else 0.1
                if conf < min_conf:
                    continue

                matched = _fuzzy_match(text, self._known_names)
                if matched:
                    best_text = text
                    best_conf = conf
                    break

            if not matched:
                all_texts = [f"'{r[1]}'(c={r[2]:.2f})" for r in results_sorted[:3]]
                self.log(f"    Row{i} Y={yc}: dark={dark_ratio:.3f} 无匹配: {', '.join(all_texts)}")
                continue

            self.log(f"    Row{i} Y={yc}: dark={dark_ratio:.3f} OCR='{best_text}' conf={best_conf:.2f}")
            self.log(f"    Row{i} Y={yc}: '{best_text}' → {matched} ✓")
            monsters.append((matched, yc))

        # ── 智能楼层纠错 ──
        if monsters:
            corrected = self._auto_correct_floor(monsters)
            if corrected:
                # 用纠正后的楼层重新匹配
                self.log(f"    [扫描NPC] 楼层已纠正为第{corrected}层，重新匹配...")
                new_monsters = []
                for name, yc in monsters:
                    rematched = _fuzzy_match(name, FLOOR_MONSTERS.get(corrected, []))
                    if rematched:
                        new_monsters.append((rematched, yc))
                        self.log(f"      '{name}' → {rematched} ✓")
                monsters = new_monsters

        self.log(f"    [扫描NPC] 完成: 共识别 {len(monsters)} 个怪物")
        return monsters

    # ── 战斗流程 ────────────────────────────────

    def _engage_monster(self, name: str, y: int, is_boss: bool = False):
        self._touch((ROW_X, y), f"点击{name}")
        self.log(f"    等待对话框...")
        time.sleep(0.5)

        is_first = (y == ROW_Y_START)
        if is_first:
            self._touch(CONFIRM_BTN, "确认寻路")
        else:
            self._touch(AUTO_PATHFIND, "自动寻路")
            time.sleep(0.3)
            self._touch(CONFIRM_BTN, "确认寻路")
        self.log(f"    自动寻路中...")
        time.sleep(3.0)
        self.log(f"    进入战斗...")
        self._touch(CONFIRM_BTN, "确认弹窗")
        time.sleep(0.8)
        self._touch(CONFIRM_BTN, "确认战斗")
        time.sleep(1.0)
        self._touch(CONFIRM_BTN, "跳过对话")

        # 等待进入战斗（循环检测，最多等3秒）
        for _ in range(6):
            time.sleep(0.5)
            if self._is_in_battle():
                self.log("    进入战斗!")
                self.log(f"    战斗中...")
                self._wait_for_round_disappear()
                break

        # 跳过结算弹窗
        self._skip_settlement()

    def _is_in_battle(self) -> bool:
        """检测是否在战斗中：回合文字 或 自动/手动按钮（一次截图，减少耗时）"""
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
            crop = arr[y1:y2, x1:x2, :]
            try:
                results = reader.readtext(crop)
            except Exception:
                continue
            for r in results:
                if r[2] >= 0.1 and keyword in r[1]:
                    return True
        return False

    def _wait_for_round_disappear(self, timeout: float = 120.0):
        start = time.time()
        miss_count = 0
        while time.time() - start < timeout and self._running:
            if not self._is_in_battle():
                miss_count += 1
                if miss_count >= 4:  # 连续2秒没检测到才确认结束
                    self.log("    战斗结束!")
                    return True
            else:
                miss_count = 0
            time.sleep(BATTLE_CHECK_INTERVAL)
        return False

    def _skip_settlement(self, max_rounds: int = 10):
        """结算弹窗：检测'按5键继续'或'战斗胜利'→确认→直到消失"""
        self.log(f"    [结算检测] 开始(最多{max_rounds}轮)...")
        for i in range(max_rounds):
            if not self._running:
                return
            has_settle = self._check_text_present("按5键继续", SETTLE_CHECK, SETTLE_RANGE)
            has_victory = self._check_text_present("战斗胜利", (500, 500), 200)
            if has_settle or has_victory:
                detail = []
                if has_settle: detail.append("按5键继续")
                if has_victory: detail.append("战斗胜利")
                self.log(f"    [结算检测] 第{i+1}轮: 检测到{'/'.join(detail)} → 确认")
                self._touch(CONFIRM_BTN, "确认结算")
                time.sleep(SETTLE_CHECK_INTERVAL)
            else:
                time.sleep(0.3)
                has2 = self._check_text_present("按5键继续", SETTLE_CHECK, SETTLE_RANGE)
                has3 = self._check_text_present("战斗胜利", (500, 500), 200)
                if not has2 and not has3:
                    self.log(f"    [结算检测] 第{i+1}轮: 无弹窗 → 结束")
                    return
        self.log(f"    [结算检测] 完成({max_rounds}轮)")

    def _check_text_at(self, keyword: str, center: tuple, spread: int) -> bool:
        """检查指定坐标周围是否存在指定文字（conf>=0.1）"""
        try:
            arr = self._screenshot_arr()
        except Exception:
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

    def _check_text_present(self, keyword: str, center: tuple, spread: int) -> bool:
        try:
            arr = self._screenshot_arr()
        except Exception:
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
            if r[2] < 0.1:
                continue
            if keyword in r[1]:
                self.log(f"    [OCR检测] 找到'{keyword}': '{r[1]}' conf={r[2]:.2f} @({x},{y})")
                return True
            if any(ch in r[1] for ch in keyword):
                self.log(f"    [OCR检测] 字符重叠: 关键词'{keyword}' ∩ OCR'{r[1]}' conf={r[2]:.2f} @({x},{y})")
                return True
        return False

    # ── Boss / 去下一层 ────────────────────────

    def _go_next_floor(self, floor: int):
        """Boss已击杀，OCR循环清弹窗直到'跳转下一层'出现并点击，验证跳转成功后返回"""
        for attempt in range(3):
            self.log(f"  准备跳转第{floor + 1}层... (尝试{attempt + 1})")

            for _ in range(8):
                self._touch(CONFIRM_BTN, "确认清弹窗")
                time.sleep(1.0)
                if self._check_text_present("下一层", BOSS_NEXT_FLOOR, 200):
                    self._touch(BOSS_NEXT_FLOOR, "跳转下一层")
                    time.sleep(0.8)
                    self._touch(CONFIRM_BTN, "确认跳转")
                    time.sleep(3.0)
                    break
            else:
                self.log(f"  ⚠ 跳转超时，未检测到'下一层'弹窗")
                return

            # 验证是否真的到了新楼层
            if self._verify_floor(floor + 1):
                self.log(f"  已进入第{floor + 1}层 ✓")
                return
            self.log(f"  跳转未生效，仍在第{floor}层，重试...")

        self.log(f"  已进入第{floor + 1}层 (多次尝试后)")

    def _verify_floor(self, target_floor: int) -> bool:
        """快速扫描NPC列表，验证是否到达目标楼层"""
        target_names = FLOOR_MONSTERS.get(target_floor, [])
        old_names = FLOOR_MONSTERS.get(target_floor - 1, [])

        saved = self._known_names
        self._known_names = target_names + old_names
        try:
            self._open_npc_list()
            monsters = self._scan_npc_page()
        finally:
            self._known_names = saved

        for name, y in monsters:
            if TELEPORTER_KEY in name:
                continue
            if name in target_names:
                return True
            if name in old_names:
                return False

        return True  # 无法判断，假定成功
