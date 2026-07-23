"""设备连接管理"""
import subprocess
import re
from airtest.core.api import connect_device, device as current_device


# MuMu 模拟器常用 ADB 端口
MUMU_PORTS = {
    "MuMu 6": "127.0.0.1:7555",
    "MuMu 12": "127.0.0.1:16384",
    "MuMu 12 (备用)": "127.0.0.1:7555",
}


def list_adb_devices(adb_path: str = "adb") -> list[dict]:
    """列出所有 ADB 连接的设备"""
    try:
        result = subprocess.run(
            [adb_path, "devices"], capture_output=True, text=True, timeout=10
        )
        devices = []
        for line in result.stdout.strip().split("\n")[1:]:
            if "\tdevice" in line:
                serial = line.split("\t")[0]
                devices.append({"serial": serial, "status": "online"})
        return devices
    except Exception as e:
        return [{"serial": f"error: {e}", "status": "error"}]


def connect_mumu(port: str = "127.0.0.1:7555") -> bool:
    """连接 MuMu 模拟器"""
    try:
        uri = f"Android:///{port}"
        connect_device(uri)
        return True
    except Exception as e:
        print(f"连接失败: {e}")
        return False


def get_device_info() -> dict:
    """获取当前设备信息"""
    try:
        dev = current_device()
        return {
            "screen_size": dev.display_info.get("physical_size", "unknown"),
            "connected": True,
        }
    except Exception:
        return {"screen_size": "unknown", "connected": False}
