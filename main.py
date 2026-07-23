"""寻秦OL 自动化助手 - 主程序"""
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from core.device import connect_mumu, get_device_info, MUMU_PORT
from tasks.walk_demo import WalkDemo


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("寻秦OL 自动化助手")
        self.root.geometry("620x580")
        self.root.resizable(True, True)

        self._connected = False
        self._current_task = None

        self._build_ui()
        self._update_status_timer()

    # ── UI 构建 ─────────────────────────────────────

    def _build_ui(self):
        # 顶部：设备连接
        device_frame = ttk.LabelFrame(self.root, text="设备连接", padding=8)
        device_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(device_frame, text="MuMu 地址:").pack(side=tk.LEFT)
        self._addr_var = tk.StringVar(value=MUMU_PORT)
        addr_combo = ttk.Combobox(device_frame, textvariable=self._addr_var,
                                  values=[MUMU_PORT, "127.0.0.1:16384"], width=18)
        addr_combo.pack(side=tk.LEFT, padx=4)

        self._connect_btn = ttk.Button(device_frame, text="先点这里连接", command=self._on_connect)
        self._connect_btn.pack(side=tk.LEFT, padx=4)

        self._status_label = ttk.Label(device_frame, text="未连接", foreground="gray")
        self._status_label.pack(side=tk.LEFT, padx=8)

        self._info_label = ttk.Label(device_frame, text="")
        self._info_label.pack(side=tk.RIGHT)

        # 主体内容区域
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # 左侧：操作区
        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── 走路 Demo 区域
        walk_frame = ttk.LabelFrame(left, text="走路 Demo", padding=8)
        walk_frame.pack(fill=tk.X, pady=(0, 4))

        # 模式切换
        mode_frame = ttk.Frame(walk_frame)
        mode_frame.pack(fill=tk.X, pady=2)
        ttk.Label(mode_frame, text="模式:").pack(side=tk.LEFT)
        self._mode_var = tk.StringVar(value="tap")
        ttk.Radiobutton(mode_frame, text="点击地面", variable=self._mode_var,
                        value="tap").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(mode_frame, text="摇杆", variable=self._mode_var,
                        value="joystick").pack(side=tk.LEFT, padx=4)

        # 方向选择
        dir_frame = ttk.Frame(walk_frame)
        dir_frame.pack(fill=tk.X, pady=2)
        ttk.Label(dir_frame, text="方向:").pack(side=tk.LEFT)
        self._dir_var = tk.StringVar(value="right")
        for d in ["上", "下", "左", "右"]:
            ttk.Radiobutton(dir_frame, text=d, variable=self._dir_var,
                            value={"上": "up", "下": "down", "左": "left", "右": "right"}[d]
                            ).pack(side=tk.LEFT, padx=2)

        # 步数
        step_frame = ttk.Frame(walk_frame)
        step_frame.pack(fill=tk.X, pady=2)
        ttk.Label(step_frame, text="步数:").pack(side=tk.LEFT)
        self._steps_var = tk.IntVar(value=3)
        ttk.Spinbox(step_frame, from_=1, to=50, textvariable=self._steps_var,
                    width=5).pack(side=tk.LEFT, padx=4)

        # 点击坐标（屏幕中心点）
        tap_frame = ttk.Frame(walk_frame)
        tap_frame.pack(fill=tk.X, pady=2)
        ttk.Label(tap_frame, text="点击 X:").pack(side=tk.LEFT)
        self._tap_x_var = tk.IntVar(value=540)
        ttk.Entry(tap_frame, textvariable=self._tap_x_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(tap_frame, text="  Y:").pack(side=tk.LEFT)
        self._tap_y_var = tk.IntVar(value=800)
        ttk.Entry(tap_frame, textvariable=self._tap_y_var, width=6).pack(side=tk.LEFT, padx=2)

        ttk.Label(tap_frame, text="  偏移:", foreground="gray").pack(side=tk.LEFT)
        self._spread_var = tk.IntVar(value=350)
        ttk.Entry(tap_frame, textvariable=self._spread_var, width=5).pack(side=tk.LEFT, padx=2)

        # 按钮
        btn_frame = ttk.Frame(walk_frame)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        self._walk_start_btn = ttk.Button(btn_frame, text="开始走路", command=self._on_start_walk)
        self._walk_start_btn.pack(side=tk.LEFT, padx=2)
        self._walk_stop_btn = ttk.Button(btn_frame, text="停止", command=self._on_stop_walk,
                                         state=tk.DISABLED)
        self._walk_stop_btn.pack(side=tk.LEFT, padx=2)
        self._screenshot_btn = ttk.Button(btn_frame, text="截一张图", command=self._on_screenshot)
        self._screenshot_btn.pack(side=tk.RIGHT, padx=2)

        # ── 右侧：日志
        right = ttk.Frame(body)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))

        log_frame = ttk.LabelFrame(right, text="运行日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self._log_area = scrolledtext.ScrolledText(log_frame, width=36, height=20,
                                                   state=tk.DISABLED, wrap=tk.WORD)
        self._log_area.pack(fill=tk.BOTH, expand=True)

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
            self._info_label.config(text=f"分辨率: {info['width']}x{info['height']}")
            self._log(f"连接成功 (分辨率 {info['width']}x{info['height']})")
        else:
            self._status_label.config(text="连接失败", foreground="red")
            self._log("连接失败，请检查模拟器是否开启")

    def _update_status_timer(self):
        try:
            info = get_device_info()
            if info["connected"]:
                self._connected = True
                self._info_label.config(text=f"分辨率: {info['width']}x{info['height']}")
            else:
                self._connected = False
        except Exception:
            self._connected = False
        self.root.after(5000, self._update_status_timer)

    # ── 走路 Demo ─────────────────────────────────

    def _on_start_walk(self):
        if not self._connected:
            self._log("错误：请先点击「连接」按钮连接模拟器!")
            return

        direction = self._dir_var.get()
        steps = self._steps_var.get()
        use_joystick = self._mode_var.get() == "joystick"
        tap_x = self._tap_x_var.get()
        tap_y = self._tap_y_var.get()
        spread = self._spread_var.get()

        self._current_task = WalkDemo(
            direction=direction, steps=steps,
            use_joystick=use_joystick,
            tap_x=tap_x, tap_y=tap_y, spread=spread)
        self._current_task.set_log_callback(lambda msg: self.root.after(0, self._log, msg))
        self._current_task.start()

        self._walk_start_btn.config(state=tk.DISABLED)
        self._walk_stop_btn.config(state=tk.NORMAL)

    def _on_stop_walk(self):
        if self._current_task:
            self._current_task.stop()
        self._walk_start_btn.config(state=tk.NORMAL)
        self._walk_stop_btn.config(state=tk.DISABLED)

    def _on_screenshot(self):
        if not self._connected:
            self._log("错误：请先点击「连接」按钮连接模拟器!")
            return

        from core.actions import screenshot
        import time
        name = f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(BASE_DIR, "logs", name)
        screenshot(path)
        self._log(f"截图已保存: {path}")

    # ── 日志 ─────────────────────────────────────

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
