#!/usr/bin/env python3
"""Install Cupid platform sources and locally extracted stock firmware into Mu.

Input is UEFIReader's BOOT.MXF.2.0-01018.3-WAIPIO-1 output directory. This tool
never opens an OTA payload, modifies the source extraction, or publishes binaries.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_ID = 'BOOT.MXF.2.0-01018.3-WAIPIO-1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(args):
    mu, firmware, fdt = args.mu.resolve(), args.firmware_dir.resolve(), args.fdt.resolve()
    if firmware.name != BUILD_ID:
        raise ValueError('expected UEFIReader output for '+BUILD_ID)
    if not fdt.is_file() or fdt.read_bytes()[:4] != bytes.fromhex('d00dfeed'):
        raise ValueError('expected supplied binary runtime Cupid FDT')
    commit = subprocess.check_output(['git', '-C', str(mu), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != (HERE/'BASE').read_text().strip():
        raise ValueError('Mu checkout does not match uefi/BASE')
    platform = HERE/'files/Platforms/Xiaomi/cupidPkg'
    # Check all referenced binary inputs before modifying the build tree.
    inputs = set()
    for source in platform.rglob('*.inc'):
        inputs.update(re.findall(r'Binaries/cupid/([^\s]+)', source.read_text()))
    missing = [p for p in sorted(inputs) if not (firmware/p).is_file()]
    if missing:
        raise ValueError('missing extracted firmware inputs: '+', '.join(missing))
    patch = HERE/'mu-silicium.patch'
    check = subprocess.run(['git', '-C', str(mu), 'apply', '--check', str(patch)], capture_output=True)
    if check.returncode == 0:
        subprocess.run(['git', '-C', str(mu), 'apply', '--whitespace=nowarn', str(patch)], check=True)
    else:
        reverse = subprocess.run(['git', '-C', str(mu), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
        if reverse.returncode:
            raise ValueError('Mu patch is neither cleanly applicable nor already applied')
    copies = [(platform, mu/'Platforms/Xiaomi/cupidPkg'),
              (firmware, mu/'Binaries/cupid')]
    for source, dest in copies:
        shutil.copytree(source, dest, dirs_exist_ok=True)
    shared = 'Silicon/Silicium/SiliciumPkg/Library/BootManagerLib'
    for name in ('XnuLoader.c', 'XnuLoader.h'):
        shutil.copy2(HERE/'files'/shared/name, mu/shared/name)
    shutil.copy2(HERE/'files/Resources/Configs/cupid.toml', mu/'Resources/Configs/cupid.toml')
    shutil.copy2(fdt, mu/'Resources/DTBs/cupid.dtb')
    diagnostics = HERE/'cupid-diagnostics.patch'
    # Mu SEC sources use CRLF; keep our patch LF in Git and match source endings here.
    diagnostic_patch = diagnostics.read_text().replace('\n', '\r\n').encode()
    check = subprocess.run(['git', '-C', str(mu), 'apply', '--check', '-'], input=diagnostic_patch, capture_output=True)
    if check.returncode == 0:
        subprocess.run(['git', '-C', str(mu), 'apply', '-'], input=diagnostic_patch, check=True)
    else:
        reverse = subprocess.run(['git', '-C', str(mu), 'apply', '--reverse', '--check', '-'], input=diagnostic_patch, capture_output=True)
        if reverse.returncode:
            raise ValueError('Cupid diagnostics patch is neither applicable nor already applied')
    sec = 'Silicon/Silicium/SiliciumPkg/Sec'
    shutil.copy2(HERE/'files'/sec/'CupidDiagnostics.h', mu/sec/'CupidDiagnostics.h')
    # Reports stay local alongside the vendor inputs, outside this source repository.
    report = {'mu_commit': commit, 'firmware_build': BUILD_ID,
              'driver_policy': 'unmodified stock Cupid drivers; hardware compatibility pending',
              'fdt_sha256': sha(fdt),
              'firmware_sha256': {str(p.relative_to(firmware)): sha(p)
                                  for p in sorted(firmware.rglob('*')) if p.is_file()}}
    (mu/'cupid-inputs.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Prepared Cupid sources, local vendor drivers and runtime FDT in '+str(mu))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mu', type=Path, default=HERE.parent/'Mu-Silicium')
    parser.add_argument('--firmware-dir', type=Path, required=True)
    parser.add_argument('--fdt', type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args)
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
