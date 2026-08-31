# -*- coding: utf-8 -*-
"""Decrypt all 30-byte 0x03 packets from teleport5.pcap to find teleport transition"""
import struct

PCAP = "E:/DATA/xunqinol_script/logs/teleport5.pcap"

data = open(PCAP, "rb").read()

pos = 24
pkt_num = 0
results = []

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
    if ip_header[9] != 6:
        continue
    ihl = (ip_header[0] & 0x0F) * 4
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

    to_server = (dst_port == 30002)
    first = payload[0]

    # Only show client→server 0x03 packets of 30 bytes
    if to_server and first == 3 and len(payload) == 30:
        key = payload[1]
        plaintext = []
        for i in range(len(payload) - 1):
            plaintext.append(payload[i + 1] ^ key)
        hex_str = ' '.join(f"{b:02x}" for b in plaintext)

        # Extract sections
        header = ' '.join(f"{b:02x}" for b in plaintext[:17])
        map_seg = ' '.join(f"{b:02x}" for b in plaintext[17:28])
        tail = ' '.join(f"{b:02x}" for b in plaintext[28:])

        results.append({
            'num': pkt_num,
            'ts': ts,
            'plaintext': hex_str,
            'header': header,
            'map_seg': map_seg,
            'tail': tail,
        })

# Show all with timing
prev_ts = results[0]['ts'] if results else 0
print(f"Found {len(results)} client→server 30-byte 0x03 packets\n")

# Group by map_seg to find clusters
from collections import Counter
seg_counts = Counter(r['map_seg'] for r in results)
print("Unique map segments found:")
for seg, count in seg_counts.most_common():
    print(f"  [{seg}] x{count}")

print("\n--- Full timeline ---")
for r in results:
    dt = r['ts'] - prev_ts
    prev_ts = r['ts']
    print(f"#{r['num']:3d}  t={r['ts']:.2f}s (dt={dt:.2f}s)")
    print(f"  HDR: {r['header']}")
    print(f"  MAP: {r['map_seg']}")
    print(f"  TAIL:{r['tail']}")
    print()
