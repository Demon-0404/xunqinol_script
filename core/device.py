"""多设备连接管理 —— 自动读取 MuMu 多开配置"""
import os
import json
import re
import subprocess
from airtest.core.api import connect_device, device as current_device, set_current


MUMU_ADB = "D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
MUMU_VMS_PATH = "D:/Setup_and_Downloads/Setup/MuMuPlayer/vms"

if os.path.exists(MUMU_ADB):
    os.environ["ANDROID_ADB"] = MUMU_ADB

_devices = {}  # name -> {"serial": ..., "index": ..., "connected": bool}


def _adb_path() -> str:
    return os.environ.get("ANDROID_ADB", "adb")


# ── MuMu 配置解析 ─────────────────────────────

def _parse_mumu_instances() -> list[dict]:
    """
    从 MuMu 配置目录读取所有多开实例。
    返回: [{"name": "天音", "index": 0, "dir": "..."}, ...]
    """
    instances = []
    if not os.path.isdir(MUMU_VMS_PATH):
        return instances

    for entry in os.listdir(MUMU_VMS_PATH):
        if not entry.startswith("MuMuPlayer-"):
            continue
        vm_dir = os.path.join(MUMU_VMS_PATH, entry)
        extra_cfg = os.path.join(vm_dir, "configs", "extra_config.json")
        if not os.path.exists(extra_cfg):
            continue

        try:
            with open(extra_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            name = cfg.get("playerName", entry)
            # 从目录名提取 index: MuMuPlayer-12.0-3 → 3
            match = re.search(r"-(\d+)$", entry)
            index = int(match.group(1)) if match else 0
            instances.append({"name": name, "index": index, "dir": vm_dir})
        except Exception:
            pass

    return sorted(instances, key=lambda x: x["index"])


def _mumu_port(index: int) -> str:
    """MuMu 12 端口映射: index 0→16384, index 1→16386, ..."""
    return f"127.0.0.1:{16384 + index * 2}"


def _try_connect(serial: str) -> bool:
    """尝试通过 ADB connect 某个地址"""
    try:
        out = subprocess.run(
            [_adb_path(), "connect", serial],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace"
        )
        return "connected" in out.stdout.lower() or "already" in out.stdout.lower()
    except Exception:
        return False


# ── 公开 API ──────────────────────────────────

def scan_available_devices() -> list[dict]:
    """
    扫描 MuMu 可连接的设备（自动从配置读取，不依赖用户手动输入端口）。
    返回: [{"name": "天音", "serial": "127.0.0.1:16384", "connected": True}, ...]
    """
    result = []
    instances = _parse_mumu_instances()

    # 先快速 ADB 扫描一次获取已连接列表
    online_serials = set()
    try:
        out = subprocess.run(
            [_adb_path(), "devices"], capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace"
        )
        for line in out.stdout.strip().split("\n")[1:]:
            if "\tdevice" in line:
                online_serials.add(line.split("\t")[0])
    except Exception:
        pass

    for inst in instances:
        port = _mumu_port(inst["index"])
        # 尝试连接
        if port not in online_serials:
            _try_connect(port)
        # 检查是否在线
        is_connected = port in online_serials
        result.append({
            "name": inst["name"], "serial": port, "connected": is_connected
        })

    # 如果没有从配置读到任何实例，回退：扫描常见端口
    if not result:
        for port in ["127.0.0.1:7555", "127.0.0.1:16384", "127.0.0.1:5555"]:
            if _try_connect(port):
                result.append({"name": f"设备{port}", "serial": port, "connected": True})
                break

    return result


def connect_device_by_serial(name: str, serial: str) -> bool:
    """连接指定序列号的设备"""
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


def switch_device(name: str) -> bool:
    """切换到指定设备"""
    if name not in _devices:
        print(f"设备 {name} 未连接")
        return False
    set_current(_devices[name]["index"])
    return True


def list_devices() -> dict:
    """返回所有已连接设备"""
    return {
        name: {"serial": d["serial"], "connected": d["connected"]}
        for name, d in _devices.items()
    }


def get_device_info(name: str = None) -> dict:
    """获取设备分辨率"""
    if name and name in _devices:
        switch_device(name)
    try:
        dev = current_device()
        w, h = dev.get_current_resolution()
        return {"width": w, "height": h, "connected": True}
    except Exception:
        return {"width": 0, "height": 0, "connected": False}


def init_all_devices() -> list[dict]:
    """
    启动时调用：扫描所有 MuMu 实例并自动连接。
    返回设备信息列表，供 UI 使用。
    """
    available = scan_available_devices()
    for dev in available:
        if dev["connected"] or _try_connect(dev["serial"]):
            connect_device_by_serial(dev["name"], dev["serial"])
    return available
