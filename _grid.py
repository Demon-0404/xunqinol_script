import subprocess, io, os
from PIL import Image, ImageDraw, ImageFont

ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
serial = "127.0.0.1:16416"  # 琴魔-虚无缥缈

r = subprocess.run([ADB, "-s", serial, "exec-out", "screencap", "-p"],
                   capture_output=True, timeout=10)
img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
W, H = img.size
print("size:", W, H)

overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)

step = 100
for x in range(0, W + 1, step):
    od.line([(x, 0), (x, H)], fill=(0, 255, 255, 110), width=1)
for y in range(0, H + 1, step):
    od.line([(0, y), (W, y)], fill=(0, 255, 255, 110), width=1)

try:
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 22)
except Exception:
    font = ImageFont.load_default()

# 顶部标 x，左侧标 y（加黑底条提高可读性）
od.rectangle([0, 0, W, 30], fill=(0, 0, 0, 180))
od.rectangle([0, 0, 58, H], fill=(0, 0, 0, 180))
for x in range(0, W + 1, step):
    od.text((x + 3, 4), str(x), fill=(255, 255, 0, 255), font=font)
for y in range(0, H + 1, step):
    od.text((3, y + 4), str(y), fill=(255, 255, 0, 255), font=font)

img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
out = r"E:\DATA\xunqinol_script\logs\_grid.png"
img.save(out)
print("saved:", out)

try:
    os.startfile(out)
    print("opened via os.startfile")
except Exception as e:
    print("startfile failed:", e)
