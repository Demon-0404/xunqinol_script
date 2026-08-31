import sys
from core.screen_stream import ScreenStream

SERIAL = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:16480"
st = ScreenStream(SERIAL)
for did in (0, 1, 2, 3):
    v = st._screencap_display(did)
    print(f"display {did}: mean={v}")
print("detected display_id =", st._detect_display_id())
