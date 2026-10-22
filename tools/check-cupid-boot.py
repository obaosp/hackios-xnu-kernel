#!/usr/bin/env python3
"""Validate a Cupid loader diagnostic image against its actual build inputs."""
import argparse
import hashlib
import json
import struct
import subprocess
import zlib
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def cells(fdt, node, prop):
    return [int(n, 16) for n in subprocess.check_output(
        ['fdtget', '-tx', str(fdt), node, prop], text=True).split()]


def regions(fdt, node):
    values = cells(fdt, node, 'reg')
    require(len(values) % 4 == 0, 'expected 64-bit FDT address/size cells')
    return [(values[i] << 32 | values[i+1], values[i+2] << 32 | values[i+3])
            for i in range(0, len(values), 4)]


def validate(args):
    data = args.image.read_bytes()
    require(data[:8] == b'ANDROID!', 'bad Android boot magic')
    kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from('<4I', data, 8)
    require(struct.unpack_from('<I', data, 40)[0] == 4, 'expected boot header v4')
    require(header_size == 1584, 'bad v4 header size')
    signature_size = struct.unpack_from('<I', data, 1580)[0]
    require(signature_size in (0, 4096), 'unexpected diagnostic signature size')
    unsigned_size = 4096 + ((kernel_size + 4095) // 4096) * 4096 + ((ramdisk_size + 4095) // 4096) * 4096
    expected_size = unsigned_size + signature_size
    require(len(data) == expected_size, 'incorrect boot image section sizes')
    require(data[unsigned_size:] == bytes(signature_size), 'diagnostic signature is not empty')
    stream = zlib.decompressobj(31)
    blob = stream.decompress(data[4096:4096+kernel_size])
    require(stream.eof, 'incomplete gzip stream')
    dtb = stream.unused_data
    require(dtb == args.fdt.read_bytes(), 'appended FDT differs from supplied Cupid FDT')
    require(struct.unpack_from('>II', dtb)[0] == 0xd00dfeed, 'bad FDT magic')
    require(struct.unpack_from('>I', dtb, 4)[0] == len(dtb), 'bad FDT total size')
    shim = args.shim.read_bytes()
    fd = args.fd.read_bytes()
    payload = args.payload.read_bytes()
    require(blob[:len(shim)] == shim, 'shim mismatch')
    require(blob[56:60] == b'ARM\x64', 'missing ARM64 image header')
    require(struct.unpack_from('<QQ', shim, 8) == (args.fd_base, args.fd_size), 'shim FD addresses mismatch')
    # BootShim uses MOVZ X5, #(PAYLOAD_BASE >> 16), LSL #16.
    require(args.payload_base & 0xffff == 0 and args.payload_base < 0x100000000, 'shim payload address is not representable')
    instruction = 0xd2a00005 | ((args.payload_base >> 16) << 5)
    require(struct.pack('<I', instruction) in shim, 'shim payload destination mismatch')
    require(len(fd) == args.fd_size, 'FD size mismatch')
    require(blob[len(shim):len(shim)+len(fd)] == fd, 'FD mismatch')
    offset = len(shim)+len(fd)
    require(blob[offset:offset+len(payload)] == payload, 'payload mismatch')
    require(blob[offset+len(payload):] == bytes((-offset-len(payload)) % 16), 'unexpected data after payload')
    require(payload[:4] == b'XNUP', 'bad XNUP magic')
    require(struct.unpack_from('<I', payload, 4)[0]+8 == len(payload), 'bad XNUP size')
    require(len(payload) <= 0x4000000-0x1000, 'payload exceeds reserved region')
    entries = {}
    pos = 8
    while True:
        require(pos+24 <= len(payload), 'truncated XNUP entry')
        name, size, reserved = struct.unpack_from('<16sII', payload, pos)
        pos += 24
        require(reserved == 0, 'nonzero XNUP reserved field')
        if not name.strip(b'\0'):
            require(size == 0 and pos == len(payload), 'invalid XNUP terminator')
            break
        name = name.split(b'\0')[0].decode('ascii')
        require(name not in entries and pos+size <= len(payload), 'invalid XNUP entry')
        entries[name] = payload[pos:pos+size]
        pos += (size+15) & ~15
    require(set(entries) == {'loader.efi', 'usb'}, 'expected loader-only USB diagnostic payload')
    loader = args.loader.read_bytes()
    require(entries['loader.efi'] == loader and entries['usb'] == b'1\0', 'loader payload mismatch')
    require(loader[:2] == b'MZ', 'bad PE DOS header')
    pe = struct.unpack_from('<I', loader, 60)[0]
    require(loader[pe:pe+4] == b'PE\0\0', 'bad PE signature')
    require(struct.unpack_from('<H', loader, pe+4)[0] == 0xaa64, 'loader is not AArch64')
    require(struct.unpack_from('<H', loader, pe+24+68)[0] == 10, 'loader is not an EFI application')
    ram = regions(args.fdt, '/memory')
    start, end = args.payload_base, args.payload_base+0x4000000
    require(any(base <= start and end <= base+size for base, size in ram), 'payload lies outside runtime RAM')
    children = subprocess.check_output(['fdtget', '-l', str(args.fdt), '/reserved-memory'], text=True).split()
    for child in children:
        node = '/reserved-memory/'+child
        props = subprocess.check_output(['fdtget', '-p', str(args.fdt), node], text=True).split()
        if 'reg' in props:
            for base, size in regions(args.fdt, node):
                require(end <= base or base+size <= start, 'payload overlaps '+node)
    return {'status': 'passed', 'scope': 'host structural validation; hardware boot unverified',
            'image_bytes': len(data), 'header_version': 4, 'signature_bytes': signature_size, 'kernel_bytes': kernel_size,
            'fd_base': hex(args.fd_base), 'fd_bytes': len(fd), 'shim_bytes': len(shim),
            'payload_base': hex(start), 'payload_bytes': len(payload), 'loader_bytes': len(loader),
            'sha256': {name: digest(value) for name, value in
                       [('image', data), ('fd', fd), ('shim', shim), ('payload', payload), ('loader', loader), ('fdt', dtb)]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'shim', 'fd', 'payload', 'loader', 'fdt'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--fd-base', type=lambda v: int(v, 0), default=0xa7000000)
    parser.add_argument('--fd-size', type=lambda v: int(v, 0), default=0x400000)
    parser.add_argument('--payload-base', type=lambda v: int(v, 0), default=0xf6000000)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args), indent=2))
    except (ValueError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, 'validation failed: '+str(error)+'\n')


if __name__ == '__main__':
    main()
