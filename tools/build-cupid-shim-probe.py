#!/usr/bin/env python3
"""Isolate the frozen Cupid loader shim by replacing UEFI with the working probe."""
import argparse
import gzip
import hashlib
import json
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--loader-artifact', type=Path, required=True)
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    source, out = a.loader_artifact.resolve(), a.output.resolve()
    meta = json.loads((source/'validation.json').read_text())
    shim = (source/'BootShim.bin').read_bytes()
    payload = (source/'usb-payload.bin').read_bytes()
    fdt = (source/'cupid.dtb').read_bytes()
    assert sha(shim) == meta['sha256']['shim']
    assert sha(payload) == meta['sha256']['payload']
    assert sha(fdt) == meta['sha256']['fdt']
    assert struct.unpack_from('<QQ', shim, 8) == (0xa7100000, 0x300000)
    code = a.probe.read_bytes()
    assert code[:4] == bytes.fromhex('4d5a0091') and code[56:60] == b'ARM\x64'
    assert len(code) < 0x300000
    # The exact existing shim relocates this replacement FD, then the payload.
    fd = code + bytes(0x300000-len(code))
    out.mkdir(parents=True, exist_ok=True)
    checks = {}
    for kind in ('original-header', 'linux-header'):
        head = bytearray(shim)
        extent = len(shim)+len(fd)+len(payload)
        extent = (extent+15)&~15
        if kind == 'linux-header':
            struct.pack_into('<QQQ', head, 8, 0, extent, 0xa)
        blob = bytes(head)+fd+payload
        blob += bytes((-len(blob))%16)
        assert blob[len(shim):len(shim)+len(fd)] == fd
        assert blob[len(shim)+len(fd):len(shim)+len(fd)+len(payload)] == payload
        assert head[:8] == shim[:8] and head[32:] == shim[32:]
        kernel = gzip.compress(blob, mtime=0)+fdt
        kpath = out/f'cupid-shim-{kind}.kernel'
        image = out/f'cupid-shim-{kind}.img'
        kpath.write_bytes(kernel)
        cmd = ['python3', str(HERE.parent/'prebuilt/uefi/mkbootimg.py'),
               '--header_version', '4', '--kernel', str(kpath), '-o', str(image)]
        ramdisk = HERE.parent/'Mu-Silicium/Resources/ramdisk'
        cmd += ['--ramdisk', str(ramdisk)]
        subprocess.run(cmd, check=True)
        boot = image.read_bytes()
        assert boot[:8] == b'ANDROID!' and struct.unpack_from('<I',boot,40)[0] == 4
        assert boot[4096:4096+len(kernel)] == kernel
        checks[image.name] = {'bytes':len(boot),'sha256':sha(boot),
            'shim_source_sha256':sha(shim),'probe_sha256':sha(code),
            'header_fields':list(struct.unpack_from('<QQQ',head,8)),
            'fd_base':'0xa7100000','fd_size':len(fd),'payload_base':'0xf6000000',
            'scope':'host format/input checks; hardware relocation pending'}
    (out/'validation.json').write_text(json.dumps(checks,indent=2)+'\n')
    (out/'SHA256SUMS').write_text(''.join(f'{v["sha256"]}  {k}\n' for k,v in checks.items()))
    print(json.dumps(checks,indent=2))


if __name__ == '__main__':
    main()
