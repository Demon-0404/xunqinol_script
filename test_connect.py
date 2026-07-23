"""快速测试：连接 MuMu 模拟器 + 截图"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.device import connect_mumu, get_device_info, MUMU_PORT

print(f"ADB 路径: {os.environ.get('ANDROID_ADB', '未设置')}")
print(f"连接地址: {MUMU_PORT}")
print(f"正在连接...")

ok = connect_mumu()
if ok:
    print("连接成功!")
    info = get_device_info()
    print(f"屏幕分辨率: {info['screen_size']}")

    # 截一张图
    from airtest.core.api import snapshot
    path = snapshot(filename="logs/test_screenshot.png")
    print(f"截图已保存: {path}")
else:
    print("连接失败!")
