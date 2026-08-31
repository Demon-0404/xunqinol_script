// Disassemble the portal handler chain functions
// Understand how the 29-byte portal packet is constructed

var funcs = [
    {name: 'handler', addr: ptr(0xc276018)},
    {name: 'func1', addr: ptr(0xc354228)},
    {name: 'func2', addr: ptr(0xc35442c)},
    {name: 'stub', addr: ptr(0xc19181c)},
];

function disasm(addr, count) {
    var result = [];
    var cursor = addr;
    for (var i = 0; i < count; i++) {
        try {
            var insn = Instruction.parse(cursor);
            // Show: offset, bytes, mnemonic, operands
            var bytesHex = '';
            var bs = cursor.readByteArray(insn.size);
            var arr = new Uint8Array(bs);
            for (var j = 0; j < insn.size; j++) {
                bytesHex += ('0' + arr[j].toString(16)).slice(-2);
            }
            result.push({
                offset: cursor.sub(addr).toInt32(),
                addr: cursor.toString(),
                bytes: bytesHex,
                mnemonic: insn.mnemonic,
                operands: insn.operands,
                size: insn.size
            });
            cursor = cursor.add(insn.size);
        } catch(e) {
            result.push({offset: cursor.sub(addr).toInt32(), error: e.toString()});
            cursor = cursor.add(2); // skip and try next
        }
    }
    return result;
}

funcs.forEach(function(f) {
    send({t: 'func_start', name: f.name, addr: f.addr.toString()});
    var instructions = disasm(f.addr, 80);
    instructions.forEach(function(ins) {
        if (ins.error) {
            send({t: 'insn', offset: ins.offset, err: ins.error});
        } else {
            send({t: 'insn', offset: ins.offset, bytes: ins.bytes, asm: ins.mnemonic + ' ' + ins.operands});
        }
    });
    send({t: 'func_end', name: f.name});
});

send({t: 'ready'});
