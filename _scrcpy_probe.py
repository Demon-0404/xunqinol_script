import subprocess, time, os, socket, struct

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERVER_LOCAL = r"D:\Setup_and_Downloads\Setup\op\scrcpy-server"
SERIAL = "127.0.0.1:16480"
PORT = 27183

def adb(*args, timeout=10):
    return subprocess.run([ADB, "-s", SERIAL] + list(args),
                          capture_output=True, text=True, timeout=timeout)

# 1. push server
print("=== push server ===")
r = adb("push", SERVER_LOCAL, "/data/local/tmp/scrcpy-server.jar")
print("push:", r.stdout.strip(), r.stderr.strip())

# 2. forward
print("=== forward ===")
r = adb("forward", f"tcp:{PORT}", "localabstract:scrcpy")
print("forward:", r.stdout.strip(), r.stderr.strip())

# 3. start server (background)
server_cmd = ("CLASSPATH=/data/local/tmp/scrcpy-server.jar "
              "app_process / com.genymobile.scrcpy.Server 2.4 "
              "log_level=info max_size=540 max_fps=15 "
              "video_codec=h264 tunnel_forward=true control=false audio=false")
print("=== start server ===")
proc = subprocess.Popen([ADB, "-s", SERIAL, "shell", server_cmd],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# 4. connect client
time.sleep(2)
print("=== connect client ===")
s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
print("connected!")

# 5. read dummy byte + device info
dummy = s.recv(1)
print("dummy byte:", dummy.hex())

name_len = s.recv(1)[0]
name = s.recv(name_len).decode(errors="replace")
w = struct.unpack(">H", s.recv(2))[0]
h = struct.unpack(">H", s.recv(2))[0]
print(f"device: '{name}' {w}x{h}")

# 6. read first video packet header (12 bytes)
s.settimeout(5)
header = b""
while len(header) < 12:
    chunk = s.recv(12 - len(header))
    if not chunk:
        break
    header += chunk
print(f"header len={len(header)} hex={header.hex()}")
if len(header) == 12:
    flags, pts, size = struct.unpack(">III", header)
    print(f"frame: flags={flags:#x} pts={pts} size={size}")
    payload = b""
    while len(payload) < size:
        chunk = s.recv(size - len(payload))
        if not chunk:
            break
        payload += chunk
    print(f"payload: {len(payload)} bytes, first 12: {payload[:12].hex()}")

s.close()
proc.terminate()
time.sleep(0.5)
proc.kill()
print("=== done ===")
