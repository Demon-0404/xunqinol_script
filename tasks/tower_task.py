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
NEARBY_BTN = (500, 1200)       # 周围列表按钮
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
SETTLE_CHECK = (800, 950)      # "按5键继续"区域(结算弹窗)
SETTLE_RANGE = 200             # 检测范围±200px
CONFIRM_BTN = (150, 1600)      # 确认键(数字5)

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
    4: ["乱心尘", "阴阳二气瓶", "劈地珠", "杏黄旗", "刃", "穿心锁",
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

    def __init__(self):
        super().__init__("玄兵塔")
        self._reader = None
        self._cleared = 0
        self._known_names = []
        self._click_seq = 0

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
        while self._running:
            self._open_npc_list()
            result = self._scan_and_kill(floor)

            if result == "boss":
                self.log("  本层Boss已击杀")
                break

            if not result:
                self.log("  当前页无怪物，翻页...")
                self._touch(NEXT_PAGE, "翻页")
                time.sleep(0.5)
                result2 = self._scan_and_kill(floor)
                if result2 == "boss":
                    self.log("  本层Boss已击杀")
                    break
                if not result2:
                    self.log("  本层怪物已清完")
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

        boss_names = [f[-1] for f in FLOOR_MONSTERS.values()]
        is_boss = _fuzzy_match(name, boss_names) is not None
        self._engage_monster(name, y, is_boss=is_boss)
        self._cleared += 1
        return "boss" if is_boss else True

    # ── NPC列表 ────────────────────────────────

    def _open_npc_list(self):
        self.log("  打开周围列表...")
        self._touch(NEARBY_BTN, "周围列表")
        time.sleep(0.8)
        self._touch(NPC_TAB, "NPC标签")
        time.sleep(0.6)

    def _screenshot_arr(self) -> np.ndarray:
        import subprocess
        try:
            filename = snapshot()
            if filename is None:
                raise RuntimeError("snapshot returned None")
            return np.array(Image.open(filename))[:, :, :3]
        except Exception:
            adb = os.environ.get("ANDROID_ADB", "adb")
            tmp = os.path.join(LOG_DIR, "_tower_tmp.png")
            subprocess.run([adb, "shell", "screencap", "-p", "/sdcard/sc.png"],
                           capture_output=True, timeout=5)
            subprocess.run([adb, "pull", "/sdcard/sc.png", tmp],
                           capture_output=True, timeout=5)
            return np.array(Image.open(tmp))[:, :, :3]

    def _scan_npc_page(self) -> list:
        try:
            arr = self._screenshot_arr()
        except Exception as e:
            self.log(f"  截图失败: {e}")
            return []

        reader = self._get_reader()
        monsters = []

        for i in range(ROW_COUNT):
            yc = ROW_Y_START + i * ROW_SPACING
            row = arr[yc - 45:yc + 45, 0:540, :]
            gray = np.mean(row, axis=2)
            if (gray < 80).mean() < 0.02:
                continue
            try:
                results = reader.readtext(row)
            except Exception:
                continue
            if not results:
                continue
            text = results[0][1]
            conf = results[0][2]
            if conf < 0.1:
                continue
            matched = _fuzzy_match(text, self._known_names)
            if not matched:
                self.log(f"    OCR Y={yc}: {text} ({conf:.2f}) ✗ 未匹配")
                continue
            self.log(f"    OCR Y={yc}: {text} ({conf:.2f}) → {matched}")
            monsters.append((matched, yc))

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

        # 等待进入战斗
        time.sleep(1.5)
        if self._check_text_present("回合", ROUND_CHECK, ROUND_RANGE):
            self.log("    进入战斗!")
            self.log(f"    战斗中...")
            self._wait_for_round_disappear()

        # 跳过结算弹窗
        self._skip_settlement()

    def _wait_for_round_disappear(self, timeout: float = 120.0):
        start = time.time()
        while time.time() - start < timeout and self._running:
            if not self._check_text_present("回合", ROUND_CHECK, ROUND_RANGE):
                self.log("    战斗结束!")
                return True
            time.sleep(BATTLE_CHECK_INTERVAL)
        return False

    def _skip_settlement(self, max_rounds: int = 10):
        """结算弹窗：检测'按5键继续'或'战斗胜利'→确认→直到消失"""
        for _ in range(max_rounds):
            if not self._running:
                return
            has_settle = self._check_text_present("按5键继续", SETTLE_CHECK, SETTLE_RANGE)
            has_victory = self._check_text_present("战斗胜利", (500, 500), 200)
            if has_settle or has_victory:
                self.log("    跳过结算...")
                self._touch(CONFIRM_BTN, "确认结算")
                time.sleep(SETTLE_CHECK_INTERVAL)
            else:
                time.sleep(0.3)
                has2 = self._check_text_present("按5键继续", SETTLE_CHECK, SETTLE_RANGE)
                has3 = self._check_text_present("战斗胜利", (500, 500), 200)
                if not has2 and not has3:
                    return
        self.log("    结算完成")

    def _check_text_present(self, keyword: str, center: tuple, spread: int) -> bool:
        try:
            arr = self._screenshot_arr()
        except Exception:
            return False
        x, y = center
        crop = arr[y - spread:y + spread, x - spread:x + spread, :]
        reader = self._get_reader()
        try:
            results = reader.readtext(crop)
        except Exception:
            return False
        for r in results:
            if keyword in r[1] or any(ch in r[1] for ch in keyword):
                return True
        return False

    # ── Boss / 去下一层 ────────────────────────

    def _go_next_floor(self, floor: int):
        """Boss已击杀，OCR循环清弹窗直到'跳转下一层'出现并点击"""
        self.log(f"  准备跳转第{floor + 1}层...")

        for _ in range(8):
            self._touch(CONFIRM_BTN, "确认清弹窗")
            time.sleep(1.0)
            if self._check_text_present("下一层", BOSS_NEXT_FLOOR, 200):
                self._touch(BOSS_NEXT_FLOOR, "跳转下一层")
                time.sleep(0.8)
                self._touch(CONFIRM_BTN, "确认跳转")
                time.sleep(3.0)
                self.log(f"  已进入第{floor + 1}层")
                return

        self.log(f"  ⚠ 跳转超时，未检测到'下一层'弹窗")
