var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");

var sessionKey = 0;
var captureMode = false;
var capturedPlainHex = '';
var injectReady = false;
var injectEncHex = '';

Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.isGame = this.fd === GAME_FD;
    },
    onLeave: function(ret) {
        if (!this.isGame) return;
        var len = ret.toInt32();
        if (len <= 0) return;

        // Auto-detect session key
        if (sessionKey === 0 && len >= 4) {
            var tryKey = this.buf.readU8() ^ 0x03;
            if ((this.buf.add(1).readU8() ^ tryKey) === 0 &&
                (this.buf.add(2).readU8() ^ tryKey) === 0 &&
                (this.buf.add(3).readU8() ^ tryKey) === 0) {
                sessionKey = tryKey;
                send({t: 'key', key: sessionKey});
            }
        }

        // Capture mode
        if (captureMode) {
            var key = sessionKey || 0xbe;
            for (var i = 0; i < len; i++) {
                capturedPlainHex += ('0' + (this.buf.add(i).readU8() ^ key).toString(16)).slice(-2);
            }
        }

        // Inject mode
        if (injectReady && injectEncHex) {
            var data = [];
            for (var i = 0; i < injectEncHex.length; i += 2) {
                data.push(parseInt(injectEncHex.substring(i, i + 2), 16));
            }
            for (var j = 0; j < data.length; j++) {
                this.buf.add(j).writeU8(data[j]);
            }
            ret.replace(data.length);
            injectReady = false;
            send({t: 'injected', len: data.length});
        }
    }
});

// Detect portal send to start capture
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 29 && buf.readU8() === 3 && captureMode) {
            // Portal sent, stop capturing soon
            setTimeout(function() {
                if (captureMode) {
                    captureMode = false;
                    send({t: 'capture_done', len: capturedPlainHex.length / 2});
                }
            }, 3000);
        }
    }
});

rpc.exports = {
    startCapture: function() {
        captureMode = true;
        capturedPlainHex = '';
        return 'OK';
    },
    stopCapture: function() {
        captureMode = false;
        return capturedPlainHex;
    },
    teleport: function(plainHex) {
        var key = sessionKey || 0xbe;
        injectEncHex = '';
        for (var i = 0; i < plainHex.length; i += 2) {
            var b = parseInt(plainHex.substring(i, i + 2), 16);
            injectEncHex += ('0' + (b ^ key).toString(16)).slice(-2);
        }
        injectReady = true;
        return 'OK key=0x' + key.toString(16);
    },
    getKey: function() { return sessionKey; },
    isCapturing: function() { return captureMode; }
};

send({t: 'ready', msg: 'Teleport system ready.'});
