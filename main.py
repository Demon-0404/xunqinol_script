"""寻秦OL 自动化助手 - 主程序（多设备版）"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from core.device import (
    connect_device_by_serial, switch_device, get_device_info,
    init_all_devices, list_devices, scan_available_devices,
)
from tasks.walk_demo import WalkDemo
from tasks.flow_task import FlowTask


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("寻秦OL 自动化助手")
        self.root.geometry("720x640")
        self.root.resizable(True, True)

        self._current_task = None
        self._device_names = []  # 已连接的设备名列表

        self._build_ui()
        self._auto_init()

    # ── UI 构建 ─────────────────────────────────────

    def _build_ui(self):
        # 顶部：设备管理栏
        top = ttk.LabelFrame(self.root, text="设备管理", padding=6)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        # 第一行：设备选择 + 连接
        row1 = ttk.Frame(top)
        row1.pack(fill=tk.X)

        ttk.Label(row1, text="当前设备:").pack(side=tk.LEFT)
        self._device_var = tk.StringVar(value="")
        self._device_combo = ttk.Combobox(row1, textvariable=self._device_var,
                                          values=[], width=14, state="readonly")
        self._device_combo.pack(side=tk.LEFT, padx=4)
        self._device_combo.bind("<<ComboboxSelected>>", self._on_switch_device)

        ttk.Button(row1, text="刷新设备", command=self._on_refresh_devices).pack(side=tk.LEFT, padx=4)

        ttk.Label(row1, text="  ADB地址:").pack(side=tk.LEFT)
        self._addr_var = tk.StringVar(value="127.0.0.1:7555")
        ttk.Combobox(row1, textvariable=self._addr_var,
                     values=["127.0.0.1:7555", "127.0.0.1:7557",
                             "127.0.0.1:16384", "127.0.0.1:16386"], width=16).pack(side=tk.LEFT, padx=2)

        ttk.Label(row1, text="名称:").pack(side=tk.LEFT)
        self._dev_name_var = tk.StringVar(value="设备1")
        ttk.Entry(row1, textvariable=self._dev_name_var, width=8).pack(side=tk.LEFT, padx=2)

        self._connect_btn = ttk.Button(row1, text="添加设备", command=self._on_add_device)
        self._connect_btn.pack(side=tk.LEFT, padx=4)

        # 第二行：设备信息
        row2 = ttk.Frame(top)
        row2.pack(fill=tk.X, pady=(4, 0))
        self._status_label = ttk.Label(row2, text="未连接任何设备", foreground="gray")
        self._status_label.pack(side=tk.LEFT)
        self._info_label = ttk.Label(row2, text="")
        self._info_label.pack(side=tk.RIGHT)

        # 主体：标签页 + 日志
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

    # ── 走路测试页 ─────────────────────────────────

    def _build_walk_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="走路测试")

        ttk.Label(tab, text="移动模式:", font=("", 9, "bold")).pack(anchor=tk.W)
        self._mode_var = tk.StringVar(value="tap")
        mf = ttk.Frame(tab)
        mf.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(mf, text="点击地面寻路", variable=self._mode_var, value="tap").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(mf, text="摇杆拖动", variable=self._mode_var, value="joystick").pack(side=tk.LEFT)

        ttk.Label(tab, text="方向:", font=("", 9, "bold")).pack(anchor=tk.W, pady=(8, 0))
        self._dir_var = tk.StringVar(value="right")
        df = ttk.Frame(tab)
        df.pack(fill=tk.X, pady=2)
        for d in ["上", "下", "左", "右"]:
            ttk.Radiobutton(df, text=d, variable=self._dir_var,
                            value={"上":"up","下":"down","左":"left","右":"right"}[d]).pack(side=tk.LEFT, padx=2)

        ttk.Label(tab, text="参数:", font=("", 9, "bold")).pack(anchor=tk.W, pady=(8, 0))
        cf = ttk.Frame(tab)
        cf.pack(fill=tk.X, pady=2)

        ttk.Label(cf, text="步数").pack(side=tk.LEFT)
        self._steps_var = tk.IntVar(value=3)
        ttk.Spinbox(cf, from_=1, to=50, textvariable=self._steps_var, width=4).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(cf, text="X").pack(side=tk.LEFT)
        self._tap_x_var = tk.IntVar(value=540)
        ttk.Entry(cf, textvariable=self._tap_x_var, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(cf, text="Y").pack(side=tk.LEFT)
        self._tap_y_var = tk.IntVar(value=800)
        ttk.Entry(cf, textvariable=self._tap_y_var, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(cf, text="偏移").pack(side=tk.LEFT)
        self._spread_var = tk.IntVar(value=350)
        ttk.Entry(cf, textvariable=self._spread_var, width=4).pack(side=tk.LEFT, padx=2)

        bf = ttk.Frame(tab)
        bf.pack(fill=tk.X, pady=(12, 0))
        self._walk_start_btn = ttk.Button(bf, text="开始走路", command=self._on_start_walk)
        self._walk_start_btn.pack(side=tk.LEFT, padx=2)
        self._walk_stop_btn = ttk.Button(bf, text="停止", command=self._on_stop_task, state=tk.DISABLED)
        self._walk_stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="截一张图", command=self._on_screenshot).pack(side=tk.RIGHT, padx=2)

    # ── 跑环页 ─────────────────────────────────────

    def _build_quest_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="跑环任务")

        help_text = (
            "在 templates/quest/ 放入模板图：\n"
            "  accept.png / track.png / npc.png / done.png\n"
            "脚本按顺序找图→点击→等待→下一张。"
        )
        ttk.Label(tab, text=help_text, foreground="gray", justify=tk.LEFT).pack(anchor=tk.W, pady=4)

        self._quest_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="循环执行", variable=self._quest_loop_var).pack(anchor=tk.W, pady=2)

        ttk.Label(tab, text="每步等待(秒):").pack(anchor=tk.W)
        self._quest_interval_var = tk.IntVar(value=3)
        ttk.Spinbox(tab, from_=1, to=10, textvariable=self._quest_interval_var, width=4).pack(anchor=tk.W, pady=2)

        bf = ttk.Frame(tab)
        bf.pack(fill=tk.X, pady=(12, 0))
        self._quest_start_btn = ttk.Button(bf, text="开始跑环", command=self._on_start_quest)
        self._quest_start_btn.pack(side=tk.LEFT, padx=2)
        self._quest_stop_btn = ttk.Button(bf, text="停止", command=self._on_stop_task, state=tk.DISABLED)
        self._quest_stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="打开模板目录",
                   command=lambda: os.startfile(os.path.join(BASE_DIR, "templates", "quest"))
                   ).pack(side=tk.RIGHT)

    # ── 副本页 ─────────────────────────────────────

    def _build_dungeon_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="刷副本")

        help_text = (
            "在 templates/dungeon/ 放入模板图：\n"
            "  enter.png / fight.png / reward.png / exit.png"
        )
        ttk.Label(tab, text=help_text, foreground="gray", justify=tk.LEFT).pack(anchor=tk.W, pady=4)

        self._dung_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="循环刷", variable=self._dung_loop_var).pack(anchor=tk.W, pady=2)

        ttk.Label(tab, text="每步等待(秒):").pack(anchor=tk.W)
        self._dung_interval_var = tk.IntVar(value=3)
        ttk.Spinbox(tab, from_=1, to=10, textvariable=self._dung_interval_var, width=4).pack(anchor=tk.W, pady=2)

        bf = ttk.Frame(tab)
        bf.pack(fill=tk.X, pady=(12, 0))
        self._dung_start_btn = ttk.Button(bf, text="开始刷副本", command=self._on_start_dungeon)
        self._dung_start_btn.pack(side=tk.LEFT, padx=2)
        self._dung_stop_btn = ttk.Button(bf, text="停止", command=self._on_stop_task, state=tk.DISABLED)
        self._dung_stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="打开模板目录",
                   command=lambda: os.startfile(os.path.join(BASE_DIR, "templates", "dungeon"))
                   ).pack(side=tk.RIGHT)

    # ── 抓宠页 ─────────────────────────────────────

    def _build_pet_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="抓宠物")

        help_text = (
            "在 templates/pet/ 放入模板图：\n"
            "  find.png / attack.png / catch.png / done.png"
        )
        ttk.Label(tab, text=help_text, foreground="gray", justify=tk.LEFT).pack(anchor=tk.W, pady=4)

        self._pet_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="循环抓宠", variable=self._pet_loop_var).pack(anchor=tk.W, pady=2)

        ttk.Label(tab, text="每步等待(秒):").pack(anchor=tk.W)
        self._pet_interval_var = tk.IntVar(value=2)
        ttk.Spinbox(tab, from_=1, to=10, textvariable=self._pet_interval_var, width=4).pack(anchor=tk.W, pady=2)

        bf = ttk.Frame(tab)
        bf.pack(fill=tk.X, pady=(12, 0))
        self._pet_start_btn = ttk.Button(bf, text="开始抓宠", command=self._on_start_pet)
        self._pet_start_btn.pack(side=tk.LEFT, padx=2)
        self._pet_stop_btn = ttk.Button(bf, text="停止", command=self._on_stop_task, state=tk.DISABLED)
        self._pet_stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="打开模板目录",
                   command=lambda: os.startfile(os.path.join(BASE_DIR, "templates", "pet"))
                   ).pack(side=tk.RIGHT)

    # ── 设备管理 ──────────────────────────────────

    def _auto_init(self):
        """启动时自动扫描 MuMu 实例并连接"""
        self._log("正在扫描 MuMu 实例...")
        devices = init_all_devices()
        names = [d["name"] for d in devices]
        self._log(f"发现 {len(devices)} 个实例: {', '.join(names)}")
        self._refresh_device_list()

    def _on_refresh_devices(self):
        """手动刷新设备列表"""
        self._log("正在重新扫描...")
        devices = scan_available_devices()
        # 重新连接
        for d in devices:
            if not d["connected"]:
                import subprocess
                subprocess.run([os.environ.get("ANDROID_ADB", "adb"), "connect", d["serial"]],
                             capture_output=True, timeout=5)
            connect_device_by_serial(d["name"], d["serial"])
        self._refresh_device_list()
        names = [d["name"] for d in devices]
        self._log(f"共 {len(devices)} 个实例: {', '.join(names)}")

    def _on_add_device(self):
        """添加新设备"""
        addr = self._addr_var.get()
        name = self._dev_name_var.get()
        if not name.strip():
            name = addr

        self._log(f"正在连接 {name} ({addr}) ...")
        self._connect_btn.config(state=tk.DISABLED)

        def _do():
            ok = connect_device_by_serial(name, addr)
            self.root.after(0, lambda: self._on_add_done(name, ok))

        threading.Thread(target=_do, daemon=True).start()

    def _on_add_done(self, name: str, ok: bool):
        self._connect_btn.config(state=tk.NORMAL)
        self._refresh_device_list()
        if ok:
            self._device_var.set(name)
            self._on_switch_device()
            self._log(f"{name} 添加成功")

            # 自动切到这个设备
            switch_device(name)
            info = get_device_info(name)
            self._info_label.config(text=f"{info['width']}x{info['height']}")
        else:
            self._log(f"{name} 连接失败, 请检查地址是否正确")

    def _on_switch_device(self, event=None):
        """设备下拉切换"""
        name = self._device_var.get()
        if not name:
            return
        if switch_device(name):
            info = get_device_info(name)
            self._status_label.config(text=f"当前: {name}", foreground="green")
            self._info_label.config(text=f"{info['width']}x{info['height']}")
            self._log(f"已切换到: {name}")
        else:
            self._status_label.config(text=f"{name} 连接异常", foreground="red")

    def _refresh_device_list(self):
        """刷新设备下拉列表"""
        devs = list_devices()
        self._device_names = list(devs.keys())
        self._device_combo["values"] = self._device_names
        if self._device_names:
            if not self._device_var.get() or self._device_var.get() not in self._device_names:
                self._device_var.set(self._device_names[0])
            self._on_switch_device()
        else:
            self._device_var.set("")
            self._status_label.config(text="未连接任何设备", foreground="gray")
            self._info_label.config(text="")

    # ── 当前选中设备名 ─────────────────────────────

    def _selected_device(self) -> str:
        """返回当前 UI 中选中的设备名"""
        return self._device_var.get()

    # ── 走路 ─────────────────────────────────────

    def _on_start_walk(self):
        dev = self._selected_device()
        if not dev:
            self._log("错误: 请先添加设备!")
            return
        switch_device(dev)

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
        dev = self._selected_device()
        if not dev:
            self._log("错误: 请先添加设备!")
            return
        switch_device(dev)
        interval = self._quest_interval_var.get()
        steps = [
            {"template": "templates/quest/accept.png", "wait": interval, "desc": "接受任务"},
            {"template": "templates/quest/track.png",  "wait": interval, "desc": "追踪"},
            {"template": "templates/quest/npc.png",    "wait": interval, "desc": "对话NPC"},
            {"template": "templates/quest/done.png",   "wait": interval, "desc": "交任务"},
        ]
        self._current_task = FlowTask("跑环", steps, loop=self._quest_loop_var.get())
        self._current_task.set_log_callback(lambda m: self.root.after(0, self._log, m))
        self._current_task.start()
        self._quest_start_btn.config(state=tk.DISABLED)
        self._quest_stop_btn.config(state=tk.NORMAL)

    # ── 副本 ─────────────────────────────────────

    def _on_start_dungeon(self):
        dev = self._selected_device()
        if not dev:
            self._log("错误: 请先添加设备!")
            return
        switch_device(dev)
        interval = self._dung_interval_var.get()
        steps = [
            {"template": "templates/dungeon/enter.png",  "wait": interval, "desc": "进入副本"},
            {"template": "templates/dungeon/fight.png",  "wait": 10,       "desc": "战斗中"},
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
        dev = self._selected_device()
        if not dev:
            self._log("错误: 请先添加设备!")
            return
        switch_device(dev)
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

    # ── 通用 ─────────────────────────────────────

    def _on_stop_task(self):
        if self._current_task:
            self._current_task.stop()
        for b in [self._walk_start_btn, self._quest_start_btn,
                  self._dung_start_btn, self._pet_start_btn]:
            try: b.config(state=tk.NORMAL)
            except: pass
        for b in [self._walk_stop_btn, self._quest_stop_btn,
                  self._dung_stop_btn, self._pet_stop_btn]:
            try: b.config(state=tk.DISABLED)
            except: pass

    def _on_screenshot(self):
        dev = self._selected_device()
        if not dev:
            self._log("错误: 请先添加设备!")
            return
        switch_device(dev)
        from core.actions import screenshot
        import time
        name = f"screenshot_{dev}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(BASE_DIR, "logs", name)
        screenshot(path)
        self._log(f"截图({dev}): {path}")

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
