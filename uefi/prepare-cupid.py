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
    fvlist_patch = (HERE/'cupid-fvlist.patch').read_bytes()
    apply_once(mu, fvlist_patch, 'Cupid FV-list')
    basecore = mu/'Mu_Basecore'
    dxe_patch = (HERE/'cupid-dxe-diagnostics.patch').read_text().replace('\n', '\r\n').encode()
    apply_once(basecore, dxe_patch, 'Cupid DXE diagnostics')
    shutil.copy2(HERE/'files'/sec/'CupidDiagnostics.h',
                 basecore/'MdeModulePkg/Core/Dxe/DxeMain/CupidDiagnostics.h')
    dispatch_patch = (HERE/'cupid-dispatch-diagnostics.patch').read_text().replace('\n', '\r\n').encode()
    apply_once(basecore, dispatch_patch, 'Cupid dispatcher diagnostics')
    shared_dir = basecore/'MdeModulePkg/Core/Dxe/DxeMain'
    shutil.copy2(HERE/'files'/sec/'CupidDispatchDiagnostics.h',
                 shared_dir/'CupidDispatchDiagnostics.h')
    write_driver_names(mu, shared_dir/'CupidDriverNames.h')
    # Reports stay local alongside the vendor inputs, outside this source repository.
    report = {'mu_commit': commit, 'firmware_build': BUILD_ID,
              'driver_policy': 'unmodified stock Cupid drivers; hardware compatibility pending',
              'fdt_sha256': sha(fdt),
              'firmware_sha256': {str(p.relative_to(firmware)): sha(p)
                                  for p in sorted(firmware.rglob('*')) if p.is_file()}}
    (mu/'cupid-inputs.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Prepared Cupid sources, local vendor drivers and runtime FDT in '+str(mu))


def apply_once(tree, patch, label):
    check = subprocess.run(['git', '-C', str(tree), 'apply', '--check', '-'],
                           input=patch, capture_output=True)
    if check.returncode == 0:
        subprocess.run(['git', '-C', str(tree), 'apply', '-'], input=patch, check=True)
        return
    reverse = subprocess.run(['git', '-C', str(tree), 'apply', '--reverse', '--check', '-'],
                             input=patch, capture_output=True)
    if reverse.returncode:
        raise ValueError(label+' patch is neither applicable nor already applied')


def write_driver_names(mu, output):
    """Generate public driver GUID/name labels from the prepared platform INFs."""
    import uuid
    sources = set()
    for inc in (mu/'Platforms/Xiaomi/cupidPkg/Include').glob('*.inc'):
        sources.update(re.findall(r'\bINF\s+(\S+)', inc.read_text()))
    entries = {}
    roots = [mu, mu/'Mu_Basecore', mu/'Silicon/ARM',
             mu/'Silicon/Silicium', mu/'Common/Mu']
    for source in sorted(sources):
        path = next((root/source for root in roots if (root/source).is_file()), None)
        if path is None:
            raise ValueError('cannot resolve trace driver INF: '+source)
        text = path.read_text()
        guid = re.search(r'FILE_GUID\s*=\s*([0-9a-fA-F-]+)', text)
        name = re.search(r'BASE_NAME\s*=\s*(\S+)', text)
        if guid and name:
            identity = uuid.UUID(guid[1])
            entries[identity] = re.sub(r'[^A-Za-z0-9 -]', ' ', name[1])[:28]
    lines = ['/* Generated from prepared driver INFs; no binary firmware data. */',
             'STATIC CONST struct { EFI_GUID Guid; CONST CHAR8 *Name; } CupidDriverNames[] = {']
    for identity, name in sorted(entries.items()):
        fields = identity.fields
        tail = identity.bytes[8:]
        initializer = '{0x%08X,0x%04X,0x%04X,{%s}}' % (
            fields[0], fields[1], fields[2], ','.join('0x%02X' % b for b in tail))
        lines.append('  {%s, "%s"},' % (initializer, name))
    lines.append('};')
    output.write_text('\n'.join(lines)+'\n')


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
