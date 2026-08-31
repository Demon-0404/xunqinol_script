"""临时: 持续观察天音, 等真正进入战斗, 抓右下角 y≈1450 按钮"""
import time, os, subprocess, sys, numpy as np, cv2
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16384"
TMP = os.path.join(BASE, "logs", "_watch_tmp.png")
sys.path.insert(0, BASE)
from core.ocr_client import get_ocr_client

def tap(x, y):
    subprocess.run([ADB, "-s", SERIAL, "shell", "input", "tap", str(int(x)), str(int(y))],
                   capture_output=True, timeout=5)

def shot():
    with open(TMP, "wb") as f:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=8)
    return np.array(Image.open(TMP).convert("RGB"))

reader = None
def get_reader():
    global reader
    if reader is None:
        reader = get_ocr_client()
    return reader

def corner_btn(arr):
    """OCR 右下角 y[1350,1550] x[830,1080] 区域, 返回按钮文字"""
    crop = arr[1350:1550, 830:1080, :]
    txts = []
    for x in get_reader().readtext(crop):
        if x[2] >= 0.3:
            txts.append((x[1], x[2]))
    return txts

print("观察中(角色自动遇怪)...", flush=True)
for i in range(80):
    arr = shot()
    btns = corner_btn(arr)
    # 战斗界面判定: 右下角出现'手动'或'自动'按钮, 且非确认弹窗
    hit = [b for b in btns if b[0] in ("手动", "自动") or "手动" in b[0] or "自动" in b[0]]
    if hit:
        print(f"[{i:02d}] 进入战斗! 右下角按钮: {hit}", flush=True)
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                       stdout=open(os.path.join(BASE, "logs", "_auto_battle.png"), "wb"),
                       stderr=subprocess.DEVNULL, timeout=8)
        print("已保存 logs/_auto_battle.png", flush=True)
        print("--- 全屏OCR ---", flush=True)
        for x in get_reader().readtext(arr):
            if x[2] >= 0.1:
                bbox = x[0]
                cx = int(sum(p[0] for p in bbox)/4); cy = int(sum(p[1] for p in bbox)/4)
                print(f"  {x[2]:.2f} ({cx},{cy}) {x[1]}", flush=True)
        break
    else:
        print(f"[{i:02d}] 右下角: {btns}", flush=True)
    time.sleep(0.5)
