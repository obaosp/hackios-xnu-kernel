#!/usr/bin/env python3
"""Verify the compiled DXE core is embedded in Cupid's compressed UEFI FD."""
import argparse
import hashlib
import json
import lzma
import struct
import uuid
from pathlib import Path


def sections(data):
    pos = 0
    while pos + 4 <= len(data):
        size = int.from_bytes(data[pos:pos + 3], 'little')
        header = 4
        if size == 0xffffff:
            if pos + 8 > len(data):
                raise ValueError('truncated extended section header')
            size = struct.unpack_from('<I', data, pos + 4)[0]
            header = 8
        if size < header or pos + size > len(data):
            raise ValueError('invalid section bounds')
        yield data[pos + 3], data[pos + header:pos + size]
        pos = (pos + size + 3) & ~3


def verify(fd, compiled):
    guided = uuid.UUID('ee4e5898-3914-4259-9d6e-dc7bd79403cf').bytes_le
    loc = fd.index(guided)
    start = loc - 4
    size = int.from_bytes(fd[start:start + 3], 'little')
    offset = struct.unpack_from('<H', fd, loc + 16)[0]
    if start < 0 or fd[start + 3] != 2 or offset < 24 or start + size > len(fd):
        raise ValueError('invalid LZMA guided section')
    decoded = lzma.decompress(fd[start + offset:start + size], format=lzma.FORMAT_ALONE)
    fv = next((body for kind, body in sections(decoded) if kind == 0x17), None)
    if fv is None or len(fv) < 56 or fv[40:44] != b'_FVH':
        raise ValueError('no valid decompressed firmware volume')
    length = struct.unpack_from('<Q', fv, 32)[0]
    header = struct.unpack_from('<H', fv, 48)[0]
    if length != len(fv) or not 56 <= header <= length:
        raise ValueError('invalid firmware volume length/header')
    target = uuid.UUID('d6a2cb7f-6a18-4e2f-b43b-9920a733700a').bytes_le
    pos = (header + 7) & ~7
    while pos + 24 <= length:
        size = int.from_bytes(fv[pos + 20:pos + 23], 'little')
        if size == 0xffffff or size < 24 or pos + size > length:
            break
        if fv[pos:pos + 16] == target:
            core = next((body for kind, body in sections(fv[pos + 24:pos + size])
                         if kind == 0x10), None)
            if core != compiled:
                raise ValueError('embedded DXE differs from compiled DXE')
            return {'status': 'passed', 'fd_sha256': hashlib.sha256(fd).hexdigest(),
                    'embedded_dxe_sha256': hashlib.sha256(core).hexdigest(),
                    'decompressed_bytes': len(decoded),
                    'scope': 'Exact compiled DXE recovered from compressed FD; hardware execution unverified'}
        pos = (pos + size + 7) & ~7
    raise ValueError('DXE core not found in firmware volume')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=Path, required=True)
    parser.add_argument('--dxe', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.fd.read_bytes(), args.dxe.read_bytes()), indent=2))
    except (ValueError, struct.error, lzma.LZMAError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
