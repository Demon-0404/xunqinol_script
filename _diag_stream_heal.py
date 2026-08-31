# -*- coding: utf-8 -*-
"""验证视频流自愈：启动 → 等首帧 → 杀设备端 scrcpy server → 观察 is_alive/get_frame 恢复"""
import sys, time, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, r"E:\DATA\xunqinol_script")

from core.screen_stream import get_stream

ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
SERIAL = "127.0.0.1:16416"


def adb(*args, timeout=8):
    return subprocess.run([ADB, "-s", SERIAL] + list(args),
                          capture_output=True, text=True, timeout=timeout)


def kill_device_server():
    r = adb("shell", "ps", "-A")
    killed = 0
    for line in r.stdout.splitlines():
        f = line.split()
        if len(f) >= 2 and ("app_process" in f[-1].lower() or "scrcpy" in f[-1].lower()):
            adb("shell", "kill", "-9", f[1], timeout=5)
            killed += 1
    return killed


print("=== 1. 启动流并等首帧 ===", flush=True)
st = get_stream(SERIAL)
t0 = time.time()
while time.time() - t0 < 20:
    frame, _ = st.get_frame()
    if frame is not None:
        print(f"[{time.strftime('%H:%M:%S')}] 首帧就绪 seq={st.get_frame_seq()} 尺寸={frame.shape}", flush=True)
        break
    time.sleep(0.3)
else:
    print("首帧超时，退出", flush=True)
    sys.exit(1)

print("=== 2. 杀设备端 server 模拟 MuMu SIGKILL ===", flush=True)
n = kill_device_server()
print(f"已杀 {n} 个进程", flush=True)

print("=== 3. 监控自愈（每0.5s） ===", flush=True)
for i in range(40):  # 20s
    s = get_stream(SERIAL)          # 触发自愈检查
    alive = s.is_alive()
    frame, _ = s.get_frame()
    print(f"[{time.strftime('%H:%M:%S')}] alive={alive} seq={s.get_frame_seq()} frame={'OK' if frame is not None else 'None'}", flush=True)
    if alive and frame is not None and s.get_frame_seq() > 2:
        print("=== 自愈成功，帧已恢复 ===", flush=True)
        break
    time.sleep(0.5)
else:
    print("=== 20s 内未恢复 ===", flush=True)
