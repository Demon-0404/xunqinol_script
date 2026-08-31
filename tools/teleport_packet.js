var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var M1 = 0, M2 = 0;
var lastX = null, lastY = null;
var targetX = null, targetY = null;
var speedMult = 1.0;  // speed multiplier
var mode = 'monitor';  // monitor, teleport, speed

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {
            var key = buf.add(1).readU8();
            var p = [];
            for (var i = 0; i < 29; i++) p.push(buf.add(i + 1).readU8() ^ key);
            var x = p[17], y = p[21];
            if (!M1) { M1 = p[1]; M2 = p[3]; }

            // Modify packet based on mode
            if (mode === 'teleport' && targetX !== null && targetY !== null) {
                // Modify position in the packet buffer
                buf.add(18).writeU8(targetX ^ key);        // X ^ key
                buf.add(20).writeU8(targetX ^ M1 ^ key);   // X^M1 ^ key
                buf.add(22).writeU8(targetY ^ key);        // Y ^ key
                buf.add(24).writeU8(targetY ^ M2 ^ key);   // Y^M2 ^ key
                send({t: 'teleport', fromX: x, fromY: y, toX: targetX, toY: targetY});
                mode = 'monitor';  // one-shot
                targetX = null; targetY = null;
            } else if (mode === 'speed' && lastX !== null) {
                // Amplify movement delta
                var dx = x - lastX;
                var dy = y - lastY;
                var newX = (lastX + Math.round(dx * speedMult)) & 0xFF;
                var newY = (lastY + Math.round(dy * speedMult)) & 0xFF;
                buf.add(18).writeU8(newX ^ key);
                buf.add(20).writeU8(newX ^ M1 ^ key);
                buf.add(22).writeU8(newY ^ key);
                buf.add(24).writeU8(newY ^ M2 ^ key);
            }

            if (lastX === null || x !== lastX || y !== lastY) {
                send({t: 'pos', x: x, y: y});
            }
            lastX = x; lastY = y;
        }
    }
});

// Commands from Python
recv('teleport', function(data) {
    targetX = data.x & 0xFF;
    targetY = data.y & 0xFF;
    mode = 'teleport';
    send({t: 'cmd', cmd: 'teleport', x: targetX, y: targetY});
});

recv('speed', function(data) {
    speedMult = data.mult;
    mode = 'speed';
    send({t: 'cmd', cmd: 'speed', mult: speedMult});
});

recv('monitor', function(data) {
    mode = 'monitor';
    send({t: 'cmd', cmd: 'monitor'});
});

recv('status', function(data) {
    send({t: 'status', mode: mode, speedMult: speedMult, lastX: lastX, lastY: lastY});
});

send({t: 'ready'});
