// ============================================================
// 搜索 "xqj://map" 字符串引用 → 找到真正的handler函数
// ============================================================

var libc = Process.getModuleByName("libc.so");
var gameFd = -1;

// 找游戏fd
(function() {
    var gpn = libc.getExportByName("getpeername");
    var getpeername = new NativeFunction(gpn, "int", ["int", "pointer", "pointer"]);
    for (var fd = 30; fd <= 200; fd++) {
        try {
            var addr = Memory.alloc(128);
            var alen = Memory.alloc(4);
            alen.writeInt(128);
            if (getpeername(fd, addr, alen) === 0) {
                var port = ((addr.add(2).readU8() << 8) | addr.add(3).readU8());
                if (port === 30002) { gameFd = fd; break; }
            }
        } catch(e) {}
    }
})();
send({t: "info", msg: "gameFd=" + gameFd});

// 搜索 "xqj://map" 字符串
var pattern = "78 71 6a 3a 2f 2f 6d 61 70"; // "xqj://map"
var results = [];

// 在所有可读模块中搜索
Process.enumerateModules().forEach(function(m) {
    if (m.size > 50 * 1024 * 1024) return; // skip huge regions

    try {
        Memory.scan(m.base, m.size, pattern, {
            onMatch: function(addr, size) {
                // 读取完整字符串
                try {
                    var str = addr.readCString();
                    if (str && str.indexOf("xqj://map") === 0) {
                        results.push({
                            addr: addr.toString(),
                            str: str.substring(0, 100),
                            module: m.name,
                            offset: addr.sub(m.base).toString(16)
                        });
                        send({t: "found_str", addr: addr.toString(), str: str.substring(0, 100),
                              module: m.name, offset: "0x" + addr.sub(m.base).toString(16)});
                    }
                } catch(e) {}
                return "stop"; // just find first one
            },
            onComplete: function() {}
        });
    } catch(e) {}
});

// 也尝试搜索 "Portal" 或地图相关字符串
var patterns2 = [
    {name: "map", pattern: "6d 61 70"}, // "map"
];

send({t: "info", msg: "找到 " + results.length + " 个 xqj://map 引用"});

// Hook send 检测传送包 + 同时尝试读handlerObj内存
var checkInterval = setInterval(function() {
    // 周期性检查handlerObj (0xc600a30) 是否变化
    try {
        var obj = ptr(0xc600a30);
        var val = obj.readPointer();
        if (val && !val.isNull()) {
            send({t: "handlerObj", addr: "0xc600a30", val: val.toString()});
        }
    } catch(e) {}
}, 5000);

// 列出现有模块名，帮确认libtestcpp等的真实名称
send({t: "modules", msg: "已加载模块:"});
Process.enumerateModules().forEach(function(m) {
    if (m.name.indexOf("lib") >= 0 || m.name.indexOf("game") >= 0 || m.name.indexOf("cocos") >= 0) {
        send({t: "module", name: m.name, base: m.base.toString(), size: m.size});
    }
});

// 阻止断网
Interceptor.attach(libc.getExportByName("close"), {
    onEnter: function(args) {
        if (gameFd > 0 && args[0].toInt32() === gameFd) {
            this.block = true;
            send({t: "warn", msg: "close(" + gameFd + ") blocked"});
        }
    },
    onLeave: function(ret) {
        if (this.block) { ret.replace(0); this.block = false; }
    }
});

Interceptor.attach(libc.getExportByName("shutdown"), {
    onEnter: function(args) {
        if (gameFd > 0 && args[0].toInt32() === gameFd) {
            this.block = true;
            send({t: "warn", msg: "shutdown(" + gameFd + ") blocked"});
        }
    },
    onLeave: function(ret) {
        if (this.block) { ret.replace(0); this.block = false; }
    }
});

// Hook send 抓包
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        if (fd !== gameFd) return;
        var len = args[2].toInt32();
        if (len === 29 && args[1].readU8() === 0x03) {
            var raw = "";
            for (var i = 0; i < len; i++) {
                raw += ("0" + args[1].add(i).readU8().toString(16)).slice(-2);
            }
            send({t: "portal", raw: raw});
        }
    }
});

rpc.exports = {
    getResults: function() { return JSON.stringify(results); },
    getModules: function() {
        var mods = [];
        Process.enumerateModules().forEach(function(m) {
            mods.push({name: m.name, base: m.base.toString(), size: m.size});
        });
        return JSON.stringify(mods);
    },
    // 尝试在指定地址读内存
    readAddr: function(addrStr) {
        try {
            var p = ptr(addrStr);
            var bytes = "";
            for (var i = 0; i < 64; i++) {
                bytes += ("0" + p.add(i).readU8().toString(16)).slice(-2);
            }
            return bytes;
        } catch(e) {
            return "Error: " + e;
        }
    },
    getGameFd: function() { return gameFd; }
};

send({t: "ready", msg: "搜索就绪", foundStrings: results.length});
