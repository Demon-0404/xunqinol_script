var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var M1 = 0, M2 = 0;
var lastRealX = null, lastRealY = null;
var lastVirtX = null, lastVirtY = null;
var speedMult = 3.0;
var pktCount = 0;
var speedCount = 0;

function wrapDelta(d) {
    if (d > 128) return d - 256;
    if (d < -128) return d + 256;
    return d;
}

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 30 && buf.readU8() === 3) {
            var key = buf.add(1).readU8();
            var p = [];
            for (var i = 0; i < 29; i++) p.push(buf.add(i + 1).readU8() ^ key);

            if (!M1) {
                M1 = p[1];
                M2 = p[3];
            }

            pktCount++;
            var x = p[17], y = p[21];

            if (lastRealX === null) {
                lastRealX = x; lastRealY = y;
                lastVirtX = x; lastVirtY = y;
                return;
            }

            if (x !== lastRealX || y !== lastRealY) {
                var dx = wrapDelta(x - lastRealX);
                var dy = wrapDelta(y - lastRealY);

                if (dx !== 0 || dy !== 0) {
                    var ampDx = Math.round(dx * speedMult);
                    var ampDy = Math.round(dy * speedMult);

                    // Apply amplified delta with clamping (no wrapping!)
                    var newVirtX = lastVirtX + ampDx;
                    var newVirtY = lastVirtY + ampDy;
                    if (newVirtX < 0) newVirtX = 0;
                    if (newVirtX > 255) newVirtX = 255;
                    if (newVirtY < 0) newVirtY = 0;
                    if (newVirtY > 255) newVirtY = 255;

                    buf.add(18).writeU8(newVirtX ^ key);
                    buf.add(20).writeU8(newVirtX ^ M1 ^ key);
                    buf.add(22).writeU8(newVirtY ^ key);
                    buf.add(24).writeU8(newVirtY ^ M2 ^ key);

                    speedCount++;
                    if (speedCount <= 10) {
                        send({t: 'amp', n: speedCount,
                              realX: x, realY: y,
                              virtX: newVirtX, virtY: newVirtY,
                              dx: dx, dy: dy, ampDx: ampDx, ampDy: ampDy});
                    }

                    lastVirtX = newVirtX;
                    lastVirtY = newVirtY;
                    lastRealX = x; lastRealY = y;
                }
            }
        }
    }
});

send({t: 'ready', mult: speedMult});
