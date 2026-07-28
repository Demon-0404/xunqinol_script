# -*- coding: utf-8 -*-
"""Frida 血条监控 —— 每设备一个独立线程"""
import subprocess
import threading
import time
import frida

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"

FRIDA_BASE_PORT = 27042  # 遁甲用这个，其他设备递增

JS_CODE = """
'use strict';
var base = null;
function findBase() {
    Process.enumerateRanges('r--').forEach(function(r) {
        if (r.file && r.file.path && r.file.path.indexOf('libtestcpp.so') !== -1) {
            if (base === null || r.base.compare(base) < 0) base = r.base;
        }
    });
}
function fixBlood() {
    if (base === null) { findBase(); if (!base) return; }
    try {
        var got1 = base.add(0x00459e3c);
        var obj1 = ptr(ptr(got1).readPointer()).readPointer();
        var blood1 = obj1.add(0x1c7);
        if (ptr(blood1).readU8() === 0) ptr(blood1).writeU8(1);

        var got2 = base.add(0x0045be3c);
        var addr2 = ptr(got2).readPointer();
        var obj2 = ptr(addr2).readPointer();
        if (!obj2.isNull()) {
            var blood2 = obj2.add(0x1c7);
            if (ptr(blood2).readU8() === 0) ptr(blood2).writeU8(1);
        } else {
            ptr(addr2).writePointer(obj1);
        }
    } catch(e) { base = null; }
}
setInterval(fixBlood, 500);
"""


def _get_game_pid(adb_serial: str) -> int | None:
    """查找指定设备上的游戏进程 PID"""
    r = subprocess.run(
        [ADB, "-s", adb_serial, "shell", "ps", "-A"],
        capture_output=True, text=True, timeout=15
    )
    for line in r.stdout.split("\n"):
        if "proj.xqj" in line and "grep" not in line:
            parts = line.split()
            if len(parts) >= 2:
                return int(parts[1])
    return None


def _ensure_frida_port(adb_serial: str, host_port: int) -> bool:
    """设置 ADB 端口转发 host_port -> guest:27042"""
    subprocess.run(
        [ADB, "-s", adb_serial, "forward", f"tcp:{host_port}", "tcp:27042"],
        capture_output=True, timeout=10
    )
    return True


class BloodMonitor:
    """单个设备的血条监控"""

    def __init__(self, name: str, adb_serial: str, frida_port: int):
        self.name = name
        self.adb_serial = adb_serial
        self.frida_port = frida_port
        self._running = False
        self._thread = None
        self._status = "stopped"  # stopped | running | error
        self._error_msg = ""

    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> str:
        return self._error_msg

    def start(self, on_status_change=None):
        """启动血条监控"""
        if self._running:
            return
        self._running = True
        self._status = "starting"
        self._thread = threading.Thread(
            target=self._run, args=(on_status_change,), daemon=True
        )
        self._thread.start()

    def stop(self):
        """停止血条监控（不阻塞，让 daemon 线程自行清理）"""
        self._running = False
        self._status = "stopped"

    def _update_status(self, status: str, error: str = "",
                       callback=None):
        self._status = status
        self._error_msg = error
        if callback:
            callback(self.name, status, error)

    def _run(self, on_status_change=None):
        update = lambda s, e="": self._update_status(s, e, on_status_change)

        # 1. 找游戏 PID
        pid = _get_game_pid(self.adb_serial)
        if not pid:
            update("error", "游戏未运行")
            return

        # 2. 端口转发
        _ensure_frida_port(self.adb_serial, self.frida_port)

        # 3. 连接 Frida
        try:
            device = frida.get_device_manager().add_remote_device(
                f"127.0.0.1:{self.frida_port}"
            )
            session = device.attach(pid)
            script = session.create_script(JS_CODE)
            script.load()
            update("running")
        except Exception as e:
            update("error", f"Frida连接失败: {e}")
            return

        # 4. 保持监控
        while self._running:
            try:
                # Frida session 保持活跃
                time.sleep(1)
            except Exception:
                break

        # 清理：先把 blood flag 写回 0，再断开
        try:
            cleanup = session.create_script("""
                'use strict';
                var base = null;
                Process.enumerateRanges('r--').forEach(function(r) {
                    if (r.file && r.file.path && r.file.path.indexOf('libtestcpp.so') !== -1) {
                        if (base === null || r.base.compare(base) < 0) base = r.base;
                    }
                });
                if (base) {
                    var got1 = base.add(0x00459e3c);
                    var obj1 = ptr(ptr(got1).readPointer()).readPointer();
                    ptr(obj1.add(0x1c7)).writeU8(0);
                    var got2 = base.add(0x0045be3c);
                    var obj2 = ptr(ptr(got2).readPointer()).readPointer();
                    if (!obj2.isNull()) ptr(obj2.add(0x1c7)).writeU8(0);
                }
            """)
            cleanup.load()
        except Exception:
            pass
        try:
            session.detach()
        except Exception:
            pass
        update("stopped")
