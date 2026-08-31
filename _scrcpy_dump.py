import subprocess, time, socket

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERVER_LOCAL = r"D:\Setup_and_Downloads\Setup\op\scrcpy-server"
SERIAL = "127.0.0.1:16480"
PORT = 27184

def adb(*args, timeout=10):
    return subprocess.run([ADB, "-s", SERIAL] + list(args),
                          capture_output=True, text=True, timeout=timeout)

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
s.settimeout(3)

# dump 前 128 字节
data = b""
try:
    while len(data) < 128:
        chunk = s.recv(128 - len(data))
        if not chunk:
            break
        data += chunk
except Exception as e:
    print("recv err:", e)

print(f"got {len(data)} bytes")
for i in range(0, len(data), 16):
    chunk = data[i:i+16]
    hexs = " ".join(f"{b:02x}" for b in chunk)
    ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(f"{i:04x}  {hexs:<48}  {ascii_}")

s.close()
proc.terminate()
proc.kill()
