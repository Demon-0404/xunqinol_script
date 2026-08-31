var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var lastX = null, lastY = null;
var M1 = 0, M2 = 0;
var deltas = [];

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

            if (lastX !== null && (x !== lastX || y !== lastY)) {
                var dx = x - lastX;
                var dy = y - lastY;
                if (dx > 128) dx -= 256;
                if (dx < -128) dx += 256;
                if (dy > 128) dy -= 256;
                if (dy < -128) dy += 256;

                deltas.push({dx: dx, dy: dy});
                send({t: 'delta', n: deltas.length, dx: dx, dy: dy,
                      fromX: lastX, fromY: lastY, toX: x, toY: y});

                // Stats every 5 steps
                if (deltas.length %% 5 === 0) {
                    var sumAbs = 0, maxAbs = 0;
                    var freq = {};
                    for (var i = 0; i < deltas.length; i++) {
                        var adx = Math.abs(deltas[i].dx);
                        var ady = Math.abs(deltas[i].dy);
                        sumAbs += adx + ady;
                        if (adx > maxAbs) maxAbs = adx;
                        if (ady > maxAbs) maxAbs = ady;
                        var k = deltas[i].dx + ',' + deltas[i].dy;
                        freq[k] = (freq[k] || 0) + 1;
                    }
                    var avg = (sumAbs / (deltas.length * 2)).toFixed(2);
                    // Find most common
                    var top = [];
                    for (var k in freq) top.push({key: k, cnt: freq[k]});
                    top.sort(function(a,b){return b.cnt - a.cnt;});
                    send({t: 'stats', count: deltas.length, avg: avg, max: maxAbs,
                          top3: top.slice(0, 3), M1: M1, M2: M2});
                }
            }
            lastX = x; lastY = y;
        }
    }
});

send({t: 'ready'});
