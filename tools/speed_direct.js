// Speed hack using direct addresses (libtestcpp.so hidden by libhoudini)
var base = ptr(0x0c074000);

// Key function offsets from readelf
var offsets = {
    schedulerUpdate: 0x001a28c9,     // CCScheduler::update(float)
    sharedDirector: 0x001b8229,      // CCDirector::sharedDirector()
    setAnimInterval: 0x001db495,     // CCApplication::setAnimationInterval(double)
    jumpUrl: 0x000da099,             // AppDelegate::jumpUrl(const char*)
    getDefaultSpeed: 0x0010d468,     // CTwMovement::GetDefaultAccSpeed()
};

// Try to hook CCScheduler::update and multiply delta time
var updateAddr = base.add(offsets.schedulerUpdate);
send({t: 'log', msg: 'Hooking CCScheduler::update at ' + updateAddr});

var SPEED = 2.0;

Interceptor.attach(updateAddr, {
    onEnter: function(args) {
        // ARM32 hard-float: r0=this, s0=float delta
        // Try to read s0 via context
        try {
            var ctx = this.context;
            // Different Frida versions expose float regs differently
            if (ctx.s0 !== undefined) {
                var delta = ctx.s0;
                if (delta > 0.0001 && delta < 1.0) {
                    ctx.s0 = delta * SPEED;
                }
            } else if (ctx['s0'] !== undefined) {
                var delta = ctx['s0'];
                if (delta > 0.0001 && delta < 1.0) {
                    ctx['s0'] = delta * SPEED;
                }
            }
        } catch(e) {
            send({t: 'err', msg: 's0 access failed: ' + e});
        }
    }
});

send({t: 'ready', msg: 'Speed hack loaded (direct address), speed=' + SPEED + 'x. Check if game is faster!'});
