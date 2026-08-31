// Parse libtestcpp.so ELF to find global symbols
var base = ptr(0xc074000);

function readU32(addr) {
    var bytes = addr.readByteArray(4);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8) | (arr[2] << 16) | (arr[3] << 24);
}

function readU16(addr) {
    var bytes = addr.readByteArray(2);
    var arr = new Uint8Array(bytes);
    return arr[0] | (arr[1] << 8);
}

// Read ELF header
var e_ident = base.readByteArray(16);
var ident = new Uint8Array(e_ident);
send({t: 'log', msg: 'ELF magic: ' + String.fromCharCode(ident[1], ident[2], ident[3])});

var e_type = readU16(base.add(16));
var e_machine = readU16(base.add(18));
var e_phoff = readU32(base.add(28)); // program header offset
var e_shoff = readU32(base.add(32)); // section header offset
var e_flags = readU32(base.add(36));
var e_ehsize = readU16(base.add(40));
var e_phentsize = readU16(base.add(42));
var e_phnum = readU16(base.add(44));
var e_shentsize = readU16(base.add(46));
var e_shnum = readU16(base.add(48));
var e_shstrndx = readU16(base.add(50));

send({t: 'log', msg: 'ELF: type=' + e_type + ' machine=' + e_machine + ' phoff=0x' + e_phoff.toString(16) + ' shoff=0x' + e_shoff.toString(16)});
send({t: 'log', msg: '  shnum=' + e_shnum + ' shentsize=' + e_shentsize});

// Read section headers to find shstrtab first
var shstrtabAddr = 0;
var sections = [];
for (var i = 0; i < e_shnum; i++) {
    var shdr = base.add(e_shoff + i * e_shentsize);
    var sh_name = readU32(shdr);
    var sh_type = readU32(shdr.add(4));
    var sh_flags = readU32(shdr.add(8));
    var sh_addr = readU32(shdr.add(12));
    var sh_offset = readU32(shdr.add(16));
    var sh_size = readU32(shdr.add(20));
    var sh_link = readU32(shdr.add(24));
    var sh_info = readU32(shdr.add(28));
    var sh_addralign = readU32(shdr.add(32));
    var sh_entsize = readU32(shdr.add(36));

    sections.push({nameIdx: sh_name, type: sh_type, addr: sh_addr, offset: sh_offset, size: sh_size, entsize: sh_entsize});

    if (i === e_shstrndx) {
        shstrtabAddr = sh_addr;
    }
}

// Now find .symtab, .strtab, .dynsym, .dynstr using sh_addr for access
var symtabAddr = 0, symtabSize = 0, symtabEnt = 0;
var strtabAddr = 0, strtabSize = 0;
var dynsymAddr = 0, dynsymSize = 0, dynsymEnt = 0;
var dynstrAddr = 0, dynstrSize = 0;

for (var i = 0; i < sections.length; i++) {
    var sec = sections[i];

    // Read section name using sh_addr of shstrtab
    var name = '';
    try {
        var nameAddr = base.add(shstrtabAddr + sec.nameIdx);
        var ci = 0;
        while (ci < 32) {
            var c = nameAddr.add(ci).readU8();
            if (c === 0) break;
            name += String.fromCharCode(c);
            ci++;
        }
    } catch(e) {}

    if (name === '.symtab') {
        symtabAddr = sec.addr; symtabSize = sec.size; symtabEnt = sec.entsize;
        send({t: 'log', msg: 'Found .symtab addr=0x' + sec.addr.toString(16) + ' size=' + sec.size + ' entsize=' + sec.entsize});
    }
    if (name === '.strtab') {
        strtabAddr = sec.addr; strtabSize = sec.size;
        send({t: 'log', msg: 'Found .strtab addr=0x' + sec.addr.toString(16) + ' size=' + sec.size});
    }
    if (name === '.dynsym') {
        dynsymAddr = sec.addr; dynsymSize = sec.size; dynsymEnt = sec.entsize;
        send({t: 'log', msg: 'Found .dynsym addr=0x' + sec.addr.toString(16) + ' size=' + sec.size + ' entsize=' + sec.entsize});
    }
    if (name === '.dynstr') {
        dynstrAddr = sec.addr; dynstrSize = sec.size;
        send({t: 'log', msg: 'Found .dynstr addr=0x' + sec.addr.toString(16) + ' size=' + sec.size});
    }
}

// Search symtab for interesting symbols
var searchPatterns = [
    'Director', 'director', 'Shared', 'shared',
    'Application', 'Scheduler', 'scheduler',
    'jumpUrl', 'jump', 'Jump',
    'Movement', 'movement',
    'Scene', 'Layer', 'Sprite',
    'Player', 'player', 'Role',
    'Map', 'map', 'Scene',
];

function searchSymtab(symAddr, symSize, symEnt, strAddr) {
    var count = 0;
    // ARM ELF symbol entry: st_name(4) + st_value(4) + st_size(4) + st_info(1) + st_other(1) + st_shndx(2)
    var numSyms = symSize / symEnt;

    for (var si = 0; si < numSyms; si++) {
        var sym = base.add(symAddr + si * symEnt);
        var st_name = readU32(sym);
        var st_value = readU32(sym.add(4));
        var st_size = readU32(sym.add(8));
        var st_info = sym.add(12).readU8();

        if (st_name === 0) continue;

        // Read symbol name
        var nameAddr = base.add(strAddr + st_name);
        var symName = '';
        var si2 = 0;
        while (si2 < 128) {
            var c = nameAddr.add(si2).readU8();
            if (c === 0) break;
            symName += String.fromCharCode(c);
            si2++;
        }

        // Check if it matches any pattern
        var matched = false;
        for (var pi = 0; pi < searchPatterns.length; pi++) {
            if (symName.indexOf(searchPatterns[pi]) !== -1) {
                matched = true;
                break;
            }
        }

        if (matched && st_value > 0) {
            send({t: 'log', msg: '  ' + symName + ' @ 0x' + st_value.toString(16) + ' size=' + st_size + ' type=' + (st_info & 0xf)});
            count++;
            if (count > 30) {
                send({t: 'log', msg: '  ... (stopped at 30 matches)'});
                return;
            }
        }
    }
}

if (dynsymAddr > 0 && dynstrAddr > 0) {
    send({t: 'log', msg: '=== .dynsym search ==='});
    searchSymtab(dynsymAddr, dynsymSize, dynsymEnt, dynstrAddr);
}

if (symtabAddr > 0 && strtabAddr > 0) {
    send({t: 'log', msg: '=== .symtab search ==='});
    searchSymtab(symtabAddr, symtabSize, symtabEnt, strtabAddr);
}

// Direct approach: find the sharedDirector singleton
// In Cocos2d-x, CCDirector::sharedDirector() stores the singleton as:
// static CCDirector* s_SharedDirector = nullptr;
// The mangled name might be: _ZN10CCDirector15s_SharedDirectorE
// or _ZZN10CCDirector15sharedDirectorEvE16s_SharedDirector

// Let's search for the exact mangled names
var exactNames = [
    '_ZN10CCDirector15sharedDirectorEv',  // CCDirector::sharedDirector()
    '_ZNK10CCDirector16getRunningSceneEv', // CCDirector::getRunningScene()
    '_ZN12CCScheduler6updateEd',           // CCScheduler::update(double)  -- wait, float not double
    '_ZN12CCScheduler6updateEf',           // CCScheduler::update(float)
    '_ZN14CCApplication19sharedApplicationEv', // CCApplication::sharedApplication()
    '_ZN14CCApplication19setAnimationIntervalEd', // CCApplication::setAnimationInterval(double)
    '_ZN10AppDelegate7jumpUrlEPKc',        // AppDelegate::jumpUrl(const char*)
];

if (dynsymAddr > 0 && dynstrAddr > 0) {
    send({t: 'log', msg: '=== Exact symbol search ==='});
    var numSyms = dynsymSize / dynsymEnt;

    for (var si = 0; si < numSyms; si++) {
        var sym = base.add(dynsymAddr + si * dynsymEnt);
        var st_name = readU32(sym);
        var st_value = readU32(sym.add(4));

        if (st_name === 0) continue;

        var nameAddr = base.add(dynstrAddr + st_name);
        var symName = '';
        var si2 = 0;
        while (si2 < 128) {
            var c = nameAddr.add(si2).readU8();
            if (c === 0) break;
            symName += String.fromCharCode(c);
            si2++;
        }

        for (var eni = 0; eni < exactNames.length; eni++) {
            if (symName.indexOf(exactNames[eni]) !== -1 || exactNames[eni].indexOf(symName) !== -1) {
                send({t: 'log', msg: '  MATCH: ' + symName + ' @ 0x' + st_value.toString(16)});
            }
        }
    }
}

send({t: 'ready', msg: 'ELF parse done'});
