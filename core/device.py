"""多设备连接管理"""
import os
import subprocess
from airtest.core.api import connect_device, device as current_device, set_current


MUMU_ADB = "D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
if os.path.exists(MUMU_ADB):
    os.environ["ANDROID_ADB"] = MUMU_ADB

# 预设设备（可手动添加）
PRESET_DEVICES = [
    {"name": "默认设备", "serial": "127.0.0.1:7555"},
    {"name": "天音",     "serial": "127.0.0.1:7557"},
]

_devices = {}   # name -> {"serial": ..., "index": ..., "connected": bool}


def scan_adb_devices() -> list[str]:
    """扫描 ADB 发现的所有设备"""
    try:
        out = subprocess.run(
            [os.environ.get("ANDROID_ADB", "adb"), "devices"],
            capture_output=True, text=True, timeout=10
        )
        devices = []
        for line in out.stdout.strip().split("\n")[1:]:
            if "\tdevice" in line:
                devices.append(line.split("\t")[0])
        return devices
    except Exception:
        return []


def connect_device_by_serial(name: str, serial: str) -> bool:
    """连接指定 ADB 序列号的设备，并给一个名称"""
    try:
        uri = f"Android:///{serial}"
        dev = connect_device(uri)
        index = len(_devices)
        _devices[name] = {"serial": serial, "index": index, "connected": True}
        return True
    except Exception as e:
        _devices[name] = {"serial": serial, "index": -1, "connected": False}
        print(f"连接 {name} ({serial}) 失败: {e}")
        return False


def disconnect_device(name: str):
    """断开指定设备"""
    if name in _devices:
        del _devices[name]


def switch_device(name: str) -> bool:
    """切换到指定设备（后续所有 touch/swipe/snapshot 操作针对此设备）"""
    if name not in _devices:
        print(f"设备 {name} 未连接")
        return False
    set_current(_devices[name]["index"])
    return True


def list_devices() -> dict:
    """返回所有已连接设备的信息"""
    return {
        name: {"serial": d["serial"], "connected": d["connected"]}
        for name, d in _devices.items()
    }


def get_current_device_name() -> str:
    """返回当前活跃设备名"""
    if not _devices:
        return ""
    idx = current_device()._instance_id if hasattr(current_device(), '_instance_id') else 0
    for name, d in _devices.items():
        if d["index"] == idx:
            return name
    return list(_devices.keys())[0] if _devices else ""


def get_device_info(name: str = None) -> dict:
    """获取指定设备信息"""
    if name and name in _devices:
        switch_device(name)
    try:
        dev = current_device()
        w, h = dev.get_current_resolution()
        return {"width": w, "height": h, "connected": True}
    except Exception:
        return {"width": 0, "height": 0, "connected": False}


def init_default_devices():
    """初始化预设设备列表（扫描 + 预设）"""
    found = scan_adb_devices()
    for preset in PRESET_DEVICES:
        if preset["serial"] in found:
            connect_device_by_serial(preset["name"], preset["serial"])
    # 如果预设都没连上，尝试连找到的第一个
    if not _devices and found:
        connect_device_by_serial("设备1", found[0])
