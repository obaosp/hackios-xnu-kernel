#!/usr/bin/env python3
"""Pack loader-only Cupid UEFI diagnostics that stop at selected SEC checkpoints."""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact', type=Path, required=True)
    p.add_argument('--stages', type=int, nargs='+', default=[1, 2, 3, 4, 5, 6, 7])
    a = p.parse_args()
    root = a.artifact.resolve()
    baseline = json.loads((root/'validation.json').read_text())
    for name, file in [('image', 'cupid-loader-v003.img'), ('shim','BootShim.bin'),
                       ('fd','SILICIUM_UEFI.fd'), ('payload','usb-payload.bin'),
                       ('loader','loader.efi'), ('fdt','cupid.dtb')]:
        assert sha(root/file) == baseline['sha256'][name], name
    shim, fd, original = [(root/f).read_bytes() for f in
                          ['BootShim.bin', 'SILICIUM_UEFI.fd', 'usb-payload.bin']]
    assert original[-24:] == bytes(24)
    checks = {}
    for stage in a.stages:
        assert 1 <= stage <= 7
        extra = struct.pack('<16sII', b'sec-stop', 4, 0)+struct.pack('<I', stage)+bytes(12)
        body = original[8:-24]+extra+bytes(24)
        payload = b'XNUP'+struct.pack('<I',len(body))+body
        blob = shim+fd+payload
        blob += bytes((-len(blob))%16)
        import gzip
        kernel = gzip.compress(blob,6,mtime=0)+(root/'cupid.dtb').read_bytes()
        kpath = root/f'cupid-sec-stop-{stage:02}.kernel'
        image = root/f'cupid-sec-stop-{stage:02}.img'
        kpath.write_bytes(kernel)
        subprocess.run(['python3',str(HERE.parent/'prebuilt/uefi/mkbootimg.py'),
                        '--kernel',str(kpath),'--ramdisk',str(HERE.parent/'Mu-Silicium/Resources/ramdisk'),
                        '--header_version','4','-o',str(image)],check=True)
        boot=image.read_bytes()
        assert boot[:8]==b'ANDROID!' and boot[4096:4096+len(kernel)]==kernel
        assert struct.unpack_from('<I',boot,40)[0]==4
        import zlib
        stream=zlib.decompressobj(31)
        decoded=stream.decompress(kernel)
        assert stream.eof and stream.unused_data==(root/'cupid.dtb').read_bytes()
        assert decoded[:len(shim)]==shim
        assert decoded[len(shim):len(shim)+len(fd)]==fd
        recovered=decoded[len(shim)+len(fd):len(shim)+len(fd)+len(payload)]
        assert recovered[:4]==b'XNUP' and struct.unpack_from('<I',recovered,4)[0]+8==len(recovered)
        entries={}
        pos=8
        while pos+24<=len(recovered):
            name,size,reserved=struct.unpack_from('<16sII',recovered,pos)
            pos+=24
            if name==bytes(16):
                assert size==reserved==0 and pos==len(recovered)
                break
            assert reserved==0 and pos+size<=len(recovered)
            entries[name.rstrip(b'\0')]=recovered[pos:pos+size]
            pos+=(size+15)&~15
        assert set(entries)=={b'loader.efi',b'usb',b'sec-stop'}
        assert entries[b'loader.efi']==(root/'loader.efi').read_bytes()
        assert entries[b'usb']==b'1\0' and entries[b'sec-stop']==struct.pack('<I',stage)
        checks[image.name]={'bytes':len(boot),'sha256':sha(image),'stop_stage':stage,
            'fd_sha256':sha(root/'SILICIUM_UEFI.fd'),'payload_sha256':hashlib.sha256(payload).hexdigest(),
            'scope':'host identity/packing checks; SEC stage execution requires hardware'}
    (root/'sec-stop-validation.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps(checks,indent=2))


if __name__=='__main__':
    main()
