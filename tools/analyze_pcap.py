# -*- coding: utf-8 -*-
"""Analyze teleport5.pcap — show full packet flow with timing to find teleport sequence"""
import struct

PCAP = "E:/DATA/xunqinol_script/logs/teleport5.pcap"

data = open(PCAP, "rb").read()

pos = 24  # Skip pcap global header (link type 113 = Linux SLL)
pkt_num = 0
all_packets = []

while pos < len(data):
    if pos + 16 > len(data):
        break
    ts_sec, ts_usec, incl_len, orig_len = struct.unpack('<IIII', data[pos:pos+16])
    ts = ts_sec + ts_usec / 1000000.0
    pos += 16
    if pos + incl_len > len(data):
        break
    pkt_data = data[pos:pos+incl_len]
    pos += incl_len
    pkt_num += 1

    if len(pkt_data) < 36:
        continue

    proto = struct.unpack('!H', pkt_data[14:16])[0]
    if proto != 0x0800:
        continue

    ip_start = 16
    ip_header = pkt_data[ip_start:]
    if len(ip_header) < 20:
        continue
    protocol = ip_header[9]
    if protocol != 6:
        continue

    ihl = (ip_header[0] & 0x0F) * 4
    src_ip = '.'.join(str(b) for b in ip_header[12:16])
    dst_ip = '.'.join(str(b) for b in ip_header[16:20])

    tcp_start = ip_start + ihl
    if tcp_start + 20 > len(pkt_data):
        continue

    tcp_header = pkt_data[tcp_start:]
    src_port = struct.unpack('!H', tcp_header[0:2])[0]
    dst_port = struct.unpack('!H', tcp_header[2:4])[0]

    data_offset = ((tcp_header[12] >> 4) & 0x0F) * 4
    payload_start = tcp_start + data_offset
    payload = pkt_data[payload_start:]

    if len(payload) == 0:
        continue

    all_packets.append({
        'num': pkt_num,
        'ts': ts,
        'src': f"{src_ip}:{src_port}",
        'dst': f"{dst_ip}:{dst_port}",
        'len': len(payload),
        'data': bytes(payload)
    })

print(f"Total: {pkt_num} pkts, {len(all_packets)} with TCP payload")
print()

# Show all packets with full context
for p in all_packets:
    data = p['data']
    first = data[0]
    to_server = "30002" in p['dst']
    dir_mark = ">>> CLIENT->SERVER" if to_server else "<<< SERVER->CLIENT"
    print(f"{dir_mark} #{p['num']:3d}  len={p['len']:4d}  first=0x{first:02x}  ts={p['ts']:.2f}s")
    hex_str = ' '.join(f"{b:02x}" for b in data[:min(len(data), 64)])
    print(f"  {hex_str}")
    if len(data) > 64:
        print(f"  ... ({len(data)} bytes total)")
    print()
