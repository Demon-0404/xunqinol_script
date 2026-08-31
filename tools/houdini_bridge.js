// Explore NativeBridgeItf — the Android NativeBridge interface
// This provides getTrampoline() which can resolve ARM symbols to callable function pointers

var houdini = Process.getModuleByName("libhoudini.so");

// Find NativeBridgeItf variable
var exports = houdini.enumerateExports();
var nativeBridgeItf = null;
for (var i = 0; i < exports.length; i++) {
    if (exports[i].name === 'NativeBridgeItf') {
        nativeBridgeItf = exports[i].address;
        send({t: 'log', msg: 'NativeBridgeItf @ ' + nativeBridgeItf});
        break;
    }
}

if (!nativeBridgeItf) {
    send({t: 'err', msg: 'NativeBridgeItf not found!'});
} else {
    // NativeBridgeItf is a pointer to a struct of function pointers (NativeBridgeCallbacks)
    // Structure (from AOSP):
    //   uint32_t version;
    //   void* loadLibrary(const char* libpath, int flag);        // +4 or +8
    //   void* getTrampoline(void* handle, const char* name, ...) // +8 or +16
    //   bool isSupported(const char* libpath);                   // +12 or +24
    //   const struct NativeBridgeRuntimeValues* getRuntimeValues(); // +16 or +32

    // Read first 64 bytes of the interface structure
    try {
        var ifacePtr = nativeBridgeItf.readPointer();
        send({t: 'log', msg: 'Interface pointer: ' + ifacePtr});

        if (!ifacePtr.isNull()) {
            var bytes = ifacePtr.readByteArray(128);
            var arr = new Uint8Array(bytes);

            // Print hex dump
            for (var j = 0; j < 128; j += 16) {
                var line = ('0000' + j.toString(16)).slice(-4) + ': ';
                for (var k = 0; k < 16 && (j + k) < 128; k++) {
                    line += ('0' + arr[j + k].toString(16)).slice(-2) + ' ';
                }
                send({t: 'log', msg: line});
            }

            // Read function pointers (8 bytes each on 64-bit)
            // version: uint32 at offset 0
            var version = arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
            send({t: 'log', msg: 'Version: ' + version});

            // Function pointers start at offset 8 (after version + padding on 64-bit)
            for (var fi = 0; fi < 8; fi++) {
                var off = 8 + fi * 8;
                if (off + 7 < 128) {
                    var lo = arr[off] | (arr[off+1] << 8) | (arr[off+2] << 16) | (arr[off+3] << 24);
                    var hi = arr[off+4] | (arr[off+5] << 8) | (arr[off+6] << 16) | (arr[off+7] << 24);
                    if (lo !== 0 || hi !== 0) {
                        // Combine into 64-bit pointer (little-endian)
                        // hi is high 32 bits, lo is low 32 bits
                        var funcPtr = ptr(lo).add(ptr(hi).mul(0x100000000));
                        send({t: 'log', msg: '  fn[' + fi + ']: ' + funcPtr});
                    }
                }
            }
        }
    } catch(e) {
        send({t: 'err', msg: 'Error reading NativeBridgeItf: ' + e});
    }
}

// Also: try to call getTrampoline directly if we can find it
// First, try to read it from the right offset
// The NativeBridgeCallbacks signature from AOSP:
//   version (4 bytes) + padding (4 bytes on 64-bit) = 8 bytes
//   loadLibrary (8 bytes) → offset 8
//   getTrampoline (8 bytes) → offset 16
//   isSupported (8 bytes) → offset 24
//   getRuntimeValues (8 bytes) → offset 32

// Let's try to read getTrampoline at offset 16
try {
    var ifacePtr = nativeBridgeItf.readPointer();
    if (!ifacePtr.isNull()) {
        var getTrampolinePtr = ifacePtr.add(16).readPointer();
        send({t: 'log', msg: 'getTrampoline @ ' + getTrampolinePtr});

        if (!getTrampolinePtr.isNull()) {
            // Try to call getTrampoline to find a known function
            // getTrampoline(void* handle, const char* name, const char* shorty, uint32_t len)
            // handle = result of loadLibrary (we might need to find it)
            // name = symbol name
            // shorty = JNI shorty descriptor (irrelevant for non-JNI)
            // len = length of shorty

            // We might need a library handle. Let's try to get it.
            // The game loads libtestcpp.so through NativeBridge.
            // The handle might be stored somewhere...

            send({t: 'log', msg: 'Looking for library handles...'});

            // Try reading the loadLibrary function pointer
            var loadLibraryPtr = ifacePtr.add(8).readPointer();
            send({t: 'log', msg: 'loadLibrary @ ' + loadLibraryPtr});
        }
    }
} catch(e) {
    send({t: 'err', msg: 'Error reading getTrampoline: ' + e});
}

// Alternative: find the translation table structure more precisely
// The table entries we found earlier were at 0xe02ee6b0
// Let's examine the structure as 16-byte entries (full 64-bit pointers)
send({t: 'log', msg: '=== Table as 16-byte entries ==='});
var tableAddr = ptr(0xe02ee6b0);
for (var ti = 0; ti < 8; ti++) {
    var addr = tableAddr.add(ti * 16);
    try {
        var armPtr = addr.readPointer();
        var x86Ptr = addr.add(8).readPointer();
        var armInTestcpp = armPtr.compare(ptr(0xc074000)) >= 0 && armPtr.compare(ptr(0xc4f4000)) <= 0;
        var x86InCache = x86Ptr.compare(ptr(0xd120000)) >= 0 && x86Ptr.compare(ptr(0x11078000)) <= 0;
        var label = (armInTestcpp && x86InCache) ? ' <<< VALID MAPPING' :
                    (armInTestcpp && x86Ptr.isNull()) ? ' untranslated' : '';
        send({t: 'log', msg: '  [' + ti + '] ARM=' + armPtr + ' x86=' + x86Ptr + label});
    } catch(e) {
        send({t: 'log', msg: '  [' + ti + '] error: ' + e});
    }
}

send({t: 'ready', msg: 'bridge exploration done'});
