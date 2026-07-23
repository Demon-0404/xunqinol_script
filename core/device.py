"""设备连接管理"""
import os
from airtest.core.api import connect_device, device as current_device, G


# ── MuMu 模拟器配置 ─────────────────────────
MUMU_ADB = "D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
MUMU_PORT = "127.0.0.1:7555"

if os.path.exists(MUMU_ADB):
    os.environ["ANDROID_ADB"] = MUMU_ADB


def connect_mumu(port: str = None) -> bool:
    """连接 MuMu 模拟器"""
    if port is None:
        port = MUMU_PORT
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
        w, h = dev.get_current_resolution()
        return {
            "width": w,
            "height": h,
            "connected": True,
        }
    except Exception:
        return {"width": 0, "height": 0, "connected": False}
