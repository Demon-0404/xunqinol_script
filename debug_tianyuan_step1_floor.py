"""天渊一层→二层 楼层切换调试：左下角3次 + 右下角3次，期间检测地图名变化"""
import time
import sys
import os

import debug_tianyuan_step1 as d

LEFT_BOTTOM = (100, 1100)      # 左下角(沿用旧 MOVE_LEFT)
RIGHT_BOTTOM = (1000, 1100)    # 右下角(沿用旧 MOVE_RIGHT)
WAIT_STEP = 3.0                # 走路/传送门每步间隔
PORTAL_DONE_WAIT = 10.0        # 点满后等待传送动画
MAP_NAME_POS = (950, 110)      # 地图名位置(右上角)
MAP_NAME_RANGE = 80


def check_map_name():
    arr = d.screenshot()
    if arr is None:
        return ""
    h, w = arr.shape[:2]
    y1, y2 = max(0, 20), min(h, 190)
    x1, x2 = max(0, 780), min(w, 1080)
    try:
        rs = d.ocr(arr[y1:y2, x1:x2, :], mag_ratio=2)
    except Exception:
        return ""
    for r in rs:
        if r[2] >= 0.3 and "天渊" in r[1]:
            return r[1]
    return ""


def is_floor2(text):
    return "天渊" in text and "二" in text


def navigate():
    # 连续轮询检测(参考100副本 _portal_seq_phase)：点击和检测解耦，每0.3s查一次地图名，一变即停
    before = ""
    for _ in range(3):
        before = check_map_name()
        if before:
            break
        time.sleep(1.0)
    print(f"  当前地图: '{before}'", flush=True)

    click_seq = [
        (LEFT_BOTTOM, "左下角"),
        (LEFT_BOTTOM, "左下角"),
        (LEFT_BOTTOM, "左下角"),
        (RIGHT_BOTTOM, "右下角"),
        (RIGHT_BOTTOM, "右下角"),
        (RIGHT_BOTTOM, "右下角"),
    ]
    clicks = 0
    last_click = -1e9
    done_deadline = None
    while True:
        cur = check_map_name()
        if before and cur and cur != before:
            print(f"  地图变化: '{before}' → '{cur}'", flush=True)
            return
        if cur and is_floor2(cur):
            print(f"  到达: '{cur}'", flush=True)
            return

        if clicks < len(click_seq) and time.time() - last_click >= WAIT_STEP:
            pos, name = click_seq[clicks]
            d.tap(pos, f"{name}第{clicks + 1}次")
            clicks += 1
            last_click = time.time()
            if clicks >= len(click_seq):
                done_deadline = time.time() + PORTAL_DONE_WAIT
                print(f"  点满{len(click_seq)}次，继续等传送动画{PORTAL_DONE_WAIT}s...", flush=True)

        if done_deadline and time.time() > done_deadline:
            print("  等待传送动画超时", flush=True)
            return

        time.sleep(0.3)


if __name__ == "__main__":
    navigate()
