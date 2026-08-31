import subprocess, time, socket, struct, os, sys

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERVER_LOCAL = r"D:\Setup_and_Downloads\Setup\op\scrcpy-server"
FFMPEG = r"D:\Setup_and_Downloads\Setup\FormatFactory\ffmpeg.exe"
SERIAL = "127.0.0.1:16480"
PORT = 27185
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "_scrcpy_frame.png")

def adb(*args, timeout=10):
    return subprocess.run([ADB, "-s", SERIAL] + list(args),
                          capture_output=True, text=True, timeout=timeout)

def recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c:
            raise ConnectionError(f"eof at {len(buf)}/{n}")
        buf += c
    return buf

# 1. push + forward + start server
adb("push", SERVER_LOCAL, "/data/local/tmp/scrcpy-server.jar")
adb("forward", f"tcp:{PORT}", "localabstract:scrcpy")
server_cmd = ("CLASSPATH=/data/local/tmp/scrcpy-server.jar "
              "app_process / com.genymobile.scrcpy.Server 2.4 "
              "log_level=info max_size=540 max_fps=15 "
              "video_codec=h264 tunnel_forward=true control=false audio=false")
proc = subprocess.Popen([ADB, "-s", SERIAL, "shell", server_cmd],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)

time.sleep(2)
s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
s.settimeout(5)

# 2. protocol headers
dummy = recv_exact(s, 1)
name = recv_exact(s, 64).rstrip(b"\x00").decode(errors="replace")
codec_id, w, h = struct.unpack(">III", recv_exact(s, 12))
print(f"dummy={dummy.hex()} name='{name}' codec_id={codec_id:#x} {w}x{h}")

# 3. spawn ffmpeg decoder
dec = subprocess.Popen(
    [FFMPEG, "-hide_banner", "-loglevel", "error",
     "-f", "h264", "-i", "pipe:0",
     "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

frame_bytes = w * h * 3
print(f"frame size = {w*h*3} bytes, collecting packets...")

# 4. read video packets, feed h264 to ffmpeg, drain decoded frames in thread
import numpy as np
from PIL import Image
import threading

frame_bytes = w * h * 3
decoded_frames = []

def drain():
    try:
        while True:
            buf = b""
            while len(buf) < frame_bytes:
                c = dec.stdout.read(frame_bytes - len(buf))
                if not c:
                    return
                buf += c
            decoded_frames.append(np.frombuffer(buf, np.uint8).reshape(h, w, 3))
    except Exception:
        return

t = threading.Thread(target=drain, daemon=True)
t.start()

n_pkt = 0
t0 = time.time()
while time.time() - t0 < 2.5:
    hdr = recv_exact(s, 12)
    pts_flags, size = struct.unpack(">QI", hdr)
    payload = recv_exact(s, size)
    n_pkt += 1
    config = bool(pts_flags & (1 << 63))
    key = bool(pts_flags & (1 << 62))
    dec.stdin.write(payload)
    dec.stdin.flush()
    if n_pkt <= 3 or key:
        print(f"  pkt#{n_pkt} size={size} config={config} key={key}")

dec.stdin.close()
time.sleep(0.8)

print(f"total packets={n_pkt} decoded={len(decoded_frames)}")
if decoded_frames:
    Image.fromarray(decoded_frames[-1][:, :, ::-1]).save(OUT)
    print(f"saved {OUT}")

s.close()
proc.terminate()
time.sleep(0.5)
proc.kill()
print("=== done ===")
