#!/usr/bin/env python3
"""Build the RAM-only Cupid scanout probe; validate exact boot-image contents."""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FDT_SHA = 'ae712dd34d1f5949590d7622dfd31149863dcc7fc8ac1930ef89dde18d47f5c1'
IMAGE_SIZE = 0x200000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fdt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fdt = args.fdt.read_bytes()
    if sha(fdt) != FDT_SHA:
        parser.error('expected the supplied Cupid runtime FDT')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    name = 'cupid-display-probe-v001'
    if (out / (name + '.img')).exists():
        parser.error('output image already exists; preserve frozen artifacts')
    elf, binary = out / (name + '.elf'), out / (name + '.bin')
    sources = ['cupid-display-probe.S', 'cupid-display-probe.c', 'cupid-display-probe.ld']
    subprocess.run([
        'clang', '--target=aarch64-none-elf', '-O2', '-Wall', '-Wextra', '-Werror',
        '-ffreestanding', '-fpie', '-fno-stack-protector', '-fno-builtin',
        '-mgeneral-regs-only', '-nostdlib', '-fuse-ld=lld',
        '-Wl,-T,' + str(HERE / sources[2]), '-Wl,--build-id=none',
        '-Wl,-Map=' + str(out / (name + '.map')),
        str(HERE / sources[0]), str(HERE / sources[1]), '-o', str(elf)
    ], check=True)
    subprocess.run(['llvm-objcopy', '-O', 'binary', str(elf), str(binary)], check=True)
    blob = binary.read_bytes()
    if (blob[:4] != bytes.fromhex('4d5a0091') or
            struct.unpack_from('<QQQ', blob, 8) != (0, IMAGE_SIZE, 0xa) or
            blob[56:60] != b'ARM\x64' or len(blob) >= IMAGE_SIZE):
        raise ValueError('invalid Linux Image header/extent')
    image = blob + bytes(IMAGE_SIZE - len(blob))
    (out / (name + '.Image')).write_bytes(image)
    kernel = out / (name + '.kernel')
    kernel.write_bytes(image + fdt)
    boot_path = out / (name + '.img')
    subprocess.run(['python3', str(HERE.parent / 'prebuilt/uefi/mkbootimg.py'),
                    '--header_version', '4', '--kernel', str(kernel), '-o', str(boot_path)], check=True)
    boot = boot_path.read_bytes()
    size, ramdisk, _, header_size = struct.unpack_from('<4I', boot, 8)
    if (boot[:8] != b'ANDROID!' or header_size != 1584 or ramdisk != 0 or
            struct.unpack_from('<I', boot, 40)[0] != 4 or
            size != IMAGE_SIZE + len(fdt) or boot[4096:4096 + size] != image + fdt):
        raise ValueError('boot v4 content mismatch')
    report = {
        'image': boot_path.name, 'bytes': len(boot), 'sha256': sha(boot),
        'elf_sha256': sha(elf.read_bytes()), 'code_bytes': len(blob),
        'source_sha256': {s: sha((HERE / s).read_bytes()) for s in sources},
        'fdt_sha256': sha(fdt), 'header_version': 4,
        'linux_image': {'text_offset': 0, 'extent': IMAGE_SIZE, 'flags': '0xa'},
        'scope': 'Host format/input validation; device geometry and behavior pending',
        'hardware_access': 'Display register reads; writes only to image stack and splash RAM',
        'phases_seconds': {'assumed_control': 4, 'assumed_register_report': 8, 'live_or_fallback': 20},
    }
    (out / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    (out / 'SHA256SUMS').write_text(f'{sha(boot)}  {boot_path.name}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
