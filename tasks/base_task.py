"""任务基类 —— 所有自动化任务的父类"""
from abc import ABC, abstractmethod
import threading
import time


class BaseTask(ABC):
    """所有自动化任务的基类，提供统一的启动/停止/状态管理"""

    def __init__(self, name: str):
        self.name = name
        self._running = False
        self._thread = None
        self._on_log = None  # 回调函数，用于输出日志到 UI

    @property
    def running(self) -> bool:
        return self._running

    def set_log_callback(self, callback):
        """设置日志回调，用于将日志显示到 UI"""
        self._on_log = callback

    def log(self, msg: str):
        """输出日志"""
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line)
        if self._on_log:
            self._on_log(line)

    def start(self):
        """启动任务（在新线程中运行）"""
        if self._running:
            self.log(f"{self.name} 已在运行中")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_wrapper, daemon=True)
        self._thread.start()
        self.log(f"{self.name} 已启动")

    def stop(self):
        """停止任务"""
        self._running = False
        self.log(f"{self.name} 正在停止...")

    def _run_wrapper(self):
        """包装 run 方法，捕获异常"""
        try:
            self.run()
        except Exception as e:
            self.log(f"任务异常: {e}")
        finally:
            self._running = False
            self.log(f"{self.name} 已停止")

    @abstractmethod
    def run(self):
        """子类实现具体任务逻辑。通过检查 self._running 来决定是否继续循环。"""
        ...
