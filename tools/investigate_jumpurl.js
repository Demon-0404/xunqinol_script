// Investigate jlapp_jumpUrl and g_jumpUrlCall
var base = ptr(0xc074000);

// Read memory around the string location for context
var jumpUrlStr = ptr(0xc0a38cd); // "_ZN11AppDelegate7jumpUrlEPKc" string
var jlappJumpUrl = ptr(0xc0c2e23); // "jlapp_jumpUrl" string
var gJumpUrlCall = ptr(0xc0c2e31); // "g_jumpUrlCall" string

// These strings are in the .dynstr section. Let's find their offset
send({t: 'log', msg: 'jlapp_jumpUrl string @ ' + jlappJumpUrl + ' (off=0x' + jlappJumpUrl.sub(base).toString(16) + ')'});
send({t: 'log', msg: 'g_jumpUrlCall string @ ' + gJumpUrlCall + ' (off=0x' + gJumpUrlCall.sub(base).toString(16) + ')'});

// Now search for these names in the dynamic symbol table
// Looking for entries where st_name points to these strings
var jlappOff = jlappJumpUrl.sub(base).toInt32();
var gJumpOff = gJumpUrlCall.sub(base).toInt32();

// Scan memory for st_name values that match
// Each symbol entry is 16 bytes: st_name(4) + st_value(4) + st_size(4) + st_info(1) + st_other(1) + st_shndx(2)
// st_name is an index into .dynstr, not an absolute address
// So st_name = string_offset - dynstr_base

// Find dynstr base by looking at the .dynstr section
// The .dynstr typically starts with \0 followed by symbol names
// Let's search for the start of .dynstr

// Read a few bytes around the found strings
send({t: 'log', msg: 'Bytes around g_jumpUrlCall:'});
var ctx = gJumpUrlCall.sub(16).readByteArray(48);
var arr = new Uint8Array(ctx);
for (var i = 0; i < 48; i += 16) {
    var line = '';
    for (var j = 0; j < 16 && (i+j) < 48; j++) {
        line += ('0' + arr[i+j].toString(16)).slice(-2) + ' ';
    }
    send({t: 'log', msg: '  ' + line});
}

// Also check what's at the dynstr base that would make st_name indices match
// If these strings are at known offsets from the dynstr start,
// we can find the symbol entries

// Let's read around "jlapp_jumpUrl" to find nearby symbols
send({t: 'log', msg: '--- Nearby strings around jlapp_jumpUrl ---'});
var nearby = jlappJumpUrl.sub(64);
try {
    var nearbyData = nearby.readByteArray(192);
    var narr = new Uint8Array(nearbyData);
    var currentStr2 = '';
    for (var bi = 0; bi < narr.length; bi++) {
        var c = narr[bi];
        if (c >= 32 && c <= 126) {
            currentStr2 += String.fromCharCode(c);
        } else if (c === 0 && currentStr2.length > 3) {
            var strAddr = nearby.add(bi - currentStr2.length);
            send({t: 'log', msg: '  ' + strAddr + ' (off=0x' + strAddr.sub(base).toString(16) + '): "' + currentStr2 + '"'});
            currentStr2 = '';
        } else {
            currentStr2 = '';
        }
    }
} catch(e) {}

// Now let's explicitly find the symbol for jumpUrl by scanning for st_name patterns
// STRING OFFSETS (from base):
// jlapp_jumpUrl: 0xc0c2e23 - 0xc074000 = 0x4ae23
// g_jumpUrlCall: 0xc0c2e31 - 0xc074000 = 0x4ae31

// Search .dynsym for entries with these st_name values
// .dynsym would need its string base determined first

// Find .dynstr base by looking for the first string
// The first byte of .dynstr is \0, then strings follow
// Let's look for the dynstr section: search backwards from jlapp string for \0\0\0...\0 pattern
// Actually, the dynstr has all strings concatenated, starting at some address

// Let's try a different approach: read the data at the start of dynstr (which is a \0 byte)
// Find it by scanning for the right pattern

// Or simpler: look at the ANDROID section headers or program headers
// Actually, let me just read the DYNAMIC section which has DT_STRTAB and DT_SYMTAB entries

// The .dynamic section contains DT_* entries that point to .dynstr and .dynsym
// Let's find the .dynamic section by reading the program headers

function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

// Read program headers (ARM ELF32)
var e_phoff = readU32(base.add(28));
var e_phnum = readU16(base.add(44));

send({t: 'log', msg: 'Program headers: phoff=0x' + e_phoff.toString(16) + ' phnum=' + e_phnum});

var dynamicAddr = 0;
var dynamicSize = 0;

for (var pi = 0; pi < e_phnum; pi++) {
    var phdr = base.add(e_phoff + pi * 32); // ARM Elf32_Phdr = 32 bytes
    var p_type = readU32(phdr);
    var p_offset = readU32(phdr.add(4));
    var p_vaddr = readU32(phdr.add(8));
    var p_filesz = readU32(phdr.add(16));
    var p_memsz = readU32(phdr.add(20));

    if (p_type === 2) { // PT_DYNAMIC
        dynamicAddr = p_vaddr;
        dynamicSize = p_filesz;
        send({t: 'log', msg: 'Found PT_DYNAMIC: vaddr=0x' + p_vaddr.toString(16) + ' filesz=' + p_filesz});
    }
}

if (dynamicAddr > 0) {
    // Parse .dynamic section
    // Each entry: d_tag(4) + d_val(4) = 8 bytes
    var dynstrAddr = 0, dynstrSize = 0;
    var dynsymAddr = 0, dynsymSize = 0;

    for (var di = 0; di < dynamicSize; di += 8) {
        var d_tag = readU32(base.add(dynamicAddr + di));
        var d_val = readU32(base.add(dynamicAddr + di + 4));

        if (d_tag === 5) { // DT_STRTAB
            dynstrAddr = d_val;
            send({t: 'log', msg: 'DT_STRTAB = 0x' + d_val.toString(16)});
        }
        if (d_tag === 6) { // DT_SYMTAB
            dynsymAddr = d_val;
            send({t: 'log', msg: 'DT_SYMTAB = 0x' + d_val.toString(16)});
        }
        if (d_tag === 10) { // DT_STRSZ
            dynstrSize = d_val;
            send({t: 'log', msg: 'DT_STRSZ = ' + d_val});
        }
        if (d_tag === 0) break; // DT_NULL
    }

    if (dynsymAddr > 0 && dynstrAddr > 0) {
        // Now find symbols!
        // Also search for key target functions
        var targetStrs = {
            'jlapp_jumpUrl':       {off: 0x4ee23, found: false},
            'g_jumpUrlCall':        {off: 0x4ee31, found: false},
            'CCDirector::sharedDirector': {off: 0x2f208, found: false},
            'CCApplication::sharedApplication': {off: 0x2f277, found: false},
            'AppDelegate::jumpUrl': {off: 0x2f8cd, found: false},
            'CCApplication::setAnimationInterval': {off: 0x30500, found: false},
            'CCScheduler::update':  {off: 0x323c6, found: false},
            'CCDirector::replaceScene': {off: 0x3383d, found: false},
        };

        // Convert to name_idx
        var targetMap = {};
        for (var ts in targetStrs) {
            targetMap[targetStrs[ts].off - dynstrAddr] = ts;
        }

        // Scan all dynamic symbols
        var symEntSize = 16; // Elf32_Sym
        var symOff = dynsymAddr;
        var si = 0;

        while (true) {
            var sym = base.add(symOff + si * symEntSize);
            var st_name = readU32(sym);

            var targetName = targetMap[st_name];
            if (targetName) {
                var st_value = readU32(sym.add(4));
                var st_size = readU32(sym.add(8));
                var st_info = sym.add(12).readU8();
                var st_shndx = readU16(sym.add(14));
                send({t: 'log', msg: '*** FOUND ' + targetName + ': st_value=0x' + st_value.toString(16) +
                    ' st_size=' + st_size + ' st_info=0x' + st_info.toString(16) +
                    ' st_shndx=' + st_shndx});
                targetStrs[targetName].found = true;
                targetStrs[targetName].value = st_value;
                targetStrs[targetName].size = st_size;
                targetStrs[targetName].info = st_info;
                targetStrs[targetName].shndx = st_shndx;
            }

            // Check for likely end of symbol table
            if (st_name === 0 && si > 100) {
                // st_name=0 is the initial null entry; subsequent null entries suggest end
                var allZero = true;
                for (var zi = 0; zi < 4; zi++) {
                    if (sym.add(zi).readU8() !== 0) { allZero = false; break; }
                }
                if (allZero && sym.add(4).readU8() === 0) break;
            }
            si++;
            if (si > 20000) break; // safety limit
        }

        send({t: 'log', msg: 'Scanned ' + si + ' symbols'});

        // Summary
        send({t: 'log', msg: '=== SYMBOL SEARCH RESULTS ==='});
        for (var ts2 in targetStrs) {
            var t = targetStrs[ts2];
            if (t.found) {
                var absAddr = base.add(t.value);
                send({t: 'log', msg: '  ' + ts2 + ': OFFSET=0x' + t.value.toString(16) +
                    ' ABS=' + absAddr + ' size=' + t.size});
            } else {
                send({t: 'log', msg: '  ' + ts2 + ': NOT FOUND'});
            }
        }

        // Extra: read the g_jumpUrlCall global variable if found
        if (targetStrs['g_jumpUrlCall'] && targetStrs['g_jumpUrlCall'].found) {
            var gVarAddr = base.add(targetStrs['g_jumpUrlCall'].value);
            send({t: 'log', msg: 'Reading g_jumpUrlCall at ' + gVarAddr + '...'});
            try {
                var gVal = gVarAddr.readPointer();
                send({t: 'log', msg: '  value (ptr): ' + gVal});
            } catch(e2) {
                try {
                    var gBytes2 = gVarAddr.readByteArray(4);
                    var gArr2 = new Uint8Array(gBytes2);
                    var val32 = gArr2[0] | (gArr2[1] << 8) | (gArr2[2] << 16) | (gArr2[3] << 24);
                    send({t: 'log', msg: '  value (u32): 0x' + val32.toString(16)});
                } catch(e3) {
                    send({t: 'err', msg: 'Cannot read: ' + e3});
                }
            }
        }
    }
}

// Also look for important functions using their string offsets
function readU16(addr) {
    var bytes = addr.readByteArray(2);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8);
}

send({t: 'ready', msg: 'jumpUrl investigation done'});
