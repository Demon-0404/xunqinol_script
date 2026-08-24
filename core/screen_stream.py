"""scrcpy 视频流 —— 低延迟截图替代 adb screencap

原理:
  - 每个设备(serial)起一个 scrcpy server(lock_video_orientation=0 强制竖屏,
    max_size=0 保持原生 1080x1920), H.264 流经 adb forward 到本地 socket。
  - 本地用 ffmpeg.exe 把 H.264 解码成 rawvideo(rgb24), 后台线程持续拉帧,
    缓存最新一帧。业务侧 get_frame() 直接拿最新帧, 免去 screencap 的
    PNG 编码(设备端)+PNG 解码(宿主端) ≈ 0.7s 开销。

用法:
    from core.screen_stream import get_stream
    frame, ts = get_stream(serial).get_frame()   # frame 是 RGB ndarray (H,W,3)
"""
import io
import os
import re
import subprocess
import socket
import struct
import threading
import time

import numpy as np
from PIL import Image

MUMU_ADB = r"D:/Setup_and_Downloads/Setup/MuMuPlayer/nx_main/adb.exe"
SCRCPY_SERVER = r"D:/Setup_and_Downloads/Setup/op/scrcpy-server"
SCRCPY_SERVER_REMOTE = "/oem/scrcpy-server.jar"  # MuMu12 部分实例 /data 被挂为只读(如16416), jar 放可写的 /oem
SCRCPY_LOG_REMOTE = "/oem/scrcpy.log"
FFMPEG = r"D:/Setup_and_Downloads/Setup/FormatFactory/ffmpeg.exe"

_PORT_BASE = 27100
_RESTART_INTERVAL = 2.0    # 流挂掉后的最小重试间隔(秒)，快速自愈；设备离线时每2s重试一次
_STALE_FRAME_SECONDS = 2.0 # 帧超过该秒数未更新即视为流卡死(zombie)，触发回退/重启
_port_counter = 0
_port_lock = threading.Lock()

_registry = {}
_registry_lock = threading.Lock()


def _alloc_port() -> int:
    global _port_counter
    with _port_lock:
        _port_counter += 1
        return _PORT_BASE + _port_counter


def _read_sock(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("stream socket closed")
        buf += chunk
    return buf


def _read_file(f, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = f.read(n - len(buf))
        if not chunk:
            raise ConnectionError("decoder pipe closed")
        buf += chunk
    return buf


class ScreenStream:
    """单设备 scrcpy 视频流客户端"""

    def __init__(self, serial: str, adb: str = None, max_fps: int = 15):
        self.serial = serial
        self.adb = adb or MUMU_ADB
        self.max_fps = max_fps
        self.port = _alloc_port()

        self._lock = threading.Lock()
        self._frame = None          # RGB ndarray (H, W, 3)
        self._frame_ts = 0.0
        self._frame_seq = 0
        self.width = 0
        self.height = 0
        self.codec_id = 0

        self._server_proc = None
        self._decoder = None
        self._socket = None
        self._reader = None
        self._drainer = None
        self._stop = threading.Event()
        self._alive = False
        self._gen = 0               # 每次 start() 自增，隔离旧线程的 _mark_dead
        self._last_start_ts = 0.0
        self._display_id = None     # 缓存探测到的 display id，重启复用
        self._jar_ready = False     # scrcpy-server.jar 是否已 push，重启复用

    # ── 生命周期 ────────────────────────────────

    def _adb(self, *args, timeout=10):
        return subprocess.run([self.adb, "-s", self.serial] + list(args),
                              capture_output=True, text=True, timeout=timeout)

    def _kill_device_server(self):
        """杀掉设备端残留的 scrcpy 进程, 避免占用 localabstract:scrcpy 套接字"""
        try:
            r = self._adb("shell", "ps", "-A", timeout=5)
            pids = []
            for line in r.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 2:
                    name = fields[-1].lower()
                    if "app_process" in name or "scrcpy" in name:
                        pids.append(fields[1])
            for pid in pids:
                self._adb("shell", "kill", "-9", pid, timeout=5)
        except Exception:
            pass

    def _screencap_display(self, did: int):
        """抓指定 display 的一帧, 返回 (平均亮度, 宽, 高); 失败返回 (-1.0, 0, 0)。"""
        try:
            r = subprocess.run(
                [self.adb, "-s", self.serial, "exec-out",
                 "screencap", "-p", "-d", str(did)],
                capture_output=True, timeout=8)
            if not r.stdout:
                return (-1.0, 0, 0)
            img = Image.open(io.BytesIO(r.stdout))
            arr = np.asarray(img.convert("RGB"), dtype=np.uint8)
            h, w = arr.shape[:2]
            return (float(arr.mean()), w, h)
        except Exception:
            return (-1.0, 0, 0)

    def _detect_display_id(self) -> int:
        """自动探测游戏所在 display。
        1) 优先按游戏包名 proj.xqj 定位(dumpsys SurfaceFlinger);
        2) 回退: 竖屏(高>宽)display 优先再取最亮(桌面横屏更亮也不抢)。"""
        try:
            r = self._adb("shell", "dumpsys", "SurfaceFlinger", "--list", timeout=8)
            cur = -1
            for line in r.stdout.splitlines():
                m = re.match(r"Display (\d+)", line)
                if m:
                    cur = int(m.group(1))
                elif "proj.xqj" in line and cur >= 0:
                    return cur
        except Exception:
            pass

        best, best_val = 0, -1.0
        for did in (0, 1, 2, 3):
            v, w, h = self._screencap_display(did)
            if v < 0:
                continue
            if h > w and v > best_val:   # 竖屏 = 游戏
                best, best_val = did, v
        if best_val < 0:
            for did in (0, 1, 2, 3):
                v, w, h = self._screencap_display(did)
                if v > best_val:
                    best, best_val = did, v
        return best

    def _ensure_jar(self) -> bool:
        """确保 scrcpy-server.jar 已就位。已 push 过则跳过（push 是重启主要耗时）"""
        if self._jar_ready:
            return True
        try:
            local_size = os.path.getsize(SCRCPY_SERVER)
            r = self._adb("shell", "stat", "-c", "%s",
                          SCRCPY_SERVER_REMOTE, timeout=6)
            if r.stdout.strip().isdigit() and int(r.stdout.strip()) == local_size:
                self._jar_ready = True
                return True
        except Exception:
            pass
        try:
            self._adb("push", SCRCPY_SERVER, SCRCPY_SERVER_REMOTE, timeout=15)
            self._jar_ready = True
            return True
        except Exception:
            return False

    def _mark_launch_failed(self):
        """握手/解码失败：重置 jar/display 缓存（设备可能重启过），清理现场"""
        self._jar_ready = False
        self._display_id = None
        self._cleanup_proc()

    def start(self):
        if self._alive:
            return
        self._gen += 1
        self._last_start_ts = time.time()
        self._stop.clear()
        with self._lock:
            self._frame = None

        if not self._ensure_jar():
            return

        self._kill_device_server()
        try:
            self._adb("forward", "--remove-all", timeout=5)
            self._adb("forward", f"tcp:{self.port}", "localabstract:scrcpy", timeout=5)
        except Exception:
            return

        if self._display_id is None:
            self._display_id = self._detect_display_id()

        self._launch_server()

    def _launch_server(self):
        """启动 server 进程 + 握手 + 拉起解码线程（复用已就位的 jar/forward/display）"""
        server_cmd = ("CLASSPATH=%s "
                      "app_process / com.genymobile.scrcpy.Server 2.4 "
                      "log_level=info max_size=0 max_fps=%d video_codec=h264 "
                      "tunnel_forward=true control=false audio=false "
                      "lock_video_orientation=0" % (SCRCPY_SERVER_REMOTE, self.max_fps))
        if self._display_id and self._display_id != 0:
            server_cmd += " display_id=%d" % self._display_id
        # setsid 脱离 adb shell 进程组：MuMu 回收 shell 会话时不会连带 SIGKILL server
        full_cmd = ("setsid nohup sh -c '%s' "
                    ">%s 2>&1 &" % (server_cmd, SCRCPY_LOG_REMOTE))
        try:
            self._adb("shell", full_cmd, timeout=5)
        except Exception:
            return

        # 等待 server 就绪并读到 dummy 字节(0x00), 避免 forward 早于 server bind 导致 EOF
        sock = None
        for _ in range(40):
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                s.settimeout(2)
                if s.recv(1):
                    sock = s
                    break
                s.close()
            except Exception:
                try:
                    s.close()
                except Exception:
                    pass
            time.sleep(0.2)
        if sock is None:
            self._mark_launch_failed()
            return
        sock.settimeout(5)
        self._socket = sock

        try:
            _read_sock(sock, 64)              # device name (固定 64 字节, 已吃掉 dummy byte)
            codec_id, w, h = struct.unpack(">III", _read_sock(sock, 12))
            self.codec_id = codec_id
            self.width, self.height = w, h
        except Exception:
            self._mark_launch_failed()
            return

        # 启动 ffmpeg 解码器
        try:
            self._decoder = subprocess.Popen(
                [FFMPEG, "-hide_banner", "-loglevel", "error",
                 "-probesize", "32", "-analyzeduration", "0",
                 "-f", "h264", "-i", "pipe:0",
                 "-vf", f"scale={self.width}:{self.height}",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL)
        except Exception:
            self._mark_launch_failed()
            return

        self._alive = True
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._drainer = threading.Thread(target=self._drain_loop, daemon=True)
        self._reader.start()
        self._drainer.start()

    def stop(self):
        self._stop.set()
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._decoder:
            try:
                self._decoder.stdin.close()
            except Exception:
                pass
            try:
                self._decoder.terminate()
            except Exception:
                pass
            self._decoder = None
        self._cleanup_proc()
        self._alive = False

    def _cleanup_proc(self):
        if self._server_proc:
            try:
                self._server_proc.terminate()
            except Exception:
                pass
            try:
                self._server_proc.kill()
            except Exception:
                pass
            self._server_proc = None
        self._kill_device_server()
        try:
            self._adb("forward", "--remove", f"tcp:{self.port}", timeout=5)
        except Exception:
            pass

    def is_alive(self) -> bool:
        if not self._alive:
            return False
        if self._decoder is None or self._decoder.poll() is not None:
            return False
        if self._reader is None or not self._reader.is_alive():
            return False
        if self._drainer is None or not self._drainer.is_alive():
            return False
        with self._lock:
            if self._frame is None:
                # zombie：启动后迟迟无第一帧 → 判死；刚启动还在等首帧，算活
                return time.time() - self._last_start_ts <= _STALE_FRAME_SECONDS
            if time.time() - self._frame_ts > _STALE_FRAME_SECONDS:
                return False
        return True

    # ── 帧读取 ──────────────────────────────────

    def _reader_loop(self):
        """socket → ffmpeg stdin"""
        gen = self._gen
        try:
            while not self._stop.is_set():
                hdr = _read_sock(self._socket, 12)
                _pts_flags, size = struct.unpack(">QI", hdr)
                payload = _read_sock(self._socket, size)
                if self._decoder is None or self._decoder.stdin is None:
                    break
                self._decoder.stdin.write(payload)
                self._decoder.stdin.flush()
        except Exception:
            pass
        finally:
            self._mark_dead(gen)

    def _drain_loop(self):
        """ffmpeg stdout → 最新帧缓存"""
        gen = self._gen
        frame_size = self.width * self.height * 3
        try:
            while not self._stop.is_set():
                buf = _read_file(self._decoder.stdout, frame_size)
                arr = np.frombuffer(buf, dtype=np.uint8).copy().reshape(
                    self.height, self.width, 3)
                with self._lock:
                    self._frame = arr
                    self._frame_ts = time.time()
                    self._frame_seq += 1
        except Exception:
            pass
        finally:
            self._mark_dead(gen)

    def _mark_dead(self, gen: int):
        if gen != self._gen:
            return                      # 旧线程收尾，不影响新流
        self._alive = False
        with self._lock:
            self._frame = None

    def get_frame(self):
        """返回 (frame, ts); 无帧或帧已卡死返回 (None, ts)"""
        with self._lock:
            if self._frame is None:
                return None, 0.0
            if time.time() - self._frame_ts > _STALE_FRAME_SECONDS:
                return None, self._frame_ts
            return self._frame, self._frame_ts

    def get_frame_seq(self) -> int:
        with self._lock:
            return self._frame_seq

    def wait_fresh(self, after_seq: int, timeout: float = 2.0) -> bool:
        """等待 seq > after_seq 的新帧到来, 用于点击后确认画面已更新"""
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stop.is_set():
            if self.get_frame_seq() > after_seq:
                return True
            time.sleep(0.01)
        return False


def get_stream(serial: str, **kw) -> ScreenStream:
    """获取(或懒启动)某设备的视频流。串口无流或已死则自动重启。"""
    with _registry_lock:
        st = _registry.get(serial)
        if st is None:
            st = ScreenStream(serial, **kw)
            _registry[serial] = st
            st.start()
        elif not st.is_alive() and time.time() - st._last_start_ts > _RESTART_INTERVAL:
            st.stop()
            st.start()
        return st


def stop_all():
    with _registry_lock:
        for st in _registry.values():
            st.stop()
        _registry.clear()
