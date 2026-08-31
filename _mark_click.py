import subprocess, io
from PIL import Image, ImageDraw

ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
serial = "127.0.0.1:16416"  # 琴魔-虚无缥缈

r = subprocess.run([ADB, "-s", serial, "exec-out", "screencap", "-p"],
                   capture_output=True, timeout=10)
img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
W, H = img.size
print("size:", W, H)
draw = ImageDraw.Draw(img)

marks = [
    (150, 1590, "KEY5 (5, x2)"),
    (150, 1790, "* 号键"),
]
R = 45
for x, y, label in marks:
    draw.line([(x - 80, y), (x + 80, y)], fill=(255, 0, 0), width=7)
    draw.line([(x, y - 80), (x, y + 80)], fill=(255, 0, 0), width=7)
    draw.ellipse([x - R, y - R, x + R, y + R], outline=(255, 0, 0), width=7)
    # 标签底框 + 文字
    tw = len(label) * 22
    bx0, by0, bx1, by1 = x + 70, y - 70, x + 70 + tw + 20, y - 10
    if bx1 > W:
        bx0, bx1 = x - 70 - tw - 20, x - 70
    draw.rectangle([bx0, by0, bx1, by1], fill=(255, 0, 0))
    draw.text((bx0 + 10, by0 + 8), label, fill=(255, 255, 255))

out = r"E:\DATA\xunqinol_script\logs\_click_mark.png"
img.save(out)
print("saved:", out)
