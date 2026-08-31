# -*- coding: utf-8 -*-
"""Navigate character to a target game coordinate using position feedback + screen tap"""
import sys, time, subprocess, random

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16480"

TARGET_X = 23
TARGET_Y = 239

# Screen config (1080x1920)
CENTER_X = 540
CENTER_Y = 960
SPREAD = 200  # pixels from center to tap (smaller = finer steps)

# Safe tap zone (avoid edges, keyboard, UI bars)
SAFE_X_MIN = 120
SAFE_X_MAX = 960
SAFE_Y_MIN = 200
SAFE_Y_MAX = 1500

r = subprocess.run([ADB, "-s", SERIAL, "shell", "ps", "-A"],
                   capture_output=True, text=True, timeout=15)
pid = None
for line in r.stdout.split("\n"):
    if "proj.xqj" in line:
        parts = line.split()
        if len(parts) >= 2:
            pid = int(parts[1])
            break
print(f"PID={pid}", flush=True)

game_fd = -1
for tcp_file in ["net/tcp", "net/tcp6"]:
    r = subprocess.run([ADB, "-s", SERIAL, "shell", f"cat /proc/{pid}/{tcp_file}"],
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.split("\n"):
        line = line.strip()
        if not line or line.startswith("sl"):
            continue
        parts = line.split()
        if len(parts) >= 10 and parts[3] == "01":
            inode = parts[9]
            if inode != "0":
                r2 = subprocess.run([ADB, "-s", SERIAL, "shell", f"ls -la /proc/{pid}/fd/ | grep {inode}"],
                                   capture_output=True, text=True, timeout=10)
                for fl in r2.stdout.split("\n"):
                    fp = fl.strip().split()
                    if len(fp) >= 8:
                        try:
                            fd = int(fp[7])
                            if fd > 2:
                                game_fd = fd
                                break
                        except:
                            pass
        if game_fd > 0:
            break
    if game_fd > 0:
        break
print(f"Game fd={game_fd}", flush=True)
if game_fd < 0:
    sys.exit(1)

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)

# Shared state between Frida callback and main loop
current_pos = {'x': None, 'y': None, 'updated': False}

JS = f"""
var GAME_FD = {game_fd};
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;

Interceptor.attach(libc.getExportByName("send"), {{
    onEnter: function(args) {{
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {{
            var key = buf.add(1).readU8();
            var p = [];
            for (var i = 0; i < 29; i++) p.push(buf.add(i + 1).readU8() ^ key);
            var x = p[17], y = p[21];
            if (x !== lastX || y !== lastY) {{
                send({{t: 'pos', x: x, y: y}});
                lastX = x; lastY = y;
            }}
        }}
    }}
}});
send({{t: 'ready'}});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if isinstance(payload, dict) and payload.get('t') == 'pos':
        current_pos['x'] = payload['x']
        current_pos['y'] = payload['y']
        current_pos['updated'] = True

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

def tap_screen(x, y):
    """Tap screen at pixel position via ADB"""
    subprocess.run([ADB, "-s", SERIAL, "shell", f"input tap {x} {y}"],
                   capture_output=True, timeout=5)

def wait_position_change(old_x, old_y, timeout=8):
    """Wait for position to change from old values"""
    start = time.time()
    while time.time() - start < timeout:
        if current_pos['updated']:
            current_pos['updated'] = False
            if current_pos['x'] != old_x or current_pos['y'] != old_y:
                return current_pos['x'], current_pos['y']
        time.sleep(0.15)
    return None, None

def get_current_pos(timeout=3):
    """Wait for a fresh position reading"""
    current_pos['updated'] = False
    start = time.time()
    while time.time() - start < timeout:
        if current_pos['updated']:
            current_pos['updated'] = False
            return current_pos['x'], current_pos['y']
        time.sleep(0.15)
    return current_pos['x'], current_pos['y']

# Wait for initial position
print("Waiting for initial position...", flush=True)
time.sleep(2)
x, y = get_current_pos()
if x is None:
    print("Failed to get position!", flush=True)
    session.detach()
    sys.exit(1)

print(f"\nStart: X={x} Y={y}")
print(f"Target: X={TARGET_X} Y={TARGET_Y}")
print(f"Distance: dX={TARGET_X - x:+d} dY={TARGET_Y - y:+d}")
print("=" * 50)

MAX_STEPS = 30
THRESHOLD = 3  # Stop when within 3 units

for step in range(MAX_STEPS):
    x, y = get_current_pos()
    if x is None:
        break

    dx = TARGET_X - x
    dy = TARGET_Y - y

    # Handle byte overflow - find shortest path in 0-255 space
    if dx > 128: dx -= 256
    elif dx < -128: dx += 256
    if dy > 128: dy -= 256
    elif dy < -128: dy += 256

    dist = (dx*dx + dy*dy) ** 0.5
    if dist <= THRESHOLD:
        print(f"\n[DONE] Arrived! X={x} Y={y} (target: {TARGET_X},{TARGET_Y})", flush=True)
        break

    # Determine tap direction: click toward target
    # Use dx, dy signs to pick primary direction
    # Start from center, offset toward target
    ratio = 0
    if max(abs(dx), abs(dy)) > 0:
        ratio = min(abs(dx), abs(dy)) / max(abs(dx), abs(dy))

    if abs(dx) >= abs(dy):
        tap_x = CENTER_X + (SPREAD if dx > 0 else -SPREAD)
        tap_y = CENTER_Y + int(SPREAD * ratio * (1 if dy > 0 else -1))
    else:
        tap_y = CENTER_Y + (SPREAD if dy > 0 else -SPREAD)
        tap_x = CENTER_X + int(SPREAD * ratio * (1 if dx > 0 else -1))

    # Clamp strictly to safe zone (no keyboard, no UI edges)
    tap_x = max(SAFE_X_MIN, min(SAFE_X_MAX, tap_x))
    tap_y = max(SAFE_Y_MIN, min(SAFE_Y_MAX, tap_y))

    # Small jitter
    tap_x += random.randint(-20, 20)
    tap_y += random.randint(-20, 20)

    # Final clamp after jitter
    tap_x = max(SAFE_X_MIN, min(SAFE_X_MAX, tap_x))
    tap_y = max(SAFE_Y_MIN, min(SAFE_Y_MAX, tap_y))

    print(f"[Step {step+1}] X={x} Y={y}  d=({dx:+d},{dy:+d}) dist={dist:.0f}  tap=({tap_x},{tap_y})", flush=True)

    tap_screen(tap_x, tap_y)

    # Wait for character to walk
    new_x, new_y = wait_position_change(x, y, timeout=10)
    if new_x is None:
        print("  No movement detected, trying again...", flush=True)
        time.sleep(1)
    else:
        print(f"  -> X={new_x} Y={new_y}", flush=True)
        time.sleep(0.5)

session.detach()
print("Done.", flush=True)
