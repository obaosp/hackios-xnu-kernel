#!/usr/bin/env python3
"""Build and verify stand-alone Cupid Linux handoff probes from fresh sources."""
import argparse
import gzip
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fdt', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    fdt = a.fdt.read_bytes()
    if sha(fdt) != FDT_SHA:
        p.error('expected the supplied Cupid runtime FDT')
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    checks = {}
    for kind in ('reset', 'display'):
        elf = out / f'cupid-probe-{kind}.elf'
        code = out / f'cupid-probe-{kind}.bin'
        cmd = ['clang', '--target=aarch64-none-elf', '-nostdlib', '-fuse-ld=lld',
               '-Wl,--image-base=0', '-Wl,--section-start=.text=0',
               '-Wl,-e,_start', '-Wl,--build-id=none']
        if kind == 'display':
            cmd.append('-DCUPID_PROBE_DISPLAY=1')
        subprocess.run(cmd + [str(HERE/'cupid-probe.S'), '-o', str(elf)], check=True)
        subprocess.run(['llvm-objcopy', '-O', 'binary', str(elf), str(code)], check=True)
        blob = code.read_bytes()
        assert blob[:4] == bytes.fromhex('4d5a0091')
        assert struct.unpack_from('<QQQ', blob, 8) == (0, IMAGE_SIZE, 0xa)
        assert blob[56:60] == b'ARM\x64'
        assert len(blob) < IMAGE_SIZE
        image = blob + bytes(IMAGE_SIZE-len(blob))
        (out/f'cupid-probe-{kind}.Image').write_bytes(image)
        # Reset variants differ only in compression, to isolate the handoff.
        for compression in (('raw', 'gzip') if kind == 'reset' else ('raw',)):
            kernel = (image if compression == 'raw' else gzip.compress(image, mtime=0)) + fdt
            kernel_path = out / f'cupid-probe-{kind}-{compression}.kernel'
            kernel_path.write_bytes(kernel)
            boot_path = out / f'cupid-probe-{kind}-{compression}.img'
            subprocess.run(['python3', str(HERE.parent/'prebuilt/uefi/mkbootimg.py'),
                            '--header_version', '4', '--kernel', str(kernel_path),
                            '-o', str(boot_path)], check=True)
            boot = boot_path.read_bytes()
            kernel_size, ramdisk_size, _, header_size = struct.unpack_from('<4I', boot, 8)
            assert boot[:8] == b'ANDROID!' and header_size == 1584
            assert struct.unpack_from('<I', boot, 40)[0] == 4 and ramdisk_size == 0
            assert boot[4096:4096+kernel_size] == kernel
            if compression == 'gzip':
                import zlib
                stream = zlib.decompressobj(31)
                assert stream.decompress(kernel) == image and stream.eof
                assert stream.unused_data == fdt
            else:
                assert kernel[IMAGE_SIZE:] == fdt
            checks[boot_path.name] = {'bytes': len(boot), 'sha256': sha(boot),
                'header_version': 4, 'text_offset': 0, 'image_size': IMAGE_SIZE,
                'image_flags': '0xa', 'compression': compression, 'probe': kind,
                'code_bytes': len(blob), 'fdt_sha256': sha(fdt),
                'scope': 'host format/input verification; hardware behavior pending'}
    (out/'validation.json').write_text(json.dumps(checks, indent=2)+'\n')
    files = sorted(out.glob('*.img'))
    (out/'SHA256SUMS').write_text(''.join(f'{sha(f.read_bytes())}  {f.name}\n' for f in files))
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    main()
