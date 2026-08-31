var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var captureMode = false;
var capturedHex = '';
var injectReady = false;
var injectHex = '';

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd === GAME_FD && len === 29 && buf.readU8() === 3) {
            captureMode = true;
            capturedHex = '';
            send({t: 'capture_start'});
        }
    }
});

Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        if (captureMode && this.fd === GAME_FD) {
            this.doCap = true;
        }
        if (injectReady && this.fd === GAME_FD && injectHex) {
            this.doInj = true;
        }
    },
    onLeave: function(ret) {
        if (this.doCap) {
            var len = ret.toInt32();
            if (len <= 0) return;
            // Read all data
            for (var i = 0; i < len; i++) {
                capturedHex += ('0' + this.buf.add(i).readU8().toString(16)).slice(-2);
            }
            // Stop after collecting enough (about 2000 bytes)
            if (capturedHex.length > 3000) {
                captureMode = false;
                send({t: 'capture_done', totalLen: capturedHex.length / 2});
            }
        }
        if (this.doInj) {
            var data = [];
            for (var i = 0; i < injectHex.length; i += 2) {
                data.push(parseInt(injectHex.substring(i, i + 2), 16));
            }
            var len = data.length;
            for (var i = 0; i < len; i++) {
                this.buf.add(i).writeU8(data[i]);
            }
            ret.replace(len);
            injectReady = false;
            send({t: 'injected', len: len});
        }
    }
});

// Auto-stop capture after 5 seconds
setTimeout(function() {
    if (captureMode) {
        captureMode = false;
        send({t: 'capture_done', totalLen: capturedHex.length / 2});
    }
}, 5000);

rpc.exports = {
    getCapture: function() { return capturedHex; },
    inject: function(hex) {
        injectHex = hex;
        injectReady = true;
        return 'READY len=' + (hex.length / 2);
    }
};

send({t: 'ready', msg: 'Snatch & Inject ready.'});
