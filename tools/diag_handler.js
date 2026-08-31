// ============================================================
// 天音设备 — 传送门handler诊断脚本
// 目的: 抓取C++ handler被调用时的参数，验证能否直接调用跳图
// ============================================================

var libc = Process.getModuleByName("libc.so");

// === 解析函数地址 ===
// 方法1: 从libtestcpp.so基址+偏移计算 (推荐)
// 方法2: 使用之前验证过的绝对地址 (fallback)
var handlerAddr, func1Addr, func2Addr;
var ABS_HANDLER = ptr(0xc276018);
var ABS_FUNC1   = ptr(0xc354228);
var ABS_FUNC2   = ptr(0xc35442c);
var REF_BASE    = ptr(0xc19c000); // 绝对地址对应的参考基址

try {
    var libtestcpp = Process.getModuleByName("libtestcpp.so");
    var base = libtestcpp.base;
    handlerAddr = base.add(ABS_HANDLER.sub(REF_BASE));
    func1Addr   = base.add(ABS_FUNC1.sub(REF_BASE));
    func2Addr   = base.add(ABS_FUNC2.sub(REF_BASE));
    send({t: 'info', msg: '方式1: 从libtestcpp.so基址计算'});
    send({t: 'info', msg: '  base: ' + base});
} catch(e) {
    send({t: 'warn', msg: 'libtestcpp.so 未找到，尝试搜索模块...'});
    // 枚举模块找到包含handler地址的那个
    var found = false;
    Process.enumerateModules().forEach(function(m) {
        if (found) return;
        if (ABS_HANDLER.compare(m.base) >= 0 && ABS_HANDLER.compare(m.base.add(m.size)) < 0) {
            var b = m.base;
            handlerAddr = b.add(ABS_HANDLER.sub(REF_BASE));
            func1Addr   = b.add(ABS_FUNC1.sub(REF_BASE));
            func2Addr   = b.add(ABS_FUNC2.sub(REF_BASE));
            send({t: 'info', msg: '方式2: 从模块 ' + m.name + ' 计算'});
            send({t: 'info', msg: '  base: ' + b + ' size: ' + m.size});
            found = true;
        }
    });
    if (!found) {
        send({t: 'warn', msg: '未找到匹配模块，使用绝对地址'});
        handlerAddr = ABS_HANDLER;
        func1Addr   = ABS_FUNC1;
        func2Addr   = ABS_FUNC2;
    }
}

send({t: 'info', msg: 'handler: ' + handlerAddr});
send({t: 'info', msg: 'func1:   ' + func1Addr});
send({t: 'info', msg: 'func2:   ' + func2Addr});

// === Step 1: 找游戏socket fd ===
var gameFd = -1;
var sessionKey = 0;
var portalCallCount = 0;
var capturedParams = [];  // 保存每次handler调用的参数

function findGameFd() {
    var getpeernamePtr = libc.getExportByName("getpeername");
    if (!getpeernamePtr) return -1;
    var getpeername = new NativeFunction(getpeernamePtr, "int", ["int", "pointer", "pointer"]);

    for (var fd = 30; fd <= 200; fd++) {
        try {
            var addr = Memory.alloc(128);
            var addrLen = Memory.alloc(4);
            addrLen.writeInt(128);
            if (getpeername(fd, addr, addrLen) === 0) {
                var family = addr.readU16();
                if (family === 2) { // AF_INET
                    var port = ((addr.add(2).readU8() << 8) | addr.add(3).readU8());
                    if (port === 30002) {
                        send({t: 'fd_found', fd: fd});
                        return fd;
                    }
                }
            }
        } catch (e) {}
    }
    return -1;
}

gameFd = findGameFd();
if (gameFd < 0) {
    send({t: 'warn', msg: '未找到游戏socket fd=30002，将从send调用中自动检测'});
}

function isGameFd(fd) {
    if (gameFd > 0) return fd === gameFd;
    return false;
}

// === Step 2: Hook send — 抓传送包 + 自动检测fd和key ===
Interceptor.attach(libc.getExportByName("send"), {
    onEnter: function(args) {
        var fd = args[0].toInt32();
        var buf = args[1];
        var len = args[2].toInt32();

        // 自动检测游戏fd
        if (gameFd < 0 && len >= 10 && len <= 500) {
            gameFd = fd;
            send({t: 'fd_found', fd: fd, msg: '从send()自动检测到游戏fd'});
        }
        if (!isGameFd(fd)) return;

        // 自动检测XOR密钥 (17B心跳包 byte0=0x01)
        if (sessionKey === 0 && len === 17) {
            var tryKey = buf.readU8() ^ 0x01;
            if (tryKey > 0 && tryKey < 256) {
                sessionKey = tryKey;
                send({t: 'key_found', key: sessionKey, hex: '0x' + tryKey.toString(16)});
            }
        }

        // 检测传送包: 29B, type=0x03 (plain)
        if (len === 29 && sessionKey > 0) {
            var ptype = buf.readU8() ^ sessionKey;
            if (ptype === 0x03) {
                var plain = '';
                for (var i = 0; i < len; i++) {
                    plain += ('0' + (buf.add(i).readU8() ^ sessionKey).toString(16)).slice(-2);
                }
                send({t: 'portal_packet', plain: plain, callIndex: portalCallCount,
                    msg: '=== 传送包已发送 (' + len + 'B) ==='});

                // 详细字节分解
                var detail = 'Byte分解:\n';
                for (var j = 0; j < len; j++) {
                    var b = parseInt(plain.substring(j*2, j*2+2), 16);
                    detail += '  [' + j + ']=0x' + ('0' + b.toString(16)).slice(-2) + ' (' + b + ')\n';
                }
                send({t: 'portal_detail', detail: detail});
            }
        }
    }
});

// === Step 3: Hook recv — 自动检测key (备用) ===
Interceptor.attach(libc.getExportByName("recv"), {
    onEnter: function(args) {
        this.fd = args[0].toInt32();
        this.buf = args[1];
        this.doProcess = isGameFd(this.fd);
    },
    onLeave: function(ret) {
        if (!this.doProcess) return;
        var realLen = ret.toInt32();
        if (realLen <= 4) return;

        if (sessionKey === 0) {
            var b0 = this.buf.readU8();
            var b1 = this.buf.add(1).readU8();
            var b2 = this.buf.add(2).readU8();
            var b3 = this.buf.add(3).readU8();
            if (b1 === b2 && b2 === b3) {
                var tryKey = b0 ^ 0x02;
                if (tryKey > 0 && tryKey < 256) {
                    sessionKey = tryKey;
                    send({t: 'key_found', key: sessionKey, side: 'recv', hex: '0x' + tryKey.toString(16)});
                }
            }
        }
    }
});

// === Step 4: 反汇编handler函数 (前60条指令) ===
function disasmAt(addr, count, label) {
    var result = [];
    var cursor = addr;
    for (var i = 0; i < count; i++) {
        try {
            var insn = Instruction.parse(cursor);
            var bytes = '';
            var arr = new Uint8Array(cursor.readByteArray(insn.size));
            for (var j = 0; j < insn.size; j++) {
                bytes += ('0' + arr[j].toString(16)).slice(-2);
            }
            result.push({
                offset: cursor.sub(addr).toInt32(),
                addr: cursor.toString(),
                bytes: bytes,
                asm: insn.mnemonic + ' ' + insn.operands
            });
            cursor = cursor.add(insn.size);
        } catch(e) {
            result.push({offset: cursor.sub(addr).toInt32(), err: e.toString()});
            cursor = cursor.add(2);
        }
    }
    send({t: 'disasm', label: label, addr: addr.toString(), instructions: result});
    return result;
}

// === Step 5: Hook handler — 核心！抓取调用参数 ===
try {
    Interceptor.attach(handlerAddr, {
        onEnter: function(args) {
            portalCallCount++;
            var params = {
                count: portalCallCount,
                r0: args[0].toString(),
                r1: args[1].toString(),
                r2: args[2].toString(),
                r3: args[3].toString(),
                lr: this.context.lr.toString(),
                sp: this.context.sp.toString(),
                time: Date.now()
            };

            // 尝试读字符串参数 (URL等)
            // 试args[1] (可能是URL指针的指针)
            try {
                if (args[1] && !args[1].isNull()) {
                    // 可能是指向指针的指针
                    var ptr1 = args[1].readPointer();
                    if (ptr1 && !ptr1.isNull()) {
                        var str1 = ptr1.readCString();
                        if (str1 && str1.length > 0 && str1.length < 500) {
                            params.url = str1;
                            send({t: 'handler_url', url: str1, count: portalCallCount,
                                msg: '>>> 发现URL: ' + str1});
                        }
                    }
                    // 也可能是直接字符串
                    var str1d = args[1].readCString();
                    if (str1d && str1d.length > 0 && str1d.length < 500 && !params.url) {
                        params.url = str1d;
                        send({t: 'handler_url', url: str1d, count: portalCallCount,
                            msg: '>>> 发现URL(direct): ' + str1d});
                    }
                }
            } catch(e) {}

            // 试args[0] (handlerObj — 可能包含map info)
            try {
                if (args[0] && !args[0].isNull()) {
                    // 读前32字节看结构
                    var dump = '';
                    for (var di = 0; di < 32; di++) {
                        dump += ('0' + args[0].add(di).readU8().toString(16)).slice(-2);
                    }
                    params.objDump = dump;
                }
            } catch(e) {}

            // 试args[2]
            try {
                if (args[2] && !args[2].isNull()) {
                    var str2 = args[2].readCString();
                    if (str2 && str2.length > 0 && str2.length < 500) {
                        params.arg2Str = str2;
                        send({t: 'handler_str2', str: str2, count: portalCallCount});
                    }
                }
            } catch(e) {}

            capturedParams.push(params);

            send({t: 'handler_enter',
                count: portalCallCount,
                r0: params.r0,
                r1: params.r1,
                r2: params.r2,
                r3: params.r3,
                lr: params.lr,
                url: params.url || '(未识别)',
                objDump: params.objDump || '(无)',
                msg: '=== HANDLER 被调用! #' + portalCallCount + ' ==='
            });
        },
        onLeave: function(ret) {
            send({t: 'handler_leave', count: portalCallCount, ret: ret.toString()});
        }
    });
    send({t: 'info', msg: '[OK] handler hook 已安装'});
} catch(e) {
    send({t: 'error', msg: 'handler hook 失败: ' + e});
}

// === Step 6: Hook func1 (初始化函数) ===
try {
    Interceptor.attach(func1Addr, {
        onEnter: function(args) {
            send({t: 'func1_enter',
                r0: args[0].toString(), r1: args[1].toString(),
                r2: args[2].toString(), r3: args[3].toString(),
                msg: '--- func1 被调用 ---'
            });
        },
        onLeave: function(ret) {
            send({t: 'func1_leave', ret: ret.toString()});
        }
    });
    send({t: 'info', msg: '[OK] func1 hook 已安装'});
} catch(e) {
    send({t: 'error', msg: 'func1 hook 失败: ' + e});
}

// === Step 7: Hook func2 (构造包) ===
try {
    Interceptor.attach(func2Addr, {
        onEnter: function(args) {
            send({t: 'func2_enter',
                r0: args[0].toString(), r1: args[1].toString(),
                r2: args[2].toString(), r3: args[3].toString(),
                msg: '--- func2 被调用 ---'
            });
        },
        onLeave: function(ret) {
            send({t: 'func2_leave', ret: ret.toString()});
        }
    });
    send({t: 'info', msg: '[OK] func2 hook 已安装'});
} catch(e) {
    send({t: 'error', msg: 'func2 hook 失败: ' + e});
}

// === Step 8: 反汇编handler (了解内部逻辑) ===
disasmAt(handlerAddr, 50, 'handler');
disasmAt(func1Addr, 40, 'func1');
disasmAt(func2Addr, 40, 'func2');

// === RPC — 供Python端调用 ===
rpc.exports = {
    // 获取当前状态
    getStatus: function() {
        return JSON.stringify({
            gameFd: gameFd,
            sessionKey: sessionKey,
            portalCallCount: portalCallCount,
            handlerAddr: handlerAddr.toString(),
            func1Addr: func1Addr.toString(),
            func2Addr: func2Addr.toString(),
            capturedCount: capturedParams.length
        });
    },

    // 获取最近一次handler调用的参数
    getLastCall: function() {
        if (capturedParams.length === 0) return JSON.stringify({error: '还没有handler被调用'});
        return JSON.stringify(capturedParams[capturedParams.length - 1]);
    },

    // 获取所有handler调用记录
    getAllCalls: function() {
        return JSON.stringify(capturedParams);
    },

    // 尝试直接调用handler — 用自定义URL跳图
    tryCallHandler: function(urlStr) {
        if (!urlStr) return '用法: tryCallHandler("xqj://map?name=目标地图")';
        if (capturedParams.length === 0) return '错误: 还没有抓取到handlerObj，请先走一次传送门';

        // 用上次抓到的handlerObj (R0)
        var lastCall = capturedParams[capturedParams.length - 1];
        var handlerObj = ptr(lastCall.r0);

        // 构造URL
        var url = Memory.allocUtf8String(urlStr);
        var urlPtr = Memory.alloc(4);
        urlPtr.writePointer(url);

        // 调用handler
        try {
            var handlerFn = new NativeFunction(handlerAddr, 'void', ['pointer', 'pointer']);
            handlerFn(handlerObj, urlPtr);
            return '已调用 handler("' + urlStr + '"), handlerObj=' + handlerObj;
        } catch(e) {
            return '调用失败: ' + e;
        }
    },

    // 尝试调用 — 完整模拟 (先用func1初始化，再用handler)
    tryCallFull: function(urlStr) {
        if (!urlStr) return '用法: tryCallFull("xqj://map?name=目标地图")';

        // func1 可能是创建初始化结构的
        // 分配一些内存给handlerObj
        var handlerObj = Memory.alloc(256);
        var url = Memory.allocUtf8String(urlStr);
        var urlPtr = Memory.alloc(4);
        urlPtr.writePointer(url);

        try {
            // 先调func1初始化
            var func1Fn = new NativeFunction(func1Addr, 'pointer', ['pointer', 'pointer']);
            var initRet = func1Fn(handlerObj, urlPtr);
            send({t: 'try_call', msg: 'func1 返回: ' + initRet});

            // 再调handler
            var handlerFn = new NativeFunction(handlerAddr, 'void', ['pointer', 'pointer']);
            handlerFn(handlerObj, urlPtr);

            return '已调用 func1 + handler("' + urlStr + '")';
        } catch(e) {
            return '调用失败: ' + e;
        }
    },

    // 获取密钥
    getKey: function() { return sessionKey; }
};

// === 完成 ===
send({t: 'ready',
    msg: '========================================',
    msg2: '诊断脚本就绪！请操作：',
    msg3: '',
    msg4: '【步骤1】在游戏中点击任意传送门走一次',
    msg5: '   -> 观察控制台输出：handler_enter / func1 / func2 / portal_packet',
    msg6: '',
    msg7: '【步骤2】走完后看控制台，确认抓到了：',
    msg8: '   - handler的URL参数 (handler_url)',
    msg9: '   - 传送包明文 (portal_packet)',
    msg10: '   - 函数调用顺序',
    msg11: '',
    msg12: '【步骤3】然后运行 tryCallHandler("xqj://map?name=地图名") 尝试直接跳图',
    msg13: '========================================',
    gameFd: gameFd,
    key: sessionKey
});
