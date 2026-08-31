// Simple approach: search libtestcpp.so memory for C++ mangled names
var base = ptr(0xc074000);
var size = 0x480000; // 4.5MB

// Key C++ mangled names to find
var mangledNames = [
    // CCDirector
    'sharedDirector',
    'getRunningScene',
    // CCApplication
    'sharedApplication',
    'setAnimationInterval',
    // CCScheduler
    'CCScheduler',
    // AppDelegate
    'jumpUrl',
    'AppDelegate',
    // Movement/position related
    'Movement',
    'CTwMovement',
    // Scene management
    'replaceScene',
    'runWithScene',
    'pushScene',
    // Position
    'setPosition',
    'getPosition',
];

send({t: 'log', msg: 'Searching for strings in libtestcpp.so...'});

// Read the file in chunks and search for strings
var chunkSize = 1048576; // 1MB
var offset = 0;
var found = {};

while (offset < size) {
    var readSize = Math.min(chunkSize, size - offset);
    try {
        var data = base.add(offset).readByteArray(readSize);
        if (!data) { offset += chunkSize; continue; }

        var arr = new Uint8Array(data);

        // Extract all null-terminated strings from this chunk
        var currentStr = '';
        for (var bi = 0; bi < arr.length; bi++) {
            var c = arr[bi];
            if (c >= 32 && c <= 126) {
                // Printable ASCII — check for beginning of a symbol name
                // C++ mangled names start with _Z
                currentStr += String.fromCharCode(c);
                if (currentStr.length > 200) {
                    // String too long, reset
                    currentStr = '';
                }
            } else if (c === 0 && currentStr.length > 0) {
                // Null terminator — check the string
                var addr = base.add(offset + bi - currentStr.length);

                for (var mi = 0; mi < mangledNames.length; mi++) {
                    if (currentStr.indexOf(mangledNames[mi]) !== -1) {
                        if (!found[currentStr]) {
                            found[currentStr] = addr;
                            send({t: 'log', msg: '  FOUND: "' + currentStr + '" @ ' + addr});
                        }
                    }
                }
                currentStr = '';
            } else if (c < 32 || c > 126) {
                currentStr = '';
            }
        }

    } catch(e) {
        // Silently skip unreadable chunks
    }
    offset += chunkSize;
}

send({t: 'log', msg: 'Total unique matches: ' + Object.keys(found).length});

// Now try to find the DYNSYM section and associated symbol addresses
// For each interesting string we found, search backwards for the symbol table entry

// Actually, let's try a different approach:
// Find the dynstr section by signature and extract all symbol names with addresses

// The .dynsym typically comes right before .dynstr in memory
// Each entry is 16 bytes: st_name(4) + st_value(4) + st_size(4) + st_info(1) + st_other(1) + st_shndx(2)

// Let's search for the dynstr signature: lots of null-terminated C++ names
// And then work backwards to find dynsym

// First, let's look for any reasonable dynstr region by scanning for _Z at word boundaries
send({t: 'log', msg: 'Looking for dynamic symbol table...'});

// The .dynsym section has specific layout. Let's look for st_value patterns
// that match valid ARM addresses (0x0c074000 - 0x0c4f4000)

// Scan for sequences of (name_offset, value_in_libtestcpp_range, 0, type_byte)
// This pattern indicates a valid symbol table entry

var candidateSyms = [];
var scanStep = 16; // size of one symbol entry = 16 bytes

for (var off = 0; off < size; off += scanStep) {
    try {
        var addr = base.add(off);
        var sv = readU32(addr.add(4)); // st_value
        var ss = readU32(addr.add(8)); // st_size
        var si = addr.add(12).readU8(); // st_info

        // st_value should be in libtestcpp.so range (valid function address)
        if (sv >= 0xc074000 && sv <= 0xc4f4000 && (si & 0xf) === 2) {
            // FUNC type symbol with valid address
            candidateSyms.push({off: off, val: sv, size: ss, info: si});
        }
    } catch(e) {}
}

send({t: 'log', msg: 'Found ' + candidateSyms.length + ' candidate symbols (FUNC type with valid address)'});

// Show first few
for (var ci = 0; ci < Math.min(candidateSyms.length, 20); ci++) {
    var cs = candidateSyms[ci];
    var symAddr = base.add(cs.off);
    var st_name = readU32(symAddr);
    send({t: 'log', msg: '  [' + ci + '] off=0x' + cs.off.toString(16) + ' name_idx=' + st_name + ' val=0x' + cs.val.toString(16) + ' size=' + cs.size + ' info=0x' + cs.info.toString(16)});
}

// If we find symbol table, look for our targets using name indices
// For now, let's focus on the strings we already found
// and try to locate their symbol entries

// For strings in the 'found' map, compute their offset in the file
// Then search the candidateSyms for entries whose name_idx points to these strings

for (var fname in found) {
    var strAddr = found[fname];
    var strOff = strAddr.sub(base).toInt32();

    // Search for symbols whose name_idx matches this string
    for (var ci = 0; ci < candidateSyms.length; ci++) {
        var cs = candidateSyms[ci];
        var symAddr = base.add(cs.off);
        var st_name = readU32(symAddr);

        // Check if st_name points to our string (within a few bytes)
        // The dynstr table is at some base, and st_name is an index into it
        // st_name + dynstr_base should equal strOff
        var estimatedDynstrBase = strOff - st_name;
        if (estimatedDynstrBase > 0 && estimatedDynstrBase < size) {
            send({t: 'log', msg: '  SYMBOL for "' + fname + '": val=0x' + cs.val.toString(16) + ' dynstr_base=0x' + estimatedDynstrBase.toString(16)});
            // Also check other symbols with same dynstr base to validate
            break;
        }
    }
}

function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

send({t: 'ready', msg: 'symbol search done'});
