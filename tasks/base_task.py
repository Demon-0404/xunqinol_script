"""任务基类 —— 所有自动化任务的父类"""
from abc import ABC, abstractmethod
import threading
import time

# ── 公共坐标 (1080x1920) ────────────────────
STAR_KEY = (150, 1790)   # *号键 → 一键领取/提交


class BaseTask(ABC):
    """所有自动化任务的基类，提供统一的启动/停止/状态管理"""

    KEY5 = (150, 1590)    # 数字键5 → 确认/对话
    _touch_lock = threading.Lock()  # 多设备并发触摸锁

    def __init__(self, name: str, device_name: str = ""):
        self.name = name
        self.device_name = device_name  # 所属设备名
        self._running = False
        self._thread = None
        self._on_log = None  # 回调函数，用于输出日志到 UI
        self._on_finish = None  # 任务结束回调（自然结束/异常）
        self._log_path_cache = None  # 后台日志文件路径缓存

    @property
    def running(self) -> bool:
        return self._running

    def set_log_callback(self, callback):
        """设置日志回调，用于将日志显示到 UI"""
        self._on_log = callback

    def set_finish_callback(self, callback):
        """设置任务结束回调"""
        self._on_finish = callback

    def _format_log(self, msg: str) -> str:
        timestamp = time.strftime("%H:%M:%S")
        prefix = f"[{self.device_name}] " if self.device_name else ""
        return f"[{timestamp}] {prefix}{msg}"

    def _log_path(self) -> str:
        """每个任务每次运行一个独立的后台日志文件"""
        if self._log_path_cache is None:
            import os
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            d = os.path.join(base, "logs")
            os.makedirs(d, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            name = (self.name or "task").replace(" ", "")
            dev = (self.device_name or "dev").replace(" ", "")
            self._log_path_cache = os.path.join(d, f"{name}_{dev}_{ts}.log")
        return self._log_path_cache

    def _write_log_file(self, line: str):
        try:
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def log(self, msg: str):
        """详细日志 —— 只写后台文件，不上屏（避免刷屏卡 UI）"""
        line = self._format_log(msg)
        self._write_log_file(line)
        if self._on_log:
            self._on_log(line)

    def log_key(self, msg: str):
        """关键步骤 —— 写后台文件 + 上屏(stdout 供 UI 显示)"""
        line = self._format_log(msg)
        self._write_log_file(line)
        try:
            print(line, flush=True)
        except Exception:
            pass
        if self._on_log:
            self._on_log(line)

    def start(self):
        """启动任务（在新线程中运行）"""
        if self._running:
            self.log_key(f"{self.name} 已在运行中")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_wrapper, daemon=True)
        self._thread.start()
        self.log_key(f"{self.name} 已启动")

    def stop(self):
        """停止任务"""
        self._running = False
        self.log_key(f"{self.name} 正在停止...")

    def _switch_self(self):
        """切换到本任务所属设备（airtest 全局设备是唯一的，操作前必须切换）"""
        if self.device_name:
            from core.device import switch_device
            switch_device(self.device_name)

    def _safe_touch(self, pos: tuple):
        """触摸操作 —— 直接用 adb input tap，避免 airtest maxtouch 跨进程端口冲突/设备离线"""
        import os
        import subprocess
        serial = ""
        if self.device_name:
            from core.device import get_device_serial
            serial = get_device_serial(self.device_name)
        adb = os.environ.get("ANDROID_ADB", "adb")
        args = [adb]
        if serial:
            args += ["-s", serial]
        args += ["shell", "input", "tap", str(int(pos[0])), str(int(pos[1]))]
        subprocess.run(args, capture_output=True, timeout=5)

    def _safe_snapshot(self):
        """线程安全的截图操作 —— 返回当前设备截图"""
        from airtest.core.api import snapshot
        with BaseTask._touch_lock:
            self._switch_self()
            return snapshot()

    def _safe_exists(self, tmpl):
        """线程安全的模板匹配 —— 返回 (pos, score) 或 False"""
        from airtest.core.api import exists
        with BaseTask._touch_lock:
            self._switch_self()
            return exists(tmpl)

    def _safe_keyevent(self, keyname):
        """线程安全的按键操作"""
        from airtest.core.api import keyevent
        with BaseTask._touch_lock:
            self._switch_self()
            keyevent(keyname)

    def _run_wrapper(self):
        """包装 run 方法，捕获异常"""
        try:
            self.run()
        except Exception as e:
            import traceback, os
            tb = traceback.format_exc()
            # 先写错误文件（stdout 可能已损坏，必须保证 traceback 落盘）
            try:
                log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
                os.makedirs(log_dir, exist_ok=True)
                dev = (self.device_name or "dev").replace(" ", "")
                with open(os.path.join(log_dir, f"_task_error_{dev}.txt"), "w", encoding="utf-8") as f:
                    f.write(tb)
            except Exception:
                pass
            self.log_key("任务异常: " + str(e))
            for line in tb.split("\n"):
                if line.strip():
                    self.log("  " + line.strip())
        finally:
            self._running = False
            self.log_key(self.name + " 已停止")
            if self._on_finish:
                try:
                    self._on_finish()
                except Exception:
                    pass

    # ── 任务交互模板 ──────────────────────────

    def _quest_accept(self):
        """接取任务: 5→5→*  然后等1s"""
        self.log("  接取: 5→5→*...")
        self._safe_touch(self.KEY5)
        time.sleep(0.8)
        self._safe_touch(self.KEY5)
        time.sleep(0.8)
        self._safe_touch(STAR_KEY)
        time.sleep(1.0)
        self.log("  接取完成")

    def _quest_submit(self):
        """提交任务: 5→5→* → 等3s结算消失"""
        self.log("  提交: 5→5→*...")
        self._safe_touch(self.KEY5)
        time.sleep(0.8)
        self._safe_touch(self.KEY5)
        time.sleep(0.8)
        self._safe_touch(STAR_KEY)
        self.log("  提交完成，等待3s...")
        time.sleep(3.0)

    @abstractmethod
    def run(self):
        """子类实现具体任务逻辑。通过检查 self._running 来决定是否继续循环。"""
        ...
