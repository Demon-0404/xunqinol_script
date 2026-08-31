"""Live-stream test: confirm ffmpeg outputs frames while stdin stays OPEN.

Key fix vs previous run: -probesize / -analyzeduration / -fflags are INPUT
options and MUST precede -i pipe:0. Previously they were placed after -i and
silently ignored by ffmpeg.
"""
import subprocess, time, socket, struct, os, sys, threading
import numpy as np

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERVER_LOCAL = r"D:\Setup_and_Downloads\Setup\op\scrcpy-server"
FFMPEG = r"D:\Setup_and_Downloads\Setup\FormatFactory\ffmpeg.exe"
SERIAL = "127.0.0.1:16384"   # 天音
PORT = 27200


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


def kill_server():
    try:
        r = adb("shell", "ps", "-A", timeout=5)
        for line in r.stdout.splitlines():
            f = line.split()
            if len(f) >= 2 and ("app_process" in f[-1].lower() or "scrcpy" in f[-1].lower()):
                adb("shell", "kill", "-9", f[1], timeout=5)
    except Exception:
        pass


def run(input_flags, output_flags, label):
    print(f"\n=== {label} ===")
    kill_server()
    adb("forward", "--remove-all")
    adb("shell", "rm", "-f", "/data/local/tmp/scrcpy-server.jar")
    adb("push", SERVER_LOCAL, "/data/local/tmp/scrcpy-server.jar")
    adb("forward", f"tcp:{PORT}", "localabstract:scrcpy")

    server_cmd = ("CLASSPATH=/data/local/tmp/scrcpy-server.jar "
                  "app_process / com.genymobile.scrcpy.Server 2.4 "
                  "log_level=info max_size=0 max_fps=15 "
                  "video_codec=h264 tunnel_forward=true control=false audio=false "
                  "lock_video_orientation=0")
    proc = subprocess.Popen([ADB, "-s", SERIAL, "shell", server_cmd],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    s = None
    for _ in range(40):
        try:
            c = socket.create_connection(("127.0.0.1", PORT), timeout=2)
            c.settimeout(2)
            if c.recv(1):
                s = c
                break
            c.close()
        except Exception:
            try:
                c.close()
            except Exception:
                pass
        time.sleep(0.2)
    if s is None:
        print("FAIL connect")
        proc.terminate(); proc.kill(); kill_server()
        return
    s.settimeout(5)

    name = recv_exact(s, 64).rstrip(b"\x00").decode(errors="replace")
    codec_id, w, h = struct.unpack(">III", recv_exact(s, 12))
    print(f"name='{name}' codec={codec_id:#x} {w}x{h}")

    ff_args = [FFMPEG, "-hide_banner", "-loglevel", "warning"] + input_flags + \
              ["-f", "h264", "-i", "pipe:0"] + output_flags + \
              ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    print("ffmpeg:", " ".join(a for a in ff_args))
    dec = subprocess.Popen(ff_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)

    frame_bytes = w * h * 3
    frames = []
    err_buf = []

    def drain():
        try:
            while True:
                buf = b""
                while len(buf) < frame_bytes:
                    c = dec.stdout.read(frame_bytes - len(buf))
                    if not c:
                        return
                    buf += c
                frames.append(time.time())
        except Exception:
            return

    def drain_err():
        for line in dec.stderr:
            err_buf.append(line.decode(errors="replace").strip())

    threading.Thread(target=drain, daemon=True).start()
    threading.Thread(target=drain_err, daemon=True).start()

    n_pkt = 0
    t0 = time.time()
    first_frame_at = None
    try:
        while time.time() - t0 < 5.0:
            hdr = recv_exact(s, 12)
            pts_flags, size = struct.unpack(">QI", hdr)
            payload = recv_exact(s, size)
            n_pkt += 1
            dec.stdin.write(payload)
            dec.stdin.flush()
            if frames and first_frame_at is None:
                first_frame_at = time.time() - t0
    except Exception as e:
        print(f"feed stopped: {e}")

    elapsed = time.time() - t0
    print(f"fed {n_pkt} packets over {elapsed:.1f}s; frames={len(frames)}; first_frame_at={first_frame_at}")
    if err_buf:
        print("ffmpeg stderr (last 8):")
        for l in err_buf[-8:]:
            print("  ", l)

    try:
        dec.stdin.close()
    except Exception:
        pass
    time.sleep(0.5)
    dec.terminate()
    try:
        s.close()
    except Exception:
        pass
    proc.terminate(); time.sleep(0.3); proc.kill()
    kill_server()
    adb("forward", "--remove", f"tcp:{PORT}")


run(["-probesize", "32", "-analyzeduration", "0"],
    [], "A: probesize32 before -i")
run(["-probesize", "32", "-analyzeduration", "0", "-fflags", "nobuffer", "-framerate", "15"],
    ["-flags", "low_delay"], "B: probesize32+nobuffer+framerate, low_delay")
print("\n=== done ===")
