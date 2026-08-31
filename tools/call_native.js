// Call Cocos2d-x functions via NativeFunction (direct addresses)
// BASE will be replaced by Python
var BASE = 0x0c074000;

// CCApplication::sharedApplication() at 0x001db579
// CCApplication::setAnimationInterval(double) at 0x001db495
var sharedAppAddr = BASE + 0x001db579;
var setAnimIntervalAddr = BASE + 0x001db495;

send({t: 'log', msg: 'sharedApplication at ' + ptr(sharedAppAddr)});
send({t: 'log', msg: 'setAnimationInterval at ' + ptr(setAnimIntervalAddr)});

try {
    var getApp = new NativeFunction(ptr(sharedAppAddr), 'pointer', []);
    var app = getApp();
    send({t: 'log', msg: 'CCApplication: ' + app});

    if (app && !app.isNull()) {
        var setInterval = new NativeFunction(ptr(setAnimIntervalAddr), 'void', ['pointer', 'double']);
        // Default: 1/60 = 0.01667. 3x speed: 1/180 = 0.00556
        var interval = 1.0 / 180.0;
        setInterval(app, interval);
        send({t: 'log', msg: 'setAnimationInterval(' + interval + ') called. Check speed!'});
    }
} catch(e) {
    send({t: 'err', msg: 'Failed: ' + e.toString()});
}

rpc.exports = {
    speed: function(factor) {
        try {
            var getApp = new NativeFunction(ptr(sharedAppAddr), 'pointer', []);
            var app = getApp();
            var setInterval = new NativeFunction(ptr(setAnimIntervalAddr), 'void', ['pointer', 'double']);
            setInterval(app, 1.0 / (60.0 * factor));
            return 'Speed set to ' + factor + 'x';
        } catch(e) {
            return 'Error: ' + e.toString();
        }
    }
};

send({t: 'ready', msg: 'Native call test loaded'});
