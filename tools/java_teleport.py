"""Use Frida Java bridge to find teleport-related Java methods"""
import sys, os, time, subprocess

ADB = r"D:\Setup_and_Downloads\Setup\MuMuPlayer\nx_main\adb.exe"
SERIAL = "127.0.0.1:16544"

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

subprocess.run([ADB, "-s", SERIAL, "forward", "tcp:27055", "tcp:27042"],
               capture_output=True, timeout=10)

import frida
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27055")
session = dev.attach(pid)
print("Attached!", flush=True)

JS = """
Java.perform(function() {
    send({t:'info', m:'Java bridge ready'});

    // Search for classes related to map/teleport/jump/url
    var keywords = ['jump', 'url', 'map', 'teleport', 'scene', 'location', 'position', 'move'];
    var found_classes = [];

    Java.enumerateLoadedClasses({
        onMatch: function(className) {
            var lower = className.toLowerCase();
            for (var i = 0; i < keywords.length; i++) {
                if (lower.indexOf(keywords[i]) !== -1) {
                    found_classes.push(className);
                    break;
                }
            }
        },
        onComplete: function() {
            send({t:'info', m:'Found ' + found_classes.length + ' matching classes'});
            found_classes.forEach(function(c) {
                send({t:'class', name: c});
            });

            // Also try to find the main activity
            try {
                var ActivityThread = Java.use('android.app.ActivityThread');
                var currentApp = ActivityThread.currentApplication();
                send({t:'info', m:'Application: ' + currentApp});
            } catch(e) {}

            // Try common Cocos2d-x JNI helper
            try {
                var Cocos2dxHelper = Java.use('org.cocos2dx.lib.Cocos2dxHelper');
                send({t:'info', m:'Cocos2dxHelper found'});
            } catch(e) {}

            // Try to find AppActivity
            Java.enumerateLoadedClasses({
                onMatch: function(className) {
                    if (className.indexOf('Activity') !== -1 || className.indexOf('Application') !== -1) {
                        send({t:'activity', name: className});
                    }
                },
                onComplete: function() {
                    send({t:'ready'});
                }
            });
        }
    });
});
"""

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict):
        return
    ptype = payload.get('t', '?')

    if ptype == 'ready':
        print("\n>>> DONE <<<", flush=True)
    elif ptype == 'info':
        print(f"[*] {payload['m']}", flush=True)
    elif ptype == 'class':
        print(f"[CLASS] {payload['name']}", flush=True)
    elif ptype == 'activity':
        print(f"[ACTIVITY] {payload['name']}", flush=True)
    else:
        print(f"[{ptype}] {payload}", flush=True)

script = session.create_script(JS)
script.on('message', on_msg)
script.load()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDone.", flush=True)
    session.detach()
