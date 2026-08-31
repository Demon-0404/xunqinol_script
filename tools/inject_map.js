var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");
var injectData = null;
var injectReady = false;

Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
    },
    onLeave: function(ret) {
        if (!injectReady || !injectData || this.fd !== GAME_FD) return;
        var len = injectData.length;
        for (var i = 0; i < len; i++) {
            this.buf.add(i).writeU8(injectData[i]);
        }
        ret.replace(len);
        injectReady = false;
        send({t: 'injected', len: len});
    }
});

rpc.exports = {
    inject: function(hex) {
        injectData = [];
        for (var i = 0; i < hex.length; i += 2) {
            injectData.push(parseInt(hex.substring(i, i + 2), 16));
        }
        injectReady = true;
        return 'READY len=' + injectData.length;
    }
};

send({t: 'ready', msg: 'Map injector ready.'});
