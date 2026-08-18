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
    connect_device_by_serial, get_device_info,
    list_devices, scan_available_devices,
)
from frida_blood.monitor import BloodMonitor


# ── 暗黑终端主题 ─────────────────────────────────
# 配色（近黑底 + 霓虹绿主色，GitHub Dark / 黑客终端风）
C_BG        = "#0d1117"   # 主背景
C_BG_PANEL  = "#161b22"   # 面板/卡片背景
C_BG_INPUT  = "#0a0d13"   # 日志区/输入框背景（更深）
C_BORDER    = "#30363d"   # 边框
C_PRIMARY   = "#00ff9d"   # 霓虹绿主色（运行中/选中）
C_ACCENT    = "#00d4ff"   # 青色辅助（高亮/链接）
C_TEXT      = "#c9d1d9"   # 正文
C_DIM       = "#7d8590"   # 次要文字（原 gray）
C_WARN      = "#ffa657"   # 橙色（警告/连接中/上次进度）
C_ERROR     = "#ff6b6b"   # 红色（错误）
C_OK        = "#3fb950"   # 绿色（已连接/已开启）
C_DONE_BG   = "#3d2e10"   # 今日任务·已打(黄底)
C_DONE_FG   = "#ffd479"   # 今日任务·已打(黄字)
C_TODO_BG   = "#0f2f23"   # 今日任务·未打(绿底)
C_TODO_FG   = "#4ade80"   # 今日任务·未打(绿字)
C_STOP_BG   = "#b02418"   # 一键停止按钮(暗红)
C_STOP_ACT  = "#7a1a12"   # 一键停止按钮(按下)

# 字体（等宽 = 日志/横幅，中文 UI = 微软雅黑）
FONT_MONO   = "Consolas"
FONT_UI     = "Microsoft YaHei UI"

# 顶部 ASCII 横幅（ANSI Shadow 风格 "XUNQIN"）
BANNER_ASCII = (
    " ██╗  ██╗██╗   ██╗███╗   ██╗    ██████╗ ██╗███╗   ██╗\n"
    " ╚██╗██╔╝██║   ██║████╗  ██║   ██╔═══██╗██║████╗  ██║\n"
    "  ╚███╔╝ ███████║██╔██╗ ██║   ██║   ██║██║██╔██╗ ██║\n"
    "  ██╔██╗ ██╔══██║██║╚██╗██║   ██║   ██║██║██║╚██╗██║\n"
    " ██╔╝ ██╗██║  ██║██║ ╚████║   ╚██████╔╝██║██║ ╚████║\n"
    " ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝    ╚═════╝ ╚═╝╚═╝  ╚═══╝"
)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("寻秦OL · 自动化控制台")
        self.root.geometry("1280x820")
        self.root.minsize(1024, 660)
        self.root.resizable(True, True)
        self.root.configure(bg=C_BG)

        self._workers = {}  # device_name -> {"proc": Popen, "tab_key": str}
        self._device_check_vars = {}  # name -> IntVar (checkbox)
        self._device_connected = {}  # name -> bool
        self._device_serial = {}  # name -> serial
        self._device_status_labels = {}  # name -> ttk.Label (连接状态)
        self._tab_device_frames = {}  # tab_key -> Frame (设备行容器)
        self._tab_row_widgets = {}    # tab_key -> dict[name -> {start,stop,status}]
        self._tab_handlers = {}       # tab_key -> callable(dev)
        self._tab_devices = {}        # tab_key -> list[device_name] (当前运行)
        self._tab_widgets = {}        # tab_key -> tab frame (用于运行标记)
        self._notebook = None         # 标签页容器
        self._blood_monitors = {}  # name -> BloodMonitor
        self._blood_widgets = {}  # name -> (frame, status_label, btn)
        self._dungeon100_start_options = ["自动续跑", "从头开始 (Phase 0)"] + [f"Phase {i}" for i in range(1, 11)]
        self._dungeon90_start_options = ["自动续跑", "从头开始 (Phase 0)"] + [f"Phase {i}" for i in range(1, 13)]
        self._tie1_start_options = ["自动续跑", "从头开始 (Phase 0)"] + [f"Phase {i}" for i in range(1, 14)]
        self._tie2_start_options = ["自动续跑", "从头开始 (Phase 0)"] + [f"Phase {i}" for i in range(1, 11)]
        self._tie3_start_options = ["自动续跑", "从头开始 (Phase 0)"] + [f"Phase {i}" for i in range(1, 16)]
        self._tie4_start_options = ["自动续跑", "从头开始 (Phase 0)"] + [f"Phase {i}" for i in range(1, 15)]
        # 今日任务记录（全局合并，按日期）
        self._today_tasks = [
            ("dungeon100", "100副本"), ("dungeon90", "90副本"),
            ("tie1", "铁1副本"), ("tie2", "铁2副本"),
            ("tie3", "铁3副本"), ("tie4", "铁4副本"),
            ("tower", "玄兵塔"), ("chumo", "仗剑除魔"),
        ]
        self._done_markers = {
            "dungeon100": "100副本流程完成", "dungeon90": "90副本流程完成",
            "tie1": "铁1副本流程完成", "tie2": "铁2副本流程完成",
            "tie3": "铁3副本流程完成", "tie4": "铁4副本流程完成",
            "tower": "玄兵塔全部通关", "chumo": "仗剑除魔全部完成",
        }
        self._today_labels = {}   # tab_key -> tk.Label

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self._auto_init()
        threading.Thread(target=self._warmup_ocr, daemon=True).start()

    # ── UI 构建 ─────────────────────────────────────

    def _build_ui(self):
        # 全局样式（clam 主题 + 暗黑终端配色）
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".", background=C_BG, foreground=C_TEXT, font=(FONT_UI, 10))
        style.configure("TNotebook", background=C_BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=[16, 8], font=(FONT_UI, 10, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", C_BG_PANEL), ("!selected", C_BG)],
                  foreground=[("selected", C_PRIMARY), ("!selected", C_DIM)])
        style.configure("TLabelframe", background=C_BG_PANEL, bordercolor=C_BORDER,
                        borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=C_BG_PANEL, foreground=C_PRIMARY,
                        font=(FONT_UI, 9, "bold"))
        style.configure("TButton", padding=[10, 5], font=(FONT_UI, 10))
        style.map("TButton",
                  background=[("active", C_BG_INPUT), ("!disabled", C_BG_PANEL),
                              ("disabled", C_BG)],
                  foreground=[("active", C_PRIMARY), ("!disabled", C_TEXT),
                              ("disabled", C_DIM)])
        style.configure("TCombobox", padding=[4, 2], font=(FONT_UI, 10),
                        fieldbackground=C_BG_INPUT, background=C_BG_PANEL,
                        foreground=C_TEXT, arrowcolor=C_PRIMARY)
        style.map("TCombobox",
                  fieldbackground=[("readonly", C_BG_INPUT)],
                  foreground=[("readonly", C_TEXT)])
        style.configure("TCheckbutton", background=C_BG, foreground=C_TEXT,
                        font=(FONT_UI, 10))
        style.map("TCheckbutton", background=[("active", C_BG)])
        style.configure("TSpinbox", fieldbackground=C_BG_INPUT, background=C_BG_PANEL,
                        foreground=C_TEXT, arrowcolor=C_PRIMARY)

        # 顶部区域：左侧横幅 + 右侧今日任务看板
        top_bar = ttk.Frame(self.root)
        top_bar.pack(fill=tk.X, padx=12, pady=(10, 0))

        left = ttk.Frame(top_bar)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        banner = tk.Label(left, text=BANNER_ASCII, bg=C_BG, fg=C_PRIMARY,
                          font=(FONT_MONO, 9, "bold"), justify=tk.LEFT, anchor=tk.W)
        banner.pack(fill=tk.X)

        sub = tk.Label(left, text="寻秦OL · 多设备自动化控制台",
                       bg=C_BG, fg=C_DIM, font=(FONT_UI, 10))
        sub.pack(anchor=tk.W, pady=(0, 2))

        # 右侧：今日任务紧凑看板
        self._build_today_panel(top_bar)

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
        tk.Button(btn_row, text="一键停止全部", command=self._stop_all, bg=C_STOP_BG, fg="#ffffff",
                  activebackground=C_STOP_ACT, activeforeground="#ffffff",
                  font=(FONT_UI, 10, "bold"), relief=tk.FLAT, bd=0, cursor="hand2").pack(side=tk.RIGHT, padx=4)
        self._global_status_label = ttk.Label(btn_row, text="", foreground=C_DIM)
        self._global_status_label.pack(side=tk.LEFT, padx=8)

        # 主体：标签页 + 日志（grid 布局：日志固定宽度始终可见，标签页占剩余）
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)              # 标签页：占剩余空间
        body.grid_columnconfigure(1, weight=0, minsize=420)  # 日志：固定宽度

        # 左侧：标签页
        notebook = ttk.Notebook(body)
        notebook.grid(row=0, column=0, sticky="nsew")
        self._notebook = notebook

        self._build_dungeon90_tab(notebook)
        self._build_dungeon100_tab(notebook)
        self._build_tie1_tab(notebook)
        self._build_tie2_tab(notebook)
        self._build_tie3_tab(notebook)
        self._build_tie4_tab(notebook)
        self._build_crystal_tab(notebook)
        self._build_pet_tab(notebook)
        self._build_tower_tab(notebook)
        self._build_chumo_tab(notebook)
        self._build_smith_tab(notebook)
        self._build_monkey_tab(notebook)
        self._build_blood_tab(notebook)

        # 右侧：日志
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        log_frame = ttk.LabelFrame(right, text="运行日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self._log_area = scrolledtext.ScrolledText(
            log_frame, width=40, state=tk.DISABLED, wrap=tk.WORD,
            bg=C_BG_INPUT, fg=C_PRIMARY, insertbackground=C_PRIMARY,
            selectbackground=C_ACCENT, selectforeground=C_BG_INPUT,
            relief=tk.FLAT, bd=0, font=(FONT_MONO, 9))
        self._log_area.pack(fill=tk.BOTH, expand=True)

    # ── 今日任务看板 ─────────────────────────────

    def _build_today_panel(self, parent):
        panel = ttk.LabelFrame(parent, text="今日任务", padding=6)
        panel.pack(side=tk.RIGHT, anchor=tk.N, padx=(12, 0))

        header = ttk.Frame(panel)
        header.pack(fill=tk.X, pady=(0, 4))
        self._today_date_label = ttk.Label(header, text="", font=(FONT_UI, 11, "bold"))
        self._today_date_label.pack(side=tk.LEFT)
        self._today_summary_label = ttk.Label(header, text="", foreground=C_DIM)
        self._today_summary_label.pack(side=tk.LEFT, padx=8)

        ttk.Label(panel, text="黄=已打  绿=未打  点击切换",
                  foreground=C_DIM).pack(anchor=tk.W, pady=(0, 4))

        grid = ttk.Frame(panel)
        grid.pack()
        for i, (key, name) in enumerate(self._today_tasks):
            lbl = tk.Label(grid, text=name, font=(FONT_UI, 10, "bold"),
                           fg=C_TODO_FG, bg=C_TODO_BG, padx=8, pady=6,
                           width=8, relief=tk.FLAT, bd=0, cursor="hand2")
            lbl.grid(row=i // 4, column=i % 4, padx=3, pady=3)
            lbl.bind("<Button-1>", lambda e, k=key: self._toggle_task_done(k))
            self._today_labels[key] = lbl

        self._refresh_today_tab()

    def _today_record_path(self):
        return os.path.join(BASE_DIR, "logs", "daily_task_record.json")

    def _load_today_record(self):
        try:
            with open(self._today_record_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _refresh_today_tab(self):
        today = time.strftime("%Y-%m-%d")
        data = self._load_today_record()
        done_map = data.get(today, {})
        for key, lbl in self._today_labels.items():
            done = bool(done_map.get(key, False))
            lbl.config(bg=C_DONE_BG if done else C_TODO_BG,
                       fg=C_DONE_FG if done else C_TODO_FG)
        done_count = sum(1 for k in self._today_labels if done_map.get(k, False))
        total = len(self._today_tasks)
        self._today_date_label.config(text=f"今日任务 ({today})")
        self._today_summary_label.config(text=f"已完成 {done_count}/{total}")

    def _mark_task_done(self, tab_key):
        if tab_key not in self._done_markers:
            return
        today = time.strftime("%Y-%m-%d")
        data = self._load_today_record()
        data.setdefault(today, {})
        data[today][tab_key] = True
        try:
            with open(self._today_record_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self._refresh_today_tab()

    def _toggle_task_done(self, key, event=None):
        today = time.strftime("%Y-%m-%d")
        data = self._load_today_record()
        data.setdefault(today, {})
        data[today][key] = not bool(data[today].get(key, False))
        try:
            with open(self._today_record_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self._refresh_today_tab()

    # ── 设备选择辅助 ─────────────────────────────

    def _build_device_select(self, tab, tab_key: str, on_start):
        """每个已连接设备一行，独立开始/停止按钮，返回外层 frame"""
        self._tab_handlers[tab_key] = on_start
        self._tab_widgets[tab_key] = tab
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
                ttk.Label(rows_frame, text="(无已连接设备)", foreground=C_DIM).pack(anchor=tk.W)
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
                          foreground=C_PRIMARY if running else "gray").pack(side=tk.LEFT, padx=8)
                widgets_map[name] = {"start": start_btn, "stop": stop_btn, "status": status_var}
                phase_tab = {
                    "dungeon100": (self._dungeon100_last_phase, self._dungeon100_start_options),
                    "dungeon90": (self._dungeon90_last_phase, self._dungeon90_start_options),
                    "tie1": (self._tie1_last_phase, self._tie1_start_options),
                    "tie2": (self._tie2_last_phase, self._tie2_start_options),
                    "tie3": (self._tie3_last_phase, self._tie3_start_options),
                    "tie4": (self._tie4_last_phase, self._tie4_start_options),
                }.get(tab_key)
                if phase_tab:
                    last_fn, options = phase_tab
                    last = last_fn(name)
                    if last >= 0:
                        ttk.Label(row, text=f"上次: Phase {last}",
                                  foreground=C_WARN).pack(side=tk.LEFT, padx=6)
                    start_var = tk.StringVar(value="自动续跑")
                    ttk.Combobox(row, textvariable=start_var,
                                 values=options,
                                 state="readonly", width=14).pack(side=tk.LEFT, padx=6)
                    widgets_map[name]["start_var"] = start_var

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
            # 兜底：宽限期后仍未退出则强制杀进程，并强制刷新 UI 状态
            # （防止 _read_worker 卡在 stdout 读不到 EOF，导致 _on_worker_exit 不触发、状态残留）
            def _force_kill(d=dev, proc=w["proc"]):
                time.sleep(6)
                cur = self._workers.get(d)
                # 只有当前记录的仍是这个 proc（用户没重新开始新任务）才清理
                if cur and cur["proc"] is proc:
                    if proc.poll() is None:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    self.root.after(0, self._on_worker_exit, d, tab_key)
            threading.Thread(target=_force_kill, daemon=True).start()
        widgets = self._tab_row_widgets.get(tab_key, {}).get(dev)
        if widgets:
            widgets["stop"].config(state=tk.DISABLED)
            widgets["status"].set("停止中")

    def _stop_all(self):
        """一键停止所有运行中的任务（总开关）"""
        workers = list(self._workers.items())
        if not workers:
            self._log("当前无运行中的任务")
            return
        self._log("一键停止：正在停止所有任务...")
        for dev, w in workers:
            self._stop_dev(w.get("tab_key", ""), dev)

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
        self._update_tab_titles()

    def _update_tab_titles(self):
        """在运行中的任务标签页标题上标记 ●"""
        if not self._notebook:
            return
        for tab_key, tab in self._tab_widgets.items():
            running = bool(self._tab_devices.get(tab_key))
            cur = self._notebook.tab(tab, "text") or tab_key
            base = cur.replace(" ●", "")
            self._notebook.tab(tab, text=base + (" ●" if running else ""))

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
                      foreground=C_DIM).pack(anchor=tk.W, pady=4)
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
            color = C_OK if connected else C_DIM
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
                color = C_OK if connected else C_DIM
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

    def _warmup_ocr(self):
        """后台预热 OCR 共享服务，避免任务首次用到 OCR 时卡在连接阶段"""
        try:
            from core.ocr_client import warmup
            warmup()
        except Exception:
            pass

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

        self._global_status_label.config(text="连接中...", foreground=C_WARN)

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
        self._global_status_label.config(text="", foreground=C_DIM)
        self._refresh_device_status_labels()

    # ── 90副本页 ─────────────────────────────────

    def _build_dungeon90_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="90副本")

        self._build_device_select(tab, "dungeon90", self._on_start_dungeon90)

        ttk.Label(tab, text="每台设备行可独立选择起始阶段；\"自动续跑\"会从该设备上次完成的 Phase 之后继续",
                  foreground=C_DIM).pack(anchor=tk.W, pady=(0, 4))

        help_text = (
            "Phase 0: 传送(备忘→副本→青丘境→瞬间传送)\n"
            "Phase 1: 进入副本(NPC对话)\n"
            "Phase 2: 青丘入口 遇怪2次→进灵隐绝境\n"
            "Phase 3: 灵隐绝境 找瑞南羽→交→接(触发Boss)\n"
            "Phase 4: 瑞南羽Boss战→交→接\n"
            "Phase 5: 回青丘入口\n"
            "Phase 6: 青丘入口 遇怪2次→进灵隐绝境\n"
            "Phase 7: 灵隐绝境 找瑞南羽→交→接\n"
            "Phase 8: 进禁忌古道→遇怪2次→回灵隐\n"
            "Phase 9: 灵隐绝境 找瑞南羽→交→接\n"
            "Phase 10: 进禁忌古道→进迷影禁地\n"
            "Phase 11: 迷影禁地 找九尾异兽→交→接(触发Boss)\n"
            "Phase 12: 九尾异兽Boss战→交→接→交\n"
            "坐标基于1080x1920"
        )
        ttk.Label(tab, text=help_text, foreground=C_DIM,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=4)

    # ── 100副本页 ─────────────────────────────────

    def _build_dungeon100_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="100副本")

        # 设备选择行（每台设备行内含: 起点选择 + 上次进度）
        self._build_device_select(tab, "dungeon100", self._on_start_dungeon100)

        ttk.Label(tab, text="每台设备行可独立选择起始阶段；\"自动续跑\"会从该设备上次完成的 Phase 之后继续",
                  foreground=C_DIM).pack(anchor=tk.W, pady=(0, 4))

        help_text = (
            "Phase 0: 从备忘打开副本(混沌邪灵渊→瞬间传送)\n"
            "Phase 1: 进入副本(阳谷→惊凡渊)\n"
            "Phase 2: 惊凡渊走路+传送门 → 裂影渊\n"
            "Phase 3: 裂影渊 找洞渊战魂→交任务→接任务\n"
            "Phase 4: 裂影渊 洞渊战魂Boss战→交任务→接任务\n"
            "Phase 5: 裂影渊→泣魔渊 传送门\n"
            "Phase 6: 泣魔渊→陨仙渊 走路+传送门\n"
            "Phase 7: 陨仙渊 找百鬼之王→交任务→接任务\n"
            "Phase 8: 陨仙渊 遇怪2场→找百鬼之王→交任务→接任务\n"
            "Phase 9: 陨仙渊 百鬼之王Boss战→交任务→接任务×2\n"
            "Phase 10: 陨仙渊→阳谷 传送出地图+提交任务\n"
            "使用条件: 从备忘自动打开副本，坐标基于1080x1920"
        )
        ttk.Label(tab, text=help_text, foreground=C_DIM,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=4)

    # ── 铁1副本页 ─────────────────────────────────

    def _build_tie1_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="铁1副本")

        # 设备选择行（每台设备行内含: 起点选择 + 上次进度）
        self._build_device_select(tab, "tie1", self._on_start_tie1)

        ttk.Label(tab, text="每台设备行可独立选择起始阶段；\"自动续跑\"会从该设备上次完成的 Phase 之后继续",
                  foreground=C_DIM).pack(anchor=tk.W, pady=(0, 4))

        help_text = (
            "Phase 0: 传送(备忘→副本→赤炼→瞬间传送)\n"
            "Phase 1: 进入副本(NPC对话)\n"
            "Phase 2: 乱葬废墟 找小女孩→交→接\n"
            "Phase 3: 乱葬废墟 遇怪2次→找小女孩→交→接\n"
            "Phase 4: 传送门(20,900)→虐杀之地\n"
            "Phase 5: 虐杀之地 找虐杀之鬼→交→接→Boss战→交→接\n"
            "Phase 6: 右上角2次→右下角2次→乱葬废墟\n"
            "Phase 7: 乱葬废墟 找小女孩→交→接\n"
            "Phase 8: 右下角3次→右上角3次→枯魂阴牢\n"
            "Phase 9: 枯魂阴牢 找黑衣人→交→接\n"
            "Phase 10: 枯魂阴牢 遇怪2次→找小男孩→交→接\n"
            "Phase 11: 右下角4次→赤炼血池\n"
            "Phase 12: 赤炼血池 找暗影杀手→交→接→Boss战→交→接\n"
            "Phase 13: 任务列表选中(副)戏之谢幕→确定→瞬间传送→提交\n"
            "坐标基于1080x1920"
        )
        ttk.Label(tab, text=help_text, foreground=C_DIM,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=4)

    # ── 铁2副本页 ─────────────────────────────────

    def _build_tie2_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="铁2副本")

        # 设备选择行（每台设备行内含: 起点选择 + 上次进度）
        self._build_device_select(tab, "tie2", self._on_start_tie2)

        ttk.Label(tab, text="每台设备行可独立选择起始阶段；\"自动续跑\"会从该设备上次完成的 Phase 之后继续",
                  foreground=C_DIM).pack(anchor=tk.W, pady=(0, 4))

        help_text = (
            "Phase 0: 传送(备忘→副本→浮游→瞬间传送)\n"
            "Phase 1: 进入副本(NPC对话)\n"
            "Phase 2: 虚幻之地 找红衣女→交→接\n"
            "Phase 3: 点(550,200)3次→(700,200)2次→渴望之境\n"
            "Phase 4: 渴望之境 找夫人→交→接(交前补足战斗)\n"
            "Phase 5: 点(1050,200)3次→回忆之地\n"
            "Phase 6: 回忆之地 找红衣女→交→接(交前补足战斗)\n"
            "Phase 7: 点(550,200)4次→痛苦之境\n"
            "Phase 8: 痛苦之境 找灭城将军→交→接→Boss战→交→接\n"
            "Phase 9: 找红衣女→交→接→Boss战→交→接\n"
            "Phase 10: 任务列表选中(副)解决之道→确定→瞬间传送→提交\n"
            "坐标基于1080x1920"
        )
        ttk.Label(tab, text=help_text, foreground=C_DIM,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=4)

    # ── 铁3副本页 ─────────────────────────────────

    def _build_tie3_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="铁3副本")

        # 设备选择行（每台设备行内含: 起点选择 + 上次进度）
        self._build_device_select(tab, "tie3", self._on_start_tie3)

        ttk.Label(tab, text="每台设备行可独立选择起始阶段；\"自动续跑\"会从该设备上次完成的 Phase 之后继续",
                  foreground=C_DIM).pack(anchor=tk.W, pady=(0, 4))

        help_text = (
            "Phase 0: 传送(备忘→副本→隐龙→瞬间传送)\n"
            "Phase 1: 进入副本(NPC对话)\n"
            "Phase 2: 焚火废墟 遇怪1场\n"
            "Phase 3: 焚火废墟 说书人→交→接(第1轮)\n"
            "Phase 4: 焚火废墟 遇怪1场\n"
            "Phase 5: 焚火废墟 说书人→交→接(第2轮)\n"
            "Phase 6: 走路→烈焰野地(左上角3次/右上角3次)\n"
            "Phase 7: 点(20,600)3次→龙隐秘地\n"
            "Phase 8: 龙隐秘地 找龙女→交→接\n"
            "Phase 9: 龙隐秘地 Boss战→交→接\n"
            "Phase 10: 点(20,600)3次→龙啸古地\n"
            "Phase 11: 龙啸古地 说书人→交→接(第1次)\n"
            "Phase 12: 龙啸古地 遇怪2场\n"
            "Phase 13: 龙啸古地 说书人→交→接(第2次)\n"
            "Phase 14: 龙啸古地 Boss战→交→接\n"
            "Phase 15: 任务列表选中(副)天星子大计→确定→瞬间传送→提交\n"
            "坐标基于1080x1920"
        )
        ttk.Label(tab, text=help_text, foreground=C_DIM,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=4)

    # ── 铁4副本页 ─────────────────────────────────

    def _build_tie4_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="铁4副本")

        # 设备选择行（每台设备行内含: 起点选择 + 上次进度）
        self._build_device_select(tab, "tie4", self._on_start_tie4)

        ttk.Label(tab, text="每台设备行可独立选择起始阶段；\"自动续跑\"会从该设备上次完成的 Phase 之后继续",
                  foreground=C_DIM).pack(anchor=tk.W, pady=(0, 4))

        help_text = (
            "Phase 0: 传送(备忘→副本→魔界之门→瞬间传送)\n"
            "Phase 1: 进入副本(NPC对话)\n"
            "Phase 2: 焚骨熔岩 找心魔→交→接\n"
            "Phase 3: 焚骨熔岩 自动遇怪1次\n"
            "Phase 4: 焚骨熔岩 再找心魔→交→接\n"
            "Phase 5: 点(550,200)3次→隐之境\n"
            "Phase 6: 点左下角3次→左上角3次→鬼爪炼狱\n"
            "Phase 7: 鬼爪炼狱 找蜃兽→交→接\n"
            "Phase 8: 鬼爪炼狱 Boss战\n"
            "Phase 9: 蜃兽战后 交→接\n"
            "Phase 10: 回隐之境(右下角→右上角)\n"
            "Phase 11: 进炼魂祭坛(点(1050,650)3次)\n"
            "Phase 12: 炼魂祭坛 补1场战斗\n"
            "Phase 13: 炼魂祭坛 找天星子→交\n"
            "Phase 14: 接新任务→Boss战→交任务\n"
            "坐标基于1080x1920"
        )
        ttk.Label(tab, text=help_text, foreground=C_DIM,
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
            "循环执行点击序列触发遇怪，模板匹配检测战斗结束。\n"
            "点击序列: (100,200) → (1000,200) → (200,450) → (200,450)\n"
            "战斗结束后立即重复，无限循环。\n\n"
            "使用条件: 角色已在目标位置。"
        )
        ttk.Label(info, text=help_text, foreground=C_DIM,
                  justify=tk.LEFT).pack(anchor=tk.W)

        # 点击间隔设置（全局，所有设备适用）
        gap_box = ttk.LabelFrame(tab, text="点击间隔(秒) — 全局，所有设备适用", padding=6)
        gap_box.pack(fill=tk.X, pady=(0, 6))

        self._crystal_gap1_var = tk.DoubleVar(value=0.1)
        self._crystal_gap2_var = tk.DoubleVar(value=0.1)
        self._crystal_gap3_var = tk.DoubleVar(value=0.4)

        row = ttk.Frame(gap_box)
        row.pack(anchor=tk.W)
        ttk.Label(row, text="间隔1  (100,200)→(1000,200):").pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=0.1, to=5, increment=0.1,
                    textvariable=self._crystal_gap1_var, width=5).pack(side=tk.LEFT, padx=4)

        row2 = ttk.Frame(gap_box)
        row2.pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(row2, text="间隔2  (1000,200)→(200,450):").pack(side=tk.LEFT)
        ttk.Spinbox(row2, from_=0.1, to=5, increment=0.1,
                    textvariable=self._crystal_gap2_var, width=5).pack(side=tk.LEFT, padx=4)

        row3 = ttk.Frame(gap_box)
        row3.pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(row3, text="间隔3  (200,450)→(200,450):").pack(side=tk.LEFT)
        ttk.Spinbox(row3, from_=0.1, to=5, increment=0.1,
                    textvariable=self._crystal_gap3_var, width=5).pack(side=tk.LEFT, padx=4)

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
        ttk.Label(tab, text=help_text, foreground=C_DIM, justify=tk.LEFT).pack(anchor=tk.W, pady=4)

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
                  foreground=C_DIM).pack(anchor=tk.W)

        # 说明
        help_text = (
            "流程: 模板匹配怪物名字 → 走过去 → 进入战斗 → 自动 → 等结算 → 下一只\n"
            "需要模板:\n"
            "  names/monster_floorX_XX.png —— 怪物名字截图\n"
            "  enter_battle.png / auto_btn.png / battle_end.png —— UI 元素\n"
            "  next_floor.png —— 传送NPC (可选)"
        )
        ttk.Label(tab, text=help_text, foreground=C_DIM, justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))

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
        ttk.Label(tab, text=help_text, foreground=C_DIM,
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
        ttk.Label(tab, text=help_text, foreground=C_DIM,
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
        ttk.Label(tab, text=help_text, foreground=C_DIM, justify=tk.LEFT).pack(anchor=tk.W, pady=4)

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
                  foreground=C_DIM).pack(side=tk.LEFT)
        ttk.Button(top_bar, text="刷新设备",
                   command=self._on_refresh_blood).pack(side=tk.RIGHT, padx=4)

        self._blood_list_frame = ttk.Frame(tab)
        self._blood_list_frame.pack(fill=tk.BOTH, expand=True)

        help_text = (
            "工作原理: 通过 Frida 注入游戏进程，修改内存中的 blood flag。\n"
            "需要设备已 root，且 frida-server 已运行。\n"
            "点击[开启]后会自动设置端口转发并注入。"
        )
        ttk.Label(tab, text=help_text, foreground=C_DIM,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))

    def _on_refresh_blood(self):
        """刷新血量标签页的设备列表"""
        for w in self._blood_list_frame.winfo_children():
            w.destroy()
        self._blood_widgets.clear()

        devices = scan_available_devices()
        if not devices:
            ttk.Label(self._blood_list_frame, text="未发现设备",
                      foreground=C_DIM).pack()
            return

        frida_port = 27042
        for i, dev in enumerate(devices):
            name = dev["name"]
            serial = dev["serial"]
            port = frida_port + i

            row = ttk.Frame(self._blood_list_frame)
            row.pack(fill=tk.X, pady=2)

            ttk.Label(row, text=name, width=10, anchor=tk.W).pack(side=tk.LEFT, padx=2)

            status_label = ttk.Label(row, text="未启动", foreground=C_DIM, width=12)
            status_label.pack(side=tk.LEFT, padx=4)

            btn = ttk.Button(row, text="开启", width=6,
                             command=lambda n=name: self._on_toggle_blood(n))
            btn.pack(side=tk.LEFT, padx=2)

            self._blood_widgets[name] = (row, status_label, btn, serial, port)

            # 恢复已运行状态
            if name in self._blood_monitors:
                mon = self._blood_monitors[name]
                if mon.status == "running":
                    status_label.config(text="已开启", foreground=C_OK)
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
            label.config(text="已关闭", foreground=C_DIM)
            btn.config(text="开启")
        else:
            # 开启
            self._log(f"[血量] 启动 {name} 血条...")
            mon = BloodMonitor(name, serial, port)
            self._blood_monitors[name] = mon

            def on_status(dname, status, error):
                self.root.after(0, self._on_blood_status, dname, status, error)

            mon.start(on_status_change=on_status)
            label.config(text="启动中...", foreground=C_WARN)
            btn.config(text="...")

    def _on_blood_status(self, name, status, error):
        """血量监控状态回调（UI 线程）"""
        if name not in self._blood_widgets:
            return
        _, label, btn, _, _ = self._blood_widgets[name]

        if status == "running":
            label.config(text="已开启", foreground=C_OK)
            btn.config(text="关闭")
            self._log(f"[血量] {name} 血条已开启")
        elif status == "error":
            label.config(text=f"错误: {error[:20]}", foreground=C_ERROR)
            btn.config(text="开启")
            self._log(f"[血量] {name} 启动失败: {error}")
        elif status == "stopped":
            label.config(text="已关闭", foreground=C_DIM)
            btn.config(text="开启")

    # ── 任务启动方法 ──────────────────────────────

    def _start_worker(self, tab_key: str, dev: str, spec: dict):
        """先确保 OCR 服务就绪，再在独立子进程中启动任务并更新 UI"""
        w = self._tab_row_widgets.get(tab_key, {}).get(dev)
        if w:
            w["status"].set("OCR预热中...")
        self.root.after(0, self._log, f"[{dev}] 等待OCR服务就绪...")

        def _after_ocr():
            try:
                from core.ocr_client import warmup
                warmup()
            except Exception:
                pass
            self.root.after(0, self._launch_worker, tab_key, dev, spec)

        threading.Thread(target=_after_ocr, daemon=True).start()

    def _launch_worker(self, tab_key: str, dev: str, spec: dict):
        """真正启动任务子进程（此时 OCR 服务已就绪）"""
        if dev in self._workers:
            return
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
        self._update_tab_titles()

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
                marker = self._done_markers.get(tab_key)
                if marker and marker in line:
                    self.root.after(0, self._mark_task_done, tab_key)
                if "══ Phase " in line:
                    try:
                        n = int(line.split("══ Phase ")[1].split("/")[0])
                        self.root.after(0, self._set_dev_phase, tab_key, dev, n)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            self.root.after(0, self._on_worker_exit, dev, tab_key)

    def _set_dev_phase(self, tab_key: str, dev: str, phase: int):
        w = self._tab_row_widgets.get(tab_key, {}).get(dev)
        if w:
            total = {"dungeon100": 9, "dungeon90": 12, "tie1": 13, "tie2": 10, "tie3": 15, "tie4": 14}.get(tab_key, 9)
            w["status"].set(f"运行中 Phase {phase}/{total}")

    # ── 90副本 ─────────────────────────────────────

    def _on_start_dungeon90(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "dungeon90",
                "params": {"start_phase": self._dungeon90_start_phase(dev)}}
        self._start_worker("dungeon90", dev, spec)

    def _dungeon90_start_phase(self, dev):
        w = self._tab_row_widgets.get("dungeon90", {}).get(dev, {})
        val = w.get("start_var", tk.StringVar(value="自动续跑")).get()
        if val == "从头开始 (Phase 0)":
            return 0
        if val.startswith("Phase "):
            try:
                return int(val.split()[-1])
            except Exception:
                return None
        return None  # 自动续跑

    def _dungeon90_last_phase(self, dev):
        serial = self._device_serial.get(dev, "")
        safe = serial.replace(":", "_").replace("/", "_") if serial else "default"
        path = os.path.join(BASE_DIR, "logs", f"dungeon90_state_{safe}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("last_done_phase", -1))
        except Exception:
            return -1

    # ── 100副本 ─────────────────────────────────────

    def _on_start_dungeon100(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "dungeon100",
                "params": {"start_phase": self._dungeon100_start_phase(dev)}}
        self._start_worker("dungeon100", dev, spec)

    def _dungeon100_start_phase(self, dev):
        w = self._tab_row_widgets.get("dungeon100", {}).get(dev, {})
        val = w.get("start_var", tk.StringVar(value="自动续跑")).get()
        if val == "从头开始 (Phase 0)":
            return 0
        if val.startswith("Phase "):
            try:
                return int(val.split()[-1])
            except Exception:
                return None
        return None  # 自动续跑

    def _dungeon100_last_phase(self, dev):
        serial = self._device_serial.get(dev, "")
        safe = serial.replace(":", "_").replace("/", "_") if serial else "default"
        path = os.path.join(BASE_DIR, "logs", f"dungeon100_state_{safe}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("last_done_phase", -1))
        except Exception:
            return -1

    # ── 铁1副本 ─────────────────────────────────────

    def _on_start_tie1(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "tie1",
                "params": {"start_phase": self._tie1_start_phase(dev)}}
        self._start_worker("tie1", dev, spec)

    def _tie1_start_phase(self, dev):
        w = self._tab_row_widgets.get("tie1", {}).get(dev, {})
        val = w.get("start_var", tk.StringVar(value="自动续跑")).get()
        if val == "从头开始 (Phase 0)":
            return 0
        if val.startswith("Phase "):
            try:
                return int(val.split()[-1])
            except Exception:
                return None
        return None  # 自动续跑

    def _tie1_last_phase(self, dev):
        serial = self._device_serial.get(dev, "")
        safe = serial.replace(":", "_").replace("/", "_") if serial else "default"
        path = os.path.join(BASE_DIR, "logs", f"dungeon_tie1_state_{safe}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("last_done_phase", -1))
        except Exception:
            return -1

    # ── 铁2副本 ─────────────────────────────────────

    def _on_start_tie2(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "tie2",
                "params": {"start_phase": self._tie2_start_phase(dev)}}
        self._start_worker("tie2", dev, spec)

    def _tie2_start_phase(self, dev):
        w = self._tab_row_widgets.get("tie2", {}).get(dev, {})
        val = w.get("start_var", tk.StringVar(value="自动续跑")).get()
        if val == "从头开始 (Phase 0)":
            return 0
        if val.startswith("Phase "):
            try:
                return int(val.split()[-1])
            except Exception:
                return None
        return None  # 自动续跑

    def _tie2_last_phase(self, dev):
        serial = self._device_serial.get(dev, "")
        safe = serial.replace(":", "_").replace("/", "_") if serial else "default"
        path = os.path.join(BASE_DIR, "logs", f"dungeon_tie2_state_{safe}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("last_done_phase", -1))
        except Exception:
            return -1

    # ── 铁3副本 ─────────────────────────────────────

    def _on_start_tie3(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "tie3",
                "params": {"start_phase": self._tie3_start_phase(dev)}}
        self._start_worker("tie3", dev, spec)

    def _tie3_start_phase(self, dev):
        w = self._tab_row_widgets.get("tie3", {}).get(dev, {})
        val = w.get("start_var", tk.StringVar(value="自动续跑")).get()
        if val == "从头开始 (Phase 0)":
            return 0
        if val.startswith("Phase "):
            try:
                return int(val.split()[-1])
            except Exception:
                return None
        return None  # 自动续跑

    def _tie3_last_phase(self, dev):
        serial = self._device_serial.get(dev, "")
        safe = serial.replace(":", "_").replace("/", "_") if serial else "default"
        path = os.path.join(BASE_DIR, "logs", f"dungeon_tie3_state_{safe}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("last_done_phase", -1))
        except Exception:
            return -1

    # ── 铁4副本 ─────────────────────────────────────

    def _on_start_tie4(self, dev):
        if dev in self._workers:
            self._log(f"[{dev}] 已有任务在运行，跳过")
            return
        spec = {"task_type": "tie4",
                "params": {"start_phase": self._tie4_start_phase(dev)}}
        self._start_worker("tie4", dev, spec)

    def _tie4_start_phase(self, dev):
        w = self._tab_row_widgets.get("tie4", {}).get(dev, {})
        val = w.get("start_var", tk.StringVar(value="自动续跑")).get()
        if val == "从头开始 (Phase 0)":
            return 0
        if val.startswith("Phase "):
            try:
                return int(val.split()[-1])
            except Exception:
                return None
        return None  # 自动续跑

    def _tie4_last_phase(self, dev):
        serial = self._device_serial.get(dev, "")
        safe = serial.replace(":", "_").replace("/", "_") if serial else "default"
        path = os.path.join(BASE_DIR, "logs", f"dungeon_tie4_state_{safe}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("last_done_phase", -1))
        except Exception:
            return -1

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
        gaps = [self._crystal_gap1_var.get(), self._crystal_gap2_var.get(), self._crystal_gap3_var.get()]
        self._start_worker("crystal", dev, {"task_type": "crystal", "params": {"gaps": gaps}})

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
