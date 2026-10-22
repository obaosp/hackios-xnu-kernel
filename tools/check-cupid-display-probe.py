#!/usr/bin/env python3
"""Execute a frozen Cupid display probe in modeled ARM64 RAM (unicorn, pillow).

Checks nonzero relocation, exact MMIO read addresses, absence of MMIO writes,
candidate rejection/selection and reset. Delays are skipped. This does not model
the physical panel, IOMMU, interrupt state or bootloader page tables.
"""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

from PIL import Image
from unicorn import (Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_MEM_READ,
                     UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_INVALID)
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_LR, UC_ARM64_REG_PSTATE

IMAGE_BASE, SPLASH_BASE, MDSS_BASE = 0x88000000, 0xb8000000, 0x0ae00000
OFFSETS = (0x5000, 0x7000, 0x9000, 0xb000, 0x25000, 0x27000, 0x29000, 0x2b000)
REGISTERS = (0, 8, 12, 20, 36, 48, 52, 56)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', type=Path)
    parser.add_argument('--case', choices=('exact', 'offset-stride', 'invalid', 'tiled', 'outside'), required=True)
    args = parser.parse_args()
    root = args.artifacts.resolve()
    manifest = json.loads((root / 'validation.json').read_text())
    elf = root / 'cupid-display-probe-v001.elf'
    if hashlib.sha256(elf.read_bytes()).hexdigest() != manifest['elf_sha256']:
        raise ValueError('frozen ELF differs from validated artifact')
    symbols = {}
    for line in subprocess.check_output(['llvm-nm', '-n', str(elf)], text=True).splitlines():
        address, _, name = line.split()
        symbols[name] = int(address, 16)
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(IMAGE_BASE, 0x200000)
    mu.mem_write(IMAGE_BASE, (root / 'cupid-display-probe-v001.Image').read_bytes())
    mu.mem_map(SPLASH_BASE, 0x2b00000)
    mu.mem_map(MDSS_BASE, 0x84000)
    mu.reg_write(UC_ARM64_REG_PSTATE, 0x3c5)  # EL1h, interrupts masked
    address, width, height, stride, xy, fmt = SPLASH_BASE, 1080, 2400, 4320, 0, 0x237ff
    selected = args.case not in ('invalid', 'tiled', 'outside')
    if args.case == 'offset-stride':
        address, width, height, stride, xy = SPLASH_BASE + 0x100000, 1080, 2400, 4480, (4 << 16) | 8
    elif args.case == 'tiled':
        fmt |= 1 << 30
    elif args.case == 'outside':
        address = SPLASH_BASE + 0x2aff000
    if args.case != 'invalid':
        values = (height << 16 | width, xy, height << 16 | width, address, stride, fmt, 0x03020001, 0)
        for offset, value in zip(REGISTERS, values):
            mu.mem_write(MDSS_BASE + OFFSETS[0] + offset, struct.pack('<I', value))
    reads, writes, phases = [], [], []
    reset = False

    def access(mu, kind, address, size, value, user):
        (reads if kind == UC_MEM_READ else writes).append((address, size))

    def invalid(mu, kind, address, size, value, user):
        raise RuntimeError(f'invalid memory access {kind} at {address:#x}, PC={mu.reg_read(UC_ARM64_REG_PC):#x}')

    def delay(mu, pc, size, user):
        phase = len(phases)
        if phase == 2 and selected:
            base = address + (xy >> 16) * stride + (xy & 65535) * 4
            rows = [bytes(mu.mem_read(base + y * stride, width * 4)) for y in range(height)]
            pixels = b''.join(rows)
            w, h = width, height
        else:
            pixels = bytes(mu.mem_read(SPLASH_BASE, 1080 * 2400 * 4))
            w, h = 1080, 2400
        png = root / f'emulated-{args.case}-phase-{phase}.png'
        Image.frombytes('RGB', (w, h), pixels, 'raw', 'BGRX').save(png)
        # Black glyph cells must have appeared in each phase's title line.
        if b'\x00\x00\x00\xff' not in pixels[32 * w * 4:64 * w * 4]:
            raise ValueError('expected title glyph backgrounds absent')
        phases.append({'phase': phase, 'framebuffer_sha256': hashlib.sha256(pixels).hexdigest(), 'png': png.name})
        mu.reg_write(UC_ARM64_REG_PC, mu.reg_read(UC_ARM64_REG_LR))

    def finish(mu, pc, size, user):
        nonlocal reset
        reset = True
        mu.emu_stop()

    mu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access, begin=MDSS_BASE, end=MDSS_BASE + 0x83fff)
    mu.hook_add(UC_HOOK_MEM_INVALID, invalid)
    mu.hook_add(UC_HOOK_CODE, delay, begin=IMAGE_BASE + symbols['delay'], end=IMAGE_BASE + symbols['delay'])
    mu.hook_add(UC_HOOK_CODE, finish, begin=IMAGE_BASE + symbols['probe_reset'], end=IMAGE_BASE + symbols['probe_reset'])
    mu.emu_start(IMAGE_BASE, IMAGE_BASE + 0x200000, count=150000000)
    expected_reads = sorted((MDSS_BASE + p + r, 4) for p in OFFSETS for r in REGISTERS)
    if sorted(reads) != expected_reads or writes or len(phases) != 3 or not reset:
        raise ValueError(f'incomplete/incorrect run: reads={len(reads)}, writes={writes}, phases={len(phases)}, reset={reset}')
    expected_base = address + (xy >> 16) * stride + (xy & 65535) * 4 if selected else SPLASH_BASE
    # A black live checkerboard pixel near the lower left establishes the selected
    # address/stride independently of the register-reading loop and report text.
    check_stride = stride if selected else 4320
    if bytes(mu.mem_read(expected_base + 1320 * check_stride, 4)) != b'\x00\x00\x00\xff':
        raise ValueError('live pattern missing at the expected selected surface')
    report = {'case': args.case, 'status': 'passed', 'image_sha256': manifest['sha256'],
              'relocation_base': hex(IMAGE_BASE), 'mmio_reads': len(reads), 'mmio_writes': len(writes),
              'reset_reached': reset, 'expected_live_base': hex(expected_base), 'phases': phases,
              'scope': 'Frozen compiled ARM64 in modeled RAM; delays skipped, physical display/MMU/IOMMU not modeled'}
    (root / f'emulation-{args.case}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
