"""寻秦OL 自动化助手 - 主程序"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from core.device import connect_mumu, get_device_info, MUMU_PORT
from tasks.walk_demo import WalkDemo
from tasks.flow_task import FlowTask


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("寻秦OL 自动化助手")
        self.root.geometry("700x620")
        self.root.resizable(True, True)

        self._connected = False
        self._current_task = None

        self._build_ui()
        self._update_status_timer()

    # ── UI 构建 ─────────────────────────────────────

    def _build_ui(self):
        # 顶部：设备连接栏
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(top, text="MuMu 地址:").pack(side=tk.LEFT)
        self._addr_var = tk.StringVar(value=MUMU_PORT)
        ttk.Combobox(top, textvariable=self._addr_var,
                     values=[MUMU_PORT, "127.0.0.1:16384"], width=18).pack(side=tk.LEFT, padx=4)

        self._connect_btn = ttk.Button(top, text="连接模拟器", command=self._on_connect)
        self._connect_btn.pack(side=tk.LEFT, padx=4)

        self._status_label = ttk.Label(top, text="未连接", foreground="gray")
        self._status_label.pack(side=tk.LEFT, padx=8)

        self._info_label = ttk.Label(top, text="")
        self._info_label.pack(side=tk.RIGHT)

        # 下方分栏：左侧标签页 + 右侧日志
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # 左侧：标签页
        notebook = ttk.Notebook(body)
        notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_walk_tab(notebook)
        self._build_quest_tab(notebook)
        self._build_dungeon_tab(notebook)
        self._build_pet_tab(notebook)

        # 右侧：日志
        right = ttk.Frame(body)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(4, 0))

        log_frame = ttk.LabelFrame(right, text="运行日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self._log_area = scrolledtext.ScrolledText(log_frame, width=40, height=26,
                                                   state=tk.DISABLED, wrap=tk.WORD)
        self._log_area.pack(fill=tk.BOTH, expand=True)

    # ── 走路 Demo 标签页 ────────────────────────────

    def _build_walk_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="走路测试")

        ttk.Label(tab, text="移动模式:", font=("", 9, "bold")).pack(anchor=tk.W)
        self._mode_var = tk.StringVar(value="tap")
        mode_f = ttk.Frame(tab)
        mode_f.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(mode_f, text="点击地面寻路", variable=self._mode_var,
                        value="tap").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(mode_f, text="摇杆拖动", variable=self._mode_var,
                        value="joystick").pack(side=tk.LEFT)

        ttk.Label(tab, text="方向:", font=("", 9, "bold")).pack(anchor=tk.W, pady=(8, 0))
        self._dir_var = tk.StringVar(value="right")
        dir_f = ttk.Frame(tab)
        dir_f.pack(fill=tk.X, pady=2)
        for d in ["上", "下", "左", "右"]:
            ttk.Radiobutton(dir_f, text=d, variable=self._dir_var,
                            value={"上": "up", "下": "down", "左": "left", "右": "right"}[d]
                            ).pack(side=tk.LEFT, padx=2)

        # 参数
        ttk.Label(tab, text="参数:", font=("", 9, "bold")).pack(anchor=tk.W, pady=(8, 0))
        cfg = ttk.Frame(tab)
        cfg.pack(fill=tk.X, pady=2)

        ttk.Label(cfg, text="步数").pack(side=tk.LEFT)
        self._steps_var = tk.IntVar(value=3)
        ttk.Spinbox(cfg, from_=1, to=50, textvariable=self._steps_var, width=4).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(cfg, text="点击X").pack(side=tk.LEFT)
        self._tap_x_var = tk.IntVar(value=540)
        ttk.Entry(cfg, textvariable=self._tap_x_var, width=5).pack(side=tk.LEFT, padx=2)

        ttk.Label(cfg, text="Y").pack(side=tk.LEFT)
        self._tap_y_var = tk.IntVar(value=800)
        ttk.Entry(cfg, textvariable=self._tap_y_var, width=5).pack(side=tk.LEFT, padx=2)

        ttk.Label(cfg, text="偏移").pack(side=tk.LEFT)
        self._spread_var = tk.IntVar(value=350)
        ttk.Entry(cfg, textvariable=self._spread_var, width=4).pack(side=tk.LEFT, padx=2)

        # 按钮
        btn = ttk.Frame(tab)
        btn.pack(fill=tk.X, pady=(12, 0))
        self._walk_start_btn = ttk.Button(btn, text="开始走路", command=self._on_start_walk)
        self._walk_start_btn.pack(side=tk.LEFT, padx=2)
        self._walk_stop_btn = ttk.Button(btn, text="停止", command=self._on_stop_walk,
                                         state=tk.DISABLED)
        self._walk_stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn, text="截一张图", command=self._on_screenshot).pack(side=tk.RIGHT)

    # ── 跑环任务标签页 ──────────────────────────────

    def _build_quest_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="跑环任务")

        ttk.Label(tab, text="任务流程 (按顺序):", font=("", 9, "bold")).pack(anchor=tk.W)

        help_text = (
            "需要先在 templates/quest/ 下放入模板图片：\n"
            "  ① accept.png  - 接受任务按钮\n"
            "  ② track.png   - 追踪/前往按钮\n"
            "  ③ npc.png     - NPC对话框\n"
            "  ④ done.png    - 完成/交任务按钮\n\n"
            "提示：截游戏里的按钮图放进去就行，\n"
            "     图片越清晰匹配越准。"
        )
        ttk.Label(tab, text=help_text, foreground="gray", justify=tk.LEFT).pack(anchor=tk.W, pady=4)

        self._quest_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="循环执行", variable=self._quest_loop_var).pack(anchor=tk.W)

        self._quest_interval_var = tk.IntVar(value=3)
        int_f = ttk.Frame(tab)
        int_f.pack(fill=tk.X, pady=4)
        ttk.Label(int_f, text="每步等待(秒):").pack(side=tk.LEFT)
        ttk.Spinbox(int_f, from_=1, to=10, textvariable=self._quest_interval_var, width=4).pack(side=tk.LEFT)

        btn = ttk.Frame(tab)
        btn.pack(fill=tk.X, pady=(12, 0))
        self._quest_start_btn = ttk.Button(btn, text="开始跑环", command=self._on_start_quest)
        self._quest_start_btn.pack(side=tk.LEFT, padx=2)
        self._quest_stop_btn = ttk.Button(btn, text="停止", command=self._on_stop_task,
                                          state=tk.DISABLED)
        self._quest_stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn, text="打开模板目录", command=lambda: os.startfile(
            os.path.join(BASE_DIR, "templates", "quest"))).pack(side=tk.RIGHT)

    # ── 副本标签页 ─────────────────────────────────

    def _build_dungeon_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="刷副本")

        ttk.Label(tab, text="副本流程 (按顺序):", font=("", 9, "bold")).pack(anchor=tk.W)

        help_text = (
            "需要先在 templates/dungeon/ 下放入：\n"
            "  ① enter.png   - 进入副本按钮\n"
            "  ② fight.png   - 战斗中(自动挂机)\n"
            "  ③ reward.png  - 结算/领取奖励\n"
            "  ④ exit.png    - 退出副本\n"
        )
        ttk.Label(tab, text=help_text, foreground="gray", justify=tk.LEFT).pack(anchor=tk.W, pady=4)

        self._dung_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="循环刷", variable=self._dung_loop_var).pack(anchor=tk.W)

        self._dung_interval_var = tk.IntVar(value=3)
        int_f = ttk.Frame(tab)
        int_f.pack(fill=tk.X, pady=4)
        ttk.Label(int_f, text="每步等待(秒):").pack(side=tk.LEFT)
        ttk.Spinbox(int_f, from_=1, to=10, textvariable=self._dung_interval_var, width=4).pack(side=tk.LEFT)

        btn = ttk.Frame(tab)
        btn.pack(fill=tk.X, pady=(12, 0))
        self._dung_start_btn = ttk.Button(btn, text="开始刷副本", command=self._on_start_dungeon)
        self._dung_start_btn.pack(side=tk.LEFT, padx=2)
        self._dung_stop_btn = ttk.Button(btn, text="停止", command=self._on_stop_task,
                                         state=tk.DISABLED)
        self._dung_stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn, text="打开模板目录", command=lambda: os.startfile(
            os.path.join(BASE_DIR, "templates", "dungeon"))).pack(side=tk.RIGHT)

    # ── 抓宠物标签页 ───────────────────────────────

    def _build_pet_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="抓宠物")

        ttk.Label(tab, text="抓宠流程 (按顺序):", font=("", 9, "bold")).pack(anchor=tk.W)

        help_text = (
            "需要先在 templates/pet/ 下放入：\n"
            "  ① find.png    - 找到宠物(识别宠物图案)\n"
            "  ② attack.png  - 攻击/进入战斗\n"
            "  ③ catch.png   - 捕捉按钮\n"
            "  ④ done.png    - 捕捉完成确认\n"
        )
        ttk.Label(tab, text=help_text, foreground="gray", justify=tk.LEFT).pack(anchor=tk.W, pady=4)

        self._pet_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="循环抓宠", variable=self._pet_loop_var).pack(anchor=tk.W)

        self._pet_interval_var = tk.IntVar(value=2)
        int_f = ttk.Frame(tab)
        int_f.pack(fill=tk.X, pady=4)
        ttk.Label(int_f, text="每步等待(秒):").pack(side=tk.LEFT)
        ttk.Spinbox(int_f, from_=1, to=10, textvariable=self._pet_interval_var, width=4).pack(side=tk.LEFT)

        btn = ttk.Frame(tab)
        btn.pack(fill=tk.X, pady=(12, 0))
        self._pet_start_btn = ttk.Button(btn, text="开始抓宠", command=self._on_start_pet)
        self._pet_start_btn.pack(side=tk.LEFT, padx=2)
        self._pet_stop_btn = ttk.Button(btn, text="停止", command=self._on_stop_task,
                                        state=tk.DISABLED)
        self._pet_stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn, text="打开模板目录", command=lambda: os.startfile(
            os.path.join(BASE_DIR, "templates", "pet"))).pack(side=tk.RIGHT)

    # ── 设备连接 ──────────────────────────────────

    def _on_connect(self):
        addr = self._addr_var.get()
        self._log(f"正在连接 {addr} ...")
        self._connect_btn.config(state=tk.DISABLED)

        def _connect():
            ok = connect_mumu(addr)
            self.root.after(0, lambda: self._on_connect_done(ok))

        threading.Thread(target=_connect, daemon=True).start()

    def _on_connect_done(self, ok: bool):
        self._connect_btn.config(state=tk.NORMAL)
        self._connected = ok
        if ok:
            self._status_label.config(text="已连接", foreground="green")
            info = get_device_info()
            w, h = info["width"], info["height"]
            self._info_label.config(text=f"{w}x{h}")
            self._log(f"连接成功 ({w}x{h})")
        else:
            self._status_label.config(text="连接失败", foreground="red")
            self._log("连接失败")

    def _update_status_timer(self):
        try:
            info = get_device_info()
            self._connected = info["connected"]
        except Exception:
            self._connected = False
        self.root.after(5000, self._update_status_timer)

    # ── 走路 ─────────────────────────────────────

    def _on_start_walk(self):
        if not self._check_connected():
            return
        self._current_task = WalkDemo(
            direction=self._dir_var.get(),
            steps=self._steps_var.get(),
            use_joystick=self._mode_var.get() == "joystick",
            tap_x=self._tap_x_var.get(), tap_y=self._tap_y_var.get(),
            spread=self._spread_var.get())
        self._current_task.set_log_callback(lambda m: self.root.after(0, self._log, m))
        self._current_task.start()
        self._walk_start_btn.config(state=tk.DISABLED)
        self._walk_stop_btn.config(state=tk.NORMAL)

    # ── 跑环 ─────────────────────────────────────

    def _on_start_quest(self):
        if not self._check_connected():
            return
        interval = self._quest_interval_var.get()
        steps = [
            {"template": "templates/quest/accept.png", "wait": interval, "desc": "点接受任务"},
            {"template": "templates/quest/track.png",  "wait": interval, "desc": "点追踪"},
            {"template": "templates/quest/npc.png",    "wait": interval, "desc": "对话NPC"},
            {"template": "templates/quest/done.png",   "wait": interval, "desc": "交任务"},
        ]
        self._current_task = FlowTask("跑环任务", steps, loop=self._quest_loop_var.get())
        self._current_task.set_log_callback(lambda m: self.root.after(0, self._log, m))
        self._current_task.start()
        self._quest_start_btn.config(state=tk.DISABLED)
        self._quest_stop_btn.config(state=tk.NORMAL)

    # ── 副本 ─────────────────────────────────────

    def _on_start_dungeon(self):
        if not self._check_connected():
            return
        interval = self._dung_interval_var.get()
        steps = [
            {"template": "templates/dungeon/enter.png",  "wait": interval, "desc": "进入副本"},
            {"template": "templates/dungeon/fight.png",  "wait": 10,       "desc": "战斗中(等10秒)"},
            {"template": "templates/dungeon/reward.png", "wait": interval, "desc": "领奖励"},
            {"template": "templates/dungeon/exit.png",   "wait": interval, "desc": "退出"},
        ]
        self._current_task = FlowTask("刷副本", steps, loop=self._dung_loop_var.get())
        self._current_task.set_log_callback(lambda m: self.root.after(0, self._log, m))
        self._current_task.start()
        self._dung_start_btn.config(state=tk.DISABLED)
        self._dung_stop_btn.config(state=tk.NORMAL)

    # ── 抓宠 ─────────────────────────────────────

    def _on_start_pet(self):
        if not self._check_connected():
            return
        interval = self._pet_interval_var.get()
        steps = [
            {"template": "templates/pet/find.png",   "wait": interval, "desc": "找宠物"},
            {"template": "templates/pet/attack.png", "wait": interval, "desc": "进入战斗"},
            {"template": "templates/pet/catch.png",  "wait": interval, "desc": "捕捉"},
            {"template": "templates/pet/done.png",   "wait": interval, "desc": "确认"},
        ]
        self._current_task = FlowTask("抓宠物", steps, loop=self._pet_loop_var.get())
        self._current_task.set_log_callback(lambda m: self.root.after(0, self._log, m))
        self._current_task.start()
        self._pet_start_btn.config(state=tk.DISABLED)
        self._pet_stop_btn.config(state=tk.NORMAL)

    # ── 通用停止 ─────────────────────────────────

    def _on_stop_walk(self):
        self._on_stop_task()
        self._walk_start_btn.config(state=tk.NORMAL)
        self._walk_stop_btn.config(state=tk.DISABLED)

    def _on_stop_task(self):
        if self._current_task:
            self._current_task.stop()
        # 恢复所有按钮
        for b in [self._walk_start_btn, self._quest_start_btn,
                  self._dung_start_btn, self._pet_start_btn]:
            try: b.config(state=tk.NORMAL)
            except: pass
        for b in [self._walk_stop_btn, self._quest_stop_btn,
                  self._dung_stop_btn, self._pet_stop_btn]:
            try: b.config(state=tk.DISABLED)
            except: pass

    # ── 工具 ─────────────────────────────────────

    def _check_connected(self) -> bool:
        if not self._connected:
            self._log("错误: 请先点击顶部「连接模拟器」!")
            return False
        return True

    def _on_screenshot(self):
        if not self._check_connected():
            return
        from core.actions import screenshot
        import time
        name = f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(BASE_DIR, "logs", name)
        screenshot(path)
        self._log(f"截图: {path}")

    def _log(self, msg: str):
        self._log_area.config(state=tk.NORMAL)
        self._log_area.insert(tk.END, msg + "\n")
        self._log_area.see(tk.END)
        self._log_area.config(state=tk.DISABLED)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
