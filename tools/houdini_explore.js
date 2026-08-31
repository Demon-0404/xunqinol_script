// Explore libhoudini.so internals to find ARM->x86 translation table
var houdini = Process.getModuleByName("libhoudini.so");

send({t: 'log', msg: 'libhoudini.so: base=' + houdini.base + ' size=' + houdini.size});

// List all exports
var exports = houdini.enumerateExports();
send({t: 'log', msg: 'Total exports: ' + exports.length});

// Filter for interesting exports
var interesting = [];
for (var i = 0; i < exports.length; i++) {
    var name = exports[i].name;
    if (name && (name.indexOf('find') !== -1 ||
                 name.indexOf('lookup') !== -1 ||
                 name.indexOf('translate') !== -1 ||
                 name.indexOf('get') !== -1 ||
                 name.indexOf('code') !== -1 ||
                 name.indexOf('cache') !== -1 ||
                 name.indexOf('hook') !== -1 ||
                 name.indexOf('dispatch') !== -1 ||
                 name.indexOf('call') !== -1 ||
                 name.indexOf('arm') !== -1 ||
                 name.indexOf('mapping') !== -1 ||
                 name.indexOf('table') !== -1 ||
                 name.indexOf('symbol') !== -1 ||
                 name.indexOf('addr') !== -1)) {
        interesting.push(exports[i]);
    }
}

send({t: 'log', msg: 'Interesting exports (' + interesting.length + '):'});
for (var j = 0; j < interesting.length; j++) {
    send({t: 'log', msg: '  ' + interesting[j].name + ' @ ' + interesting[j].address});
}

// Also look at the close() caller — offset 0x2b006e in libhoudini
var closeCaller = houdini.base.add(0x2b006e);
send({t: 'log', msg: 'Close caller in houdini: ' + closeCaller});

// Check what's around that address — any symbols nearby?
for (var k = 0; k < exports.length; k++) {
    var diff = exports[k].address.sub(closeCaller).toInt32();
    if (Math.abs(diff) < 0x1000) {
        send({t: 'log', msg: '  Nearby: ' + exports[k].name + ' @ ' + exports[k].address + ' (diff=' + diff + ')'});
    }
}

// Scan code cache region: 0x0d130000-0x11078000
var cacheStart = ptr(0x0d130000);
var cacheEnd = ptr(0x11078000);
var cacheSize = cacheEnd.sub(cacheStart).toInt32();
send({t: 'log', msg: 'Code cache: ' + cacheStart + ' - ' + cacheEnd + ' (' + (cacheSize/1024/1024).toFixed(1) + 'MB)'});

// Try to read from code cache — look for ARM addresses that might be stored as metadata
// The translated code might have ARM address markers
// Actually let's search for known ARM function addresses in the cache

// Known offsets in libtestcpp.so (ARM):
// CCScheduler::update = 0x001a28c9
// CCDirector::sharedDirector = 0x001b8229
// CCApplication::setAnimationInterval = 0x001db495
// AppDelegate::jumpUrl = 0x000da099

// We need to know the base. Let's find libtestcpp.so
var modules = Process.enumerateModules();
var testcpp = null;
for (var m = 0; m < modules.length; m++) {
    if (modules[m].name.indexOf('libtestcpp') !== -1) {
        send({t: 'log', msg: 'Found: ' + modules[m].name + ' base=' + modules[m].base + ' size=' + modules[m].size});
        testcpp = modules[m];
    }
}

if (!testcpp) {
    // Try to get it from memory ranges
    var ranges = Process.enumerateRanges({protection: 'r--', coalesce: true});
    for (var r = 0; r < ranges.length; r++) {
        if (ranges[r].base.toString().indexOf('0c') === 0 && ranges[r].size > 1000000) {
            send({t: 'log', msg: 'Large r-- region: ' + ranges[r].base + ' size=' + ranges[r].size});
        }
    }

    // Alternative: look for rwxp regions
    var execRanges = Process.enumerateRanges({protection: 'rwx', coalesce: true});
    for (var er = 0; er < execRanges.length; er++) {
        send({t: 'log', msg: 'rwx region: ' + execRanges[er].base + ' size=' + (execRanges[er].size/1024/1024).toFixed(1) + 'MB'});
    }
}

send({t: 'ready', msg: 'houdini explore done'});
