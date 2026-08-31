var GAME_FD = %d;
var libc = Process.getModuleByName("libc.so");

var frozenPayload = null; // 28字节冻结的payload
var frozen = false;

Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();
        if (fd !== GAME_FD) return;
        if (buf.readU8() !== 3) return;

        var key = buf.add(1).readU8();

        if (len === 30 && frozen && frozenPayload) {
            // 替换整个payload为冻结的位置
            for (var i = 0; i < 28; i++) {
                buf.add(i + 2).writeU8(frozenPayload[i] ^ key);
            }
            if (!this._cnt) this._cnt = 0;
            this._cnt++;
            if (this._cnt % 10 === 1) {
                send({t: 'frozen', cnt: this._cnt});
            }
        }
    }
});

rpc.exports = {
    freeze: function() {
        frozen = true;
        send({t: 'status', msg: 'Position FROZEN'});
        return 'OK';
    },
    unfreeze: function() {
        frozen = false;
        send({t: 'status', msg: 'Position UNFROZEN'});
        return 'OK';
    },
    setPayload: function(hex) {
        frozenPayload = [];
        for (var i = 0; i < hex.length; i += 2) {
            frozenPayload.push(parseInt(hex.substring(i, i + 2), 16));
        }
        send({t: 'status', msg: 'Payload set: ' + hex});
        return 'OK';
    }
};

send({t: 'ready', msg: 'Position freeze ready. 先走动，然后冻结位置看效果！'});
