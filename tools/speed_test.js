// Cocos2d-x speed hack — hook CCScheduler::update and multiply delta time
var mod = Process.findModuleByName("libtestcpp.so");
if (!mod) {
    send({t: 'err', msg: 'libtestcpp.so not loaded'});
} else {
    send({t: 'log', msg: 'libtestcpp.so at ' + mod.base});
}

// Method 1: Hook CCScheduler::update(float) — multiply delta time
var updateAddr = Module.findExportByName("libtestcpp.so", "_ZN7cocos2d11CCScheduler6updateEf");
if (updateAddr) {
    var SPEED = 2.0;
    Interceptor.attach(updateAddr, {
        onEnter: function(args) {
            // ARM32 hard-float: r0=this, s0=float delta
            // Try to read and modify the float in s0
            try {
                // For ARM32, the first float argument is in s0 (single-precision VFP reg)
                var delta = this.context.s0;
                if (delta && delta > 0 && delta < 1.0) {
                    this.context.s0 = delta * SPEED;
                }
            } catch(e) {
                // Context registers might have different naming
            }
        }
    });
    send({t: 'log', msg: 'CCScheduler::update hooked, speed=' + SPEED + 'x'});
}

// Method 2: Hook CCDirector::getDeltaTime — multiply return value
var getDeltaAddr = Module.findExportByName("libtestcpp.so", "_ZN7cocos2d10CCDirector12getDeltaTimeEv");
if (getDeltaAddr) {
    var SPEED2 = 2.0;
    Interceptor.attach(getDeltaAddr, {
        onLeave: function(ret) {
            try {
                var val = this.context.s0;
                if (val && val > 0 && val < 1.0) {
                    this.context.s0 = val * SPEED2;
                }
            } catch(e) {}
        }
    });
    send({t: 'log', msg: 'CCDirector::getDeltaTime hooked, speed=' + SPEED2 + 'x'});
}

// Method 3: Try to call setAnimationInterval directly
var sharedDirector = Module.findExportByName("libtestcpp.so", "_ZN7cocos2d10CCDirector14sharedDirectorEv");
var setAnimInterval = Module.findExportByName("libtestcpp.so", "_ZN7cocos2d13CCApplication20setAnimationIntervalEd");
if (sharedDirector && setAnimInterval) {
    try {
        var getDirector = new NativeFunction(sharedDirector, 'pointer', []);
        var director = getDirector();
        var setInterval = new NativeFunction(setAnimInterval, 'void', ['pointer', 'double']);
        setInterval(director, 1.0 / 180.0); // 3x (60fps -> 180fps equivalent)
        send({t: 'log', msg: 'setAnimationInterval called with ' + (1.0/180.0) + ' (3x)'});
    } catch(e) {
        send({t: 'err', msg: 'Method 3 failed: ' + e});
    }
}

rpc.exports = {
    speed: function(factor) {
        try {
            var getDirector = new NativeFunction(sharedDirector, 'pointer', []);
            var director = getDirector();
            var setInterval = new NativeFunction(setAnimInterval, 'void', ['pointer', 'double']);
            setInterval(director, 1.0 / (60.0 * factor));
            return 'Speed ' + factor + 'x';
        } catch(e) {
            return 'Error: ' + e;
        }
    }
};

send({t: 'ready', msg: 'Speed hack loaded'});
