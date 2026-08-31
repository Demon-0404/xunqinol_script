# -*- coding: utf-8 -*-
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


def server_line():
    r = adb("shell", "ps", "-A")
    for line in r.stdout.splitlines():
        if "genymobile" in line or "scrcpy" in line:
            return line.strip()
    return None


st = get_stream(SERIAL)
print("=== 停止旧流 ===", flush=True)
st.stop()

print("=== 启动新流 ===", flush=True)
st.start()
print("start 完成, alive=%s frame_seq=%s" % (st.is_alive(), st.get_frame_seq()), flush=True)

print("=== 监控 60s（每秒：流状态 / 帧 / server进程 / 关键dmesg） ===", flush=True)
last_sig9 = ""
for i in range(60):
    frame, ts = st.get_frame()
    srv = server_line()
    frame_ok = "OK" if frame is not None else "None"
    print("[%s] alive=%s frame=%s server=%s" % (
        time.strftime("%H:%M:%S"), st.is_alive(), frame_ok, "有" if srv else "无"), flush=True)
    if srv is None and st._alive:
        print(">>> server 进程已死但流仍 alive（zombie），抓 dmesg signal 9 <<<", flush=True)
        r = adb("shell", "dmesg")
        for line in r.stdout.splitlines():
            if "signal 9" in line or "Untracked" in line or "SIGKILL" in line:
                print("  dmesg:", line.strip(), flush=True)
        break
    time.sleep(1.0)

print("=== 最终 server 进程 ===", flush=True)
print(server_line() or "（无）", flush=True)
