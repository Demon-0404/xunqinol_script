"""OCR 共享服务 —— 单例 easyocr 模型，供多个 task_worker 通过 TCP 调用。

协议（JSON-lines，utf-8）:
  请求: {"img": "<base64>", "shape": [h, w, c], "mag_ratio": 1.0}
  响应: {"results": [[bbox, text, conf], ...]}
"""
import sys
import os
import json
import socket
import threading
import base64

# 单线程 torch，避免 Windows 下动态量化算子(linear_dynamic)的 OpenMP 竞争
# 触发 "RuntimeError: could not execute a primitive"
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "127.0.0.1"
PORT = 8765

_reader = None
_lock = threading.Lock()
_ready = threading.Event()


def _load_reader():
    global _reader
    try:
        print("[OCR服务] 加载模型中(约10秒)...", flush=True)
        import numpy as np  # noqa: F401 确保 numpy 已导入
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        import easyocr
        _reader = easyocr.Reader(['ch_sim'], gpu=False, verbose=False)
        print("[OCR服务] 模型就绪", flush=True)
    finally:
        _ready.set()


def _native(v):
    import numpy as np
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, (list, tuple)):
        return [_native(x) for x in v]
    return v


def _handle(conn: socket.socket):
    f = conn.makefile('rb')
    try:
        while True:
            line = f.readline()
            if not line:
                break
            try:
                req = json.loads(line.decode('utf-8'))
                img_b64 = req["img"]
                shape = req["shape"]
                mag = req.get("mag_ratio", 1.0)
            except Exception:
                continue

            import numpy as np
            raw = base64.b64decode(img_b64)
            img = np.frombuffer(raw, dtype=np.uint8).reshape(shape).copy()
            _ready.wait()  # 等模型加载完成再识别
            if _reader is None:
                break
            with _lock:
                results = _reader.readtext(img, mag_ratio=mag)

            out = {"results": [[_native(r[0]), r[1], r[2]] for r in results]}
            conn.sendall((json.dumps(out, ensure_ascii=False) + "\n").encode('utf-8'))
    except Exception as e:
        import traceback
        print(f"[OCR服务] 处理请求异常: {e}", flush=True)
        traceback.print_exc()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind((HOST, PORT))
    except OSError:
        print("[OCR服务] 端口被占用，服务已在运行，本进程退出", flush=True)
        return
    # 写入 pidfile，供 UI 退出时清理本服务进程
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "ocr_service.pid"), "w") as pf:
            pf.write(str(os.getpid()))
    except Exception:
        pass
    srv.listen(16)
    print(f"[OCR服务] 监听 {HOST}:{PORT}", flush=True)
    # 模型在后台线程加载，主循环立即 accept，避免加载窗口内连接排队/backlog 满
    threading.Thread(target=_load_reader, daemon=True).start()
    while True:
        c, _ = srv.accept()
        threading.Thread(target=_handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
