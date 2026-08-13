"""寻秦OL 自动化助手 - 主程序（多设备版）"""
import sys
import os
import io
import subprocess
import json
# 修复 Airtest 内部 subprocess GBK 编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from core.device import (
    connect_device_by_serial, switch_device, get_device_info,
    list_devices, scan_available_devices,
)
from frida_blood.monitor import BloodMonitor


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("寻秦OL 自动化助手")
        self.root.geometry("860x700")
        self.root.resizable(True, True)

        self._workers = {}  # device_name -> {"proc": Popen, "tab_key": str}
        self._device_check_vars = {}  # name -> IntVar (checkbox)
        self._device_connected = {}  # name -> bool
        self._device_serial = {}  # name -> serial
        self._device_status_labels = {}  # name -> ttk.Label (连接状态)
        self._tab_device_frames = {}  # tab_key -> Frame (设备行容器)
        self._tab_row_widgets = {}    # tab_key -> dict[name -> {start,stop,status}]
        self._tab_handlers = {}       # tab_key -> callable(dev)
        self._tab_devices = {}        # tab_key -> list[device_name] (当前运行)
        self._blood_monitors = {}  # name -> BloodMonitor
        self._blood_widgets = {}  # name -> (frame, status_label, btn)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self._auto_init()

    # ── UI 构建 ─────────────────────────────────────

    def _build_ui(self):
        # 顶部：多设备管理栏
        top = ttk.LabelFrame(self.root, text="设备管理", padding=6)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        self._device_frame = ttk.Frame(top)
        self._device_frame.pack(fill=tk.X)

        btn_row = ttk.Frame(top)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_row, text="全选", command=self._on_select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="全不选", command=self._on_deselect_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="一键连接选中", command=self._on_connect_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="刷新", command=self._on_refresh_devices).pack(side=tk.LEFT, padx=2)
        self._global_status_label = ttk.Label(btn_row, text="", foreground="gray")
        self._global_status_label.pack(side=tk.LEFT, padx=8)

        # 主体：标签页 + 日志
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # 左侧：标签页
        notebook = ttk.Notebook(body)
        notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_walk_tab(notebook)
        self._build_quest_tab(notebook)
        self._build_dungeon_tab(notebook)
        self._build_dungeon100_tab(notebook)
        self._build_crystal_tab(notebook)
        self._build_pet_tab(notebook)
        self._build_tower_tab(notebook)
        self._build_chumo_tab(notebook)
        self._build_smith_tab(notebook)
        self._build_monkey_tab(notebook)
        self._build_blood_tab(notebook)

        # 右侧：日志
        right = ttk.Frame(body)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(4, 0))

        log_frame = ttk.LabelFrame(right, text="运行日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self._log_area = scrolledtext.ScrolledText(log_frame, width=40, height=26,
                                                   state=tk.DISABLED, wrap=tk.WORD)
        self._log_area.pack(fill=tk.BOTH, expand=True)

    # ── 设备选择辅助 ─────────────────────────────

    def _build_device_select(self, tab, tab_key: str, on_start):
        """每个已连接设备一行，独立开始/停止按钮，返回外层 frame"""
        self._tab_handlers[tab_key] = on_start
        outer = ttk.Frame(tab)
        outer.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(outer, text="运行设备:").pack(side=tk.LEFT, anchor=tk.N)
        rows = ttk.Frame(outer)
        rows.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._tab_device_frames[tab_key] = rows
        return outer

    def _update_tab_device_rows(self):
        """为每台已连接设备创建一行控制按钮（开始/停止/状态）"""
        connected = [n for n, c in self._device_connected.items() if c]
        for tab_key, rows_frame in self._tab_device_frames.items():
            for w in rows_frame.winfo_children():
                w.destroy()
            widgets_map = self._tab_row_widgets.setdefault(tab_key, {})
            widgets_map.clear()
            if not connected:
                ttk.Label(rows_frame, text="(无已连接设备)", foreground="gray").pack(anchor=tk.W)
                continue
            for name in connected:
                row = ttk.Frame(rows_frame)
                row.pack(fill=tk.X, pady=1)
                ttk.Label(row, text=name, width=12, anchor=tk.W).pack(side=tk.LEFT)
                running = name in self._workers
                start_btn = ttk.Button(row, text="开始", width=6,
                                       command=lambda n=name, tk=tab_key: self._start_dev(tk, n))
                start_btn.pack(side=tk.LEFT, padx=2)
                start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
                stop_btn = ttk.Button(row, text="停止", width=6,
                                      command=lambda n=name, tk=tab_key: self._stop_dev(tk, n))
                stop_btn.pack(side=tk.LEFT, padx=2)
                stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
                status_var = tk.StringVar(value="运行中" if running else "就绪")
                ttk.Label(row, textvariable=status_var,
                          foreground="blue" if running else "gray").pack(side=tk.LEFT, padx=8)
                widgets_map[name] = {"start": start_btn, "stop": stop_btn, "status": status_var}

    def _start_dev(self, tab_key: str, dev: str):
        handler = self._tab_handlers.get(tab_key)
        if handler:
            handler(dev)

    def _stop_dev(self, tab_key: str, dev: str):
        w = self._workers.get(dev)
        if w:
            try:
                w["proc"].stdin.write("STOP\n")
                w["proc"].stdin.flush()
            except Exception:
                pass
            # 兜底：宽限期后仍未退出则强制杀进程
            def _force_kill(d=dev, proc=w["proc"]):
                time.sleep(6)
                if d in self._workers and proc.poll() is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            threading.Thread(target=_force_kill, daemon=True).start()
        widgets = self._tab_row_widgets.get(tab_key, {}).get(dev)
        if widgets:
            widgets["stop"].config(state=tk.DISABLED)
            widgets["status"].set("停止中")

    def _kill_ocr_service(self):
        """按 pidfile 结束共享 OCR 服务进程"""
        try:
            pid_file = os.path.join(BASE_DIR, "logs", "ocr_service.pid")
            if os.path.exists(pid_file):
                with open(pid_file, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip())
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=10)
                os.remove(pid_file)
        except Exception:
            pass

    def _on_close(self):
        """关闭 UI 时终止所有 worker 子进程和 OCR 服务，避免后台残留"""
        for dev, w in list(self._workers.items()):
            try:
                w["proc"].kill()
            except Exception:
                pass
        self._workers.clear()
        self._kill_ocr_service()
        self.root.destroy()

    def _update_dev_row(self, tab_key: str, dev: str):
        w = self._tab_row_widgets.get(tab_key, {}).get(dev)
        if not w:
            return
        running = dev in self._workers
        w["start"].config(state=tk.DISABLED if running else tk.NORMAL)
        w["stop"].config(state=tk.NORMAL if running else tk.DISABLED)
        w["status"].set("运行中" if running else "就绪")

    def _on_worker_exit(self, dev: str, tab_key: str):
        if dev in self._workers:
            del self._workers[dev]
        if tab_key in self._tab_devices and dev in self._tab_devices[tab_key]:
            self._tab_devices[tab_key].remove(dev)
        self._update_dev_row(tab_key, dev)

    # ── 设备管理区填充 ───────────────────────────

    def _populate_device_checkboxes(self):
        """根据扫描结果填充设备 checkbox 行"""
        for w in self._device_frame.winfo_children():
            w.destroy()
        self._device_check_vars.clear()
        self._device_status_labels.clear()

        devices = getattr(self, '_available_devices', [])
        if not devices:
            ttk.Label(self._device_frame, text="未发现设备，请点击[刷新]",
                      foreground="gray").pack(anchor=tk.W, pady=4)
            return

        for d in devices:
            name = d["name"]
            serial = d.get("serial", "")
            connected = d.get("connected", False)

            self._device_serial[name] = serial
            self._device_connected[name] = connected

            var = tk.IntVar(value=1 if connected else 0)
            self._device_check_vars[name] = var

            row = ttk.Frame(self._device_frame)
            row.pack(side=tk.LEFT, padx=(2, 16), pady=2)
            cb = ttk.Checkbutton(row, text=name, variable=var)
            cb.pack(side=tk.LEFT)
            status_text = "已连接" if connected else "未连接"
            color = "green" if connected else "gray"
            lbl = ttk.Label(row, text=f"[{status_text}]", foreground=color)
            lbl.pack(side=tk.LEFT)
            self._device_status_labels[name] = lbl

        self._update_tab_device_rows()

    def _refresh_device_status_labels(self):
        """仅更新连接状态标签，不重建 UI"""
        for name, connected in self._device_connected.items():
            if name in self._device_status_labels:
                lbl = self._device_status_labels[name]
                status_text = "已连接" if connected else "未连接"
                color = "green" if connected else "gray"
                lbl.config(text=f"[{status_text}]", foreground=color)
        self._update_tab_device_rows()

    # ── 设备管理方法 ────────────────────────────

    def _auto_init(self):
        """启动时自动扫描并填充设备列表"""
        self._log("正在扫描 MuMu 实例...")
        self._available_devices = scan_available_devices()
        self._populate_device_checkboxes()
        names = [d["name"] for d in self._available_devices]
        self._log(f"发现 {len(names)} 个实例: {', '.join(names)}")
        self._on_refresh_blood()

    def _on_refresh_devices(self):
        """手动刷新设备列表"""
        self._log("正在重新扫描...")
        self._available_devices = scan_available_devices()
        # 更新连接状态
        for d in self._available_devices:
            name = d["name"]
            self._device_serial[name] = d.get("serial", "")
            if name not in self._device_connected:
                self._device_connected[name] = d.get("connected", False)
        self._populate_device_checkboxes()
        names = [d["name"] for d in self._available_devices]
        self._log(f"共 {len(names)} 个实例: {', '.join(names)}")

    def _on_select_all(self):
        for var in self._device_check_vars.values():
            var.set(1)

    def _on_deselect_all(self):
        for var in self._device_check_vars.values():
            var.set(0)

    def _on_connect_selected(self):
        """连接所有勾选的设备"""
        selected = [n for n, v in self._device_check_vars.items() if v.get()]
        if not selected:
            self._log("请先勾选要连接的设备")
            return

        self._global_status_label.config(text="连接中...", foreground="orange")

        def _do():
            for name in selected:
                serial = self._device_serial.get(name, "")
                if not serial:
                    continue
                self.root.after(0, lambda n=name: self._log(f"正在连接 {n} ..."))
                ok, err = connect_device_by_serial(name, serial)
                self._device_connected[name] = ok
                if ok:
                    info = get_device_info(name)
                    self.root.after(0, lambda n=name, i=info:
                        self._log(f"{n} 连接成功 ({i['width']}x{i['height']})"))
                else:
                    self.root.after(0, lambda n=name, e=err:
                        self._log(f"{n} 连接失败: {e}"))
            self.root.after(0, self._on_connect_all_done)

        threading.Thread(target=_do, daemon=True).start()

    def _on_connect_all_done(self):
        self._global_status_label.config(text="", foreground="gray")
        self._refresh_device_status_labels()

    # ── 走路测试页 ─────────────────────────────────

    def _build_walk_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="走路测试")

        # 设备选择行
        outer = self._build_device_select(tab, "walk", self._on_start_walk)
        ttk.Button(outer, text="截一张图", command=self._on_screenshot).pack(side=tk.RIGHT)

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

    # ── 跑环页 ─────────────────────────────────────

    def _build_quest_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="跑环任务")

        # 设备选择行
        self._build_device_select(tab, "quest", self._on_start_quest)

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

        ttk.Button(tab, text="打开模板目录",
                   command=lambda: os.startfile(os.path.join(BASE_DIR, "templates", "quest"))
                   ).pack(anchor=tk.W, pady=(8, 0))

    # ── 副本页 ─────────────────────────────────────

    def _build_dungeon_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="刷副本")

        # 设备选择行
        self._build_device_select(tab, "dungeon", self._on_start_dungeon)

        # 副本选择
        sel_frame = ttk.LabelFrame(tab, text="副本配置", padding=6)
        sel_frame.pack(fill=tk.X, pady=(0, 6))

        r1 = ttk.Frame(sel_frame)
        r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="副本:").pack(side=tk.LEFT)
        self._dung_id_var = tk.IntVar(value=90)
        ttk.Radiobutton(r1, text="90青丘境", variable=self._dung_id_var, value=90).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(r1, text="100副本", variable=self._dung_id_var, value=100).pack(side=tk.LEFT, padx=4)

        r2 = ttk.Frame(sel_frame)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="轮数:").pack(side=tk.LEFT)
        self._dung_rounds_var = tk.IntVar(value=3)
        ttk.Spinbox(r2, from_=1, to=99, textvariable=self._dung_rounds_var, width=4).pack(side=tk.LEFT, padx=4)
        ttk.Label(r2, text="(每个副本刷几次)", foreground="gray").pack(side=tk.LEFT)

        # 流程说明
        help_text = (
            "流程: 备忘→副本列表→选副本→传送→领任务→进入\n"
            "→自动遇怪(0键)→OCR监控剩余场数→Boss→结算\n"
            "坐标基于1080x1920，固定点击流程"
        )
        ttk.Label(tab, text=help_text, foreground="gray",
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(8, 0))

    # ── 100副本页 ─────────────────────────────────

    def _build_dungeon100_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="100副本")

        # 设备选择行
        self._build_device_select(tab, "dungeon100", self._on_start_dungeon100)

        help_text = (
            "Phase 0: NPC对话 -> 领任务 -> 确认进入\n"
            "Phase 1-4: 惊凡渊走路 + 传送门 -> 裂影渊 -> 泣魔渊 -> 陨仙渊\n"
            "Phase 5-6: NPC扫描(洞渊战魂/百鬼之王) + 交/接任务 + Boss战\n"
            "Phase 7: 任务列表 -> 确认 -> 瞬间传送 -> 提交任务\n"
            "使用条件: 角色需已在NPC面前，坐标基于1080x1920"
        )
        ttk.Label(tab, text=help_text, foreground="gray",
                  justify=tk.LEFT).pack(anchor=tk.W, pady=4)

    # ── 水晶刷怪页 ─────────────────────────────────

    def _build_crystal_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="水晶刷怪")

        # 设备选择行
        self._build_device_select(tab, "crystal", self._on_start_crystal)

        info = ttk.LabelFrame(tab, text="功能说明", padding=6)
        info.pack(fill=tk.X, pady=(0, 6))

        help_text = (
            "持续监控\"自动遇怪剩：XX场\"计数器。\n"
            "当剩余次数归零后，等待战斗结束，自动点击数字键0\n"
            "重新开启自动遇怪，实现无人值守循环刷怪。\n\n"
            "使用条件: 已在副本中，已手动开启过第一次自动遇怪。"
        )
        ttk.Label(info, text=help_text, foreground="gray",
                  justify=tk.LEFT).pack(anchor=tk.W)

    # ── 抓宠页 ─────────────────────────────────────

    def _build_pet_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="抓宠物")

        # 设备选择行
        self._build_device_select(tab, "pet", self._on_start_pet)

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

        ttk.Button(tab, text="打开模板目录",
                   command=lambda: os.startfile(os.path.join(BASE_DIR, "templates", "pet"))
                   ).pack(anchor=tk.W, pady=(8, 0))

    # ── 玄兵塔页 ─────────────────────────────────

    def _build_tower_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="玄兵塔")

        # 设备选择行
        self._build_device_select(tab, "tower", self._on_start_tower)

        # ── 模板匹配区 ──
        ctrl = ttk.LabelFrame(tab, text="模板匹配自动清塔", padding=6)
        ctrl.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(ctrl, text="模板: templates/tower/names/  (monster_floor1_01~03 等)",
                  foreground="gray").pack(anchor=tk.W)

        # 说明
        help_text = (
            "流程: 模板匹配怪物名字 → 走过去 → 进入战斗 → 自动 → 等结算 → 下一只\n"
            "需要模板:\n"
            "  names/monster_floorX_XX.png —— 怪物名字截图\n"
            "  enter_battle.png / auto_btn.png / battle_end.png —— UI 元素\n"
            "  next_floor.png —— 传送NPC (可选)"
        )
        ttk.Label(tab, text=help_text, foreground="gray", justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))

    # ── 仗剑除魔页 ─────────────────────────────

    def _build_chumo_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="仗剑除魔")

        # 设备选择行
        self._build_device_select(tab, "chumo", self._on_start_chumo)

        help_text = (
            "20轮跑环任务 —— 自动接取、传送、战斗、交任务。\n"
            "使用条件: 已在游戏中，角色可自由移动。\n"
            "流程: 找日常活动大使 → 接任务 → 传送 → 战斗 → 交任务 ×20轮"
        )
        ttk.Label(tab, text=help_text, foreground="gray",
                  justify=tk.LEFT).pack(anchor=tk.W, pady=4)

    # ── 名匠石磨页 ─────────────────────────────

    def _build_smith_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="名匠石磨")

        # 设备选择行
        self._build_device_select(tab, "smith", self._on_start_smith)

        help_text = (
            "站在名匠NPC旁边启动。无限循环兑换石磨。\n"
            "流程: 对话NPC → 选第3项 → 连点键5确认 → 下一轮"
        )
        ttk.Label(tab, text=help_text, foreground="gray",
                  justify=tk.LEFT).pack(anchor=tk.W, pady=4)

        ttk.Label(tab, text="每轮间隔(秒):").pack(anchor=tk.W)
        self._smith_interval_var = tk.DoubleVar(value=1.2)
        ttk.Spinbox(tab, from_=0.5, to=10, increment=0.1,
                    textvariable=self._smith_interval_var, width=5).pack(anchor=tk.W, pady=2)

    # ── 打泼猴页 ─────────────────────────────────

    def _build_monkey_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="打泼猴")

        # 设备选择行
        self._build_device_select(tab, "monkey", self._on_start_monkey)

        help_text = (
            "在泼猴附近启动。\n"
            "需要模板: templates/monkey/\n"
            "  monkey_npc.png — 泼猴名字截图\n"
            "  option_yubo.png — 对话框中的'夺回玉帛'"
        )
        ttk.Label(tab, text=help_text, foreground="gray", justify=tk.LEFT).pack(anchor=tk.W, pady=4)

        ttk.Label(tab, text="战斗等待(秒):").pack(anchor=tk.W)
        self._monkey_wait_var = tk.DoubleVar(value=4.4)
        ttk.Spinbox(tab, from_=1, to=30, increment=0.1, textvariable=self._monkey_wait_var, width=5).pack(anchor=tk.W, pady=2)

        ttk.Button(tab, text="打开模板目录",
                   command=lambda: os.startfile(os.path.join(BASE_DIR, "templates", "monkey"))
                   ).pack(anchor=tk.W, pady=(8, 0))

    # ── 血量显示页 ─────────────────────────────────

    def _build_blood_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="血量显示")

        top_bar = ttk.Frame(tab)
        top_bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(top_bar, text="控制游戏内怪物血条显示（需要 Frida）",
                  foreground="gray").pack(side=tk.LEFT)
        ttk.Button(top_bar, text="刷新设备",
                   command=self._on_refresh_blood).pack(side=tk.RIGHT, padx=4)

        self._blood_list_frame = ttk.Frame(tab)
        self._blood_list_frame.pack(fill=tk.BOTH, expand=True)

        help_text = (
            "工作原理: 通过 Frida 注入游戏进程，修改内存中的 blood flag。\n"
            "需要设备已 root，且 frida-server 已运行。\n"
            "点击[开启]后会自动设置端口转发并注入。"
        )
        ttk.Label(tab, text=help_text, foreground="gray",
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))

    def _on_refresh_blood(self):
        """刷新血量标签页的设备列表"""
        for w in self._blood_list_frame.winfo_children():
            w.destroy()
        self._blood_widgets.clear()

        devices = scan_available_devices()
        if not devices:
            ttk.Label(self._blood_list_frame, text="未发现设备",
                      foreground="gray").pack()
            return

        frida_port = 27042
        for i, dev in enumerate(devices):
            name = dev["name"]
            serial = dev["serial"]
            port = frida_port + i

            row = ttk.Frame(self._blood_list_frame)
            row.pack(fill=tk.X, pady=2)

            ttk.Label(row, text=name, width=10, anchor=tk.W).pack(side=tk.LEFT, padx=2)

            status_label = ttk.Label(row, text="未启动", foreground="gray", width=12)
            status_label.pack(side=tk.LEFT, padx=4)

            btn = ttk.Button(row, text="开启", width=6,
                             command=lambda n=name: self._on_toggle_blood(n))
            btn.pack(side=tk.LEFT, padx=2)

            self._blood_widgets[name] = (row, status_label, btn, serial, port)

            # 恢复已运行状态
            if name in self._blood_monitors:
                mon = self._blood_monitors[name]
                if mon.status == "running":
                    status_label.config(text="已开启", foreground="green")
                    btn.config(text="关闭")

    def _on_toggle_blood(self, name):
        if name not in self._blood_widgets:
            return
        _, label, btn, serial, port = self._blood_widgets[name]

        if name in self._blood_monitors and self._blood_monitors[name].status == "running":
            # 关闭
            self._log(f"[血量] 关闭 {name} 血条...")
            self._blood_monitors[name].stop()
            del self._blood_monitors[name]
            label.config(text="已关闭", foreground="gray")
            btn.config(text="开启")
        else:
            # 开启
            self._log(f"[血量] 启动 {name} 血条...")
            mon = BloodMonitor(name, serial, port)
            self._blood_monitors[name] = mon

            def on_status(dname, status, error):
                self.root.after(0, self._on_blood_status, dname, status, error)

            mon.start(on_status_change=on_status)
            label.config(text="启动中...", foreground="orange")
            btn.config(text="...")

    def _on_blood_status(self, name, status, error):
        """血量监控状态回调（UI 线程）"""
        if name not in self._blood_widgets:
            return
        _, label, btn, _, _ = self._blood_widgets[name]

        if status == "running":
            label.config(text="已开启", foreground="green")
            btn.config(text="关闭")
            self._log(f"[血量] {name} 血条已开启")
        elif status == "error":
            label.config(text=f"错误: {error[:20]}", foreground="red")
            btn.config(text="开启")
            self._log(f"[血量] {name} 启动失败: {error}")
        elif status == "stopped":
            label.config(text="已关闭", foreground="gray")
            btn.config(text="开启")

    # ── 任务启动方法 ──────────────────────────────

    # ── 走路 ─────────────────────────────────────

    def _on_start_walk(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "walk", "params": {
            "direction": self._dir_var.get(),
            "steps": self._steps_var.get(),
            "use_joystick": self._mode_var.get() == "joystick",
            "tap_x": self._tap_x_var.get(), "tap_y": self._tap_y_var.get(),
            "spread": self._spread_var.get()}}
        self._start_worker("walk", dev, spec)

    def _start_worker(self, tab_key: str, dev: str, spec: dict):
        """在独立子进程中启动任务并更新 UI"""
        spec["device_name"] = dev
        spec["serial"] = self._device_serial.get(dev, "")
        proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "task_worker.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            cwd=BASE_DIR)
        try:
            proc.stdin.write(json.dumps(spec, ensure_ascii=False) + "\n")
            proc.stdin.flush()
        except Exception:
            pass
        self._workers[dev] = {"proc": proc, "tab_key": tab_key}
        self._tab_devices.setdefault(tab_key, []).append(dev)
        threading.Thread(target=self._read_worker, args=(dev, proc, tab_key), daemon=True).start()
        self._update_dev_row(tab_key, dev)

    def _read_worker(self, dev: str, proc, tab_key: str):
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                if not line:
                    continue
                # 过滤 airtest 的调试日志（[DEBUG]/[INFO]），只上屏任务关键日志
                if "[DEBUG]" in line or "[INFO]" in line:
                    continue
                self.root.after(0, self._log, line)
        except Exception:
            pass
        finally:
            self.root.after(0, self._on_worker_exit, dev, tab_key)

    # ── 跑环 ─────────────────────────────────────

    def _on_start_quest(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        interval = self._quest_interval_var.get()
        steps = [
            {"template": "templates/quest/accept.png", "wait": interval, "desc": "接受任务"},
            {"template": "templates/quest/track.png",  "wait": interval, "desc": "追踪"},
            {"template": "templates/quest/npc.png",    "wait": interval, "desc": "对话NPC"},
            {"template": "templates/quest/done.png",   "wait": interval, "desc": "交任务"},
        ]
        spec = {"task_type": "quest", "params": {"steps": steps, "loop": self._quest_loop_var.get()}}
        self._start_worker("quest", dev, spec)

    # ── 副本 ─────────────────────────────────────

    def _on_start_dungeon(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "dungeon", "params": {
            "dungeon_id": self._dung_id_var.get(), "rounds": self._dung_rounds_var.get()}}
        self._start_worker("dungeon", dev, spec)

    # ── 100副本 ─────────────────────────────────────

    def _on_start_dungeon100(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "dungeon100"}
        self._start_worker("dungeon100", dev, spec)

    # ── 抓宠 ─────────────────────────────────────

    def _on_start_pet(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        interval = self._pet_interval_var.get()
        steps = [
            {"template": "templates/pet/find.png",   "wait": interval, "desc": "找宠物"},
            {"template": "templates/pet/attack.png", "wait": interval, "desc": "进入战斗"},
            {"template": "templates/pet/catch.png",  "wait": interval, "desc": "捕捉"},
            {"template": "templates/pet/done.png",   "wait": interval, "desc": "确认"},
        ]
        spec = {"task_type": "pet", "params": {"steps": steps, "loop": self._pet_loop_var.get()}}
        self._start_worker("pet", dev, spec)

    # ── 玄兵塔 ─────────────────────────────────────

    def _on_start_tower(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        self._start_worker("tower", dev, {"task_type": "tower"})

    # ── 仗剑除魔 ─────────────────────────────────────

    def _on_start_chumo(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        self._start_worker("chumo", dev, {"task_type": "chumo"})

    # ── 名匠石磨 ─────────────────────────────────────

    def _on_start_smith(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "smith", "params": {"interval": self._smith_interval_var.get()}}
        self._start_worker("smith", dev, spec)

    # ── 打泼猴 ─────────────────────────────────────

    def _on_start_monkey(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "monkey", "params": {"wait_battle": self._monkey_wait_var.get()}}
        self._start_worker("monkey", dev, spec)

    # ── 水晶刷怪 ─────────────────────────────────────

    def _on_start_crystal(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        self._start_worker("crystal", dev, {"task_type": "crystal"})

    # ── 截图 ─────────────────────────────────────

    def _on_screenshot(self):
        running = list(self._workers.keys())
        connected = [n for n, c in self._device_connected.items() if c]
        dev = (running + connected)[0] if (running + connected) else ""
        if not dev:
            self._log("错误: 请先连接设备!")
            return
        ok = switch_device(dev)
        if not ok:
            self._log(f"错误: 切换到设备 {dev} 失败!")
            return
        from core.actions import screenshot
        from airtest.core.api import device as cur_dev
        try:
            cur = cur_dev()
            self._log(f"当前设备: {cur}")
        except:
            pass
        name = f"screenshot_{dev}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(BASE_DIR, "logs", name)
        screenshot(path)
        self._log(f"截图({dev}): {path}")

    MAX_LOG_LINES = 2000

    def _log(self, msg: str):
        self._log_area.config(state=tk.NORMAL)
        self._log_area.insert(tk.END, msg + "\n")
        # 限制日志条数，防止多 worker 刷屏拖慢 UI
        line_count = int(self._log_area.index("end-1c").split(".")[0])
        if line_count > self.MAX_LOG_LINES:
            self._log_area.delete("1.0", f"{line_count - self.MAX_LOG_LINES}.0")
        self._log_area.see(tk.END)
        self._log_area.config(state=tk.DISABLED)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
