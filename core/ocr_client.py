"""OCR 客户端 —— 通过 TCP 调用共享 OCR 服务，避免每个 worker 各加载一份 easyocr。

对外提供与 easyocr.Reader.readtext 兼容的接口，任务代码几乎不用改。
"""
import os
import sys
import json
import time
import socket
import base64
import threading
import subprocess

HOST = "127.0.0.1"
PORT = 8765

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class OCRClient:
    """连接共享 OCR 服务的客户端，readtext 接口兼容 easyocr.Reader"""

    def __init__(self, host: str = HOST, port: int = PORT):
        self._sock = socket.create_connection((host, port), timeout=10)
        self._sock.settimeout(30)
        self._lock = threading.Lock()

    def readtext(self, image, mag_ratio: float = 1.0, **kwargs):
        """识别图像文字。image 为 numpy 数组或图像路径。返回 [[bbox, text, conf], ...]"""
        import numpy as np
        if isinstance(image, str):
            from PIL import Image
            image = np.array(Image.open(image))
        arr = np.ascontiguousarray(image)
        shape = list(arr.shape)
        img_b64 = base64.b64encode(arr.tobytes()).decode('ascii')

        req = {"img": img_b64, "shape": shape, "mag_ratio": mag_ratio}
        payload = (json.dumps(req) + "\n").encode('utf-8')

        with self._lock:
            self._sock.sendall(payload)
            f = self._sock.makefile('rb')
            line = f.readline()
            if not line:
                raise ConnectionError("OCR服务连接中断")
            resp = json.loads(line.decode('utf-8'))

        return [[r[0], r[1], r[2]] for r in resp.get("results", [])]

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass


_client = None
_client_lock = threading.Lock()


def _start_service():
    """启动 OCR 服务子进程（幂等：端口被占用时重复启动会自然失败退出）"""
    log_path = os.path.join(BASE_DIR, "logs", "ocr_service.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "ab") as f:
        subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "ocr_service.py")],
            stdout=f, stderr=subprocess.STDOUT, cwd=BASE_DIR)


def get_ocr_client() -> OCRClient:
    """获取（进程级）单例 OCR 客户端。连接失败时自动拉起服务。"""
    global _client
    with _client_lock:
        if _client is not None:
            return _client
        for attempt in range(2):
            try:
                _client = OCRClient()
                return _client
            except Exception:
                _start_service()
                # 等服务加载模型（首次约 10 秒）
                for _ in range(120):
                    time.sleep(0.5)
                    try:
                        _client = OCRClient()
                        return _client
                    except Exception:
                        continue
        raise RuntimeError("无法连接 OCR 服务")
