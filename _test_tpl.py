"""临时: 让天音进一场战斗, 实测 templates/tianyuan 三个模板的匹配度"""
import time, os, subprocess, numpy as np, cv2
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16384"
TPL = os.path.join(BASE, "templates", "tianyuan")
TMP = os.path.join(BASE, "logs", "_tpl_test.png")

def tap(x, y):
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap", str(int(x)), str(int(y))],
                   capture_output=True, timeout=5)

def shot():
    with open(TMP, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=8)
    return np.array(Image.open(TMP).convert("RGB"))

round_t = cv2.imread(os.path.join(TPL, "round.png"))
manual_t = cv2.imread(os.path.join(TPL, "manual.png"))
auto_t = cv2.imread(os.path.join(TPL, "auto.png"))

def best(arr, tpl, cx, cy, spread):
    h, w = arr.shape[:2]
    y1, y2 = max(0, cy - spread), min(h, cy + spread)
    x1, x2 = max(0, cx - spread), min(w, cx + spread)
    if y2 - y1 < tpl.shape[0] or x2 - x1 < tpl.shape[1]:
        return 0.0
    roi = cv2.cvtColor(arr[y1:y2, x1:x2, :], cv2.COLOR_RGB2BGR)
    res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, _ = cv2.minMaxLoc(res)
    return mx

print("键0 开自动遇怪", flush=True)
tap(950, 1590)
time.sleep(0.5)

entered = False
for i in range(40):
    arr = shot()
    r = best(arr, round_t, 500, 200, 80)
    m = best(arr, manual_t, 1000, 1450, 80)
    a = best(arr, auto_t, 1000, 1450, 80)
    print(f"[{i:02d}] round={r:.2f} manual={m:.2f} auto={a:.2f}", flush=True)
    if r > 0.7 or m > 0.7 or a > 0.7:
        print(">>> 已进入战斗", flush=True)
        entered = True
        break
    time.sleep(0.5)

if entered:
    arr = shot()
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    for name, tpl in [("round", round_t), ("manual", manual_t), ("auto", auto_t)]:
        res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        cx = loc[0] + tpl.shape[1] // 2
        cy = loc[1] + tpl.shape[0] // 2
        print(f"全屏匹配 {name}: max={mx:.2f} @({cx},{cy})", flush=True)
    # 保存战斗截图供重录模板用
    subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                   stdout=open(os.path.join(BASE, "logs", "_tianyuan_battle.png"), "wb"),
                   stderr=subprocess.DEVNULL, timeout=8)
    print("已保存 logs/_tianyuan_battle.png", flush=True)
else:
    print(">>> 40s 内未进入战斗", flush=True)

print("键0 关自动遇怪", flush=True)
tap(950, 1590)
