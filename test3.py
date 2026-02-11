a = bytearray.fromhex("0b00707f000000004500005454d900000101f455c0a833be6812140208004d9d9d2ed8000b")

import struct
import json


ICMP_HEADER_FORMAT = "!BBHI"
ICMP_ORIGINAL_IPV4 = "!BBHHHBBHII"
ICMP_ORIGINAL_ICMP = "!BBHHH"


header_offset = 0
original_ipv4_offset = struct.calcsize(ICMP_HEADER_FORMAT)
original_icmp_offset = original_ipv4_offset + struct.calcsize(ICMP_ORIGINAL_IPV4)


icmp_header =        a[header_offset:        header_offset +        struct.calcsize(ICMP_HEADER_FORMAT)]
icmp_original_ipv4 = a[original_ipv4_offset: original_ipv4_offset + struct.calcsize(ICMP_ORIGINAL_IPV4)]
icmp_original_icmp = a[original_icmp_offset: original_icmp_offset + struct.calcsize(ICMP_ORIGINAL_ICMP)]


print(icmp_header)
print(icmp_original_ipv4)
print(icmp_original_icmp)

icmp_header_dict = dict(zip(
    (
        "type",
        "code",
        "checksum",
        "unused",
    ),
    struct.unpack(ICMP_HEADER_FORMAT, icmp_header)
))
icmp_original_ipv4_dict = dict(zip(
    (
        "version",
        "dscp",
        "total_length",
        "identification",
        "flags",
        "ttl",
        "protocol",
        "checksum",
        "source_address",
        "destination_address",
    ),
    struct.unpack(ICMP_ORIGINAL_IPV4, icmp_original_ipv4)
))
icmp_original_icmp_dict = dict(zip(
    (
        "type",
        "code",
        "checksum",
        "identifier",
        "sequence_number",
    ),
    struct.unpack(ICMP_ORIGINAL_ICMP, icmp_original_icmp)
))

def int_to_ip(ip: int) -> str:
    return "{}.{}.{}.{}".format(
        (ip >> (3 * 8)) & 0xff,
        (ip >> (2 * 8)) & 0xff,
        (ip >> (1 * 8)) & 0xff,
        (ip >> (0 * 8)) & 0xff,
    )

icmp_original_ipv4_dict["source_address"] =      int_to_ip(icmp_original_ipv4_dict["source_address"])
icmp_original_ipv4_dict["destination_address"] = int_to_ip(icmp_original_ipv4_dict["destination_address"])

print("ICMP HEADER",        json.dumps(icmp_header_dict,        indent=4))
print("ICMP ORIGINAL IPV4", json.dumps(icmp_original_ipv4_dict, indent=4))
print("ICMP ORIGINAL ICMP", json.dumps(icmp_original_icmp_dict, indent=4))
