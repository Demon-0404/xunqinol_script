import subprocess, time, socket, struct, os

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERVER_LOCAL = r"D:\Setup_and_Downloads\Setup\op\scrcpy-server"
SERIAL = "127.0.0.1:16480"
PORT = 27186

def adb(*args, timeout=10):
    return subprocess.run([ADB, "-s", SERIAL] + list(args),
                          capture_output=True, text=True, timeout=timeout)

def recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c:
            raise ConnectionError("eof")
        buf += c
    return buf

def probe(extra_args, label):
    adb("push", SERVER_LOCAL, "/data/local/tmp/scrcpy-server.jar")
    adb("forward", f"tcp:{PORT}", "localabstract:scrcpy")
    server_cmd = ("CLASSPATH=/data/local/tmp/scrcpy-server.jar "
                  "app_process / com.genymobile.scrcpy.Server 2.4 "
                  "log_level=info max_fps=15 video_codec=h264 "
                  "tunnel_forward=true control=false audio=false " + extra_args)
    proc = subprocess.Popen([ADB, "-s", SERIAL, "shell", server_cmd],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
        s.settimeout(5)
        recv_exact(s, 1)
        recv_exact(s, 64)
        codec_id, w, h = struct.unpack(">III", recv_exact(s, 12))
        print(f"{label}: codec={codec_id:#x} {w}x{h}")
        s.close()
    except Exception as e:
        print(f"{label}: ERROR {e}")
    proc.terminate(); time.sleep(0.3); proc.kill()
    time.sleep(1)

probe("max_size=1080", "no-lock max1080")
probe("max_size=1080 lock_video_orientation=0", "lock0  max1080")
probe("max_size=0 lock_video_orientation=0", "lock0  native")
print("=== done ===")
