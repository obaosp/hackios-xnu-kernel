#!/usr/bin/env python3
"""Run frozen Cupid DXE dispatcher entry in modeled ARM64 RAM (pefile/unicorn).

Require the constant entry trace, dispatcher-global trace and pre-event trace,
then stop before the event constructor. Executes the real PE, glyph drawing,
cache-maintenance instructions and payload parser; only delay calls are skipped.
Physical scanout, page tables, IOMMU, interrupts and later drivers are not modeled.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

import pefile
from PIL import Image
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.arm64_const import (UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
                                UC_ARM64_REG_X0, UC_ARM64_REG_X2, UC_ARM64_REG_PSTATE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', type=Path)
    args = parser.parse_args()
    root = args.artifacts.resolve()
    core = (root / 'DxeCore.efi').read_bytes()
    symbols = {}
    for line in (root / 'DxeCore.map').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{8})\s+0{8}\s+0\s+(\S+)', line)
        if match:
            symbols[match[2]] = int(match[1], 16)
    required = ('CoreDispatcher', 'CoreCreateEventInternal', 'CupidDriverSequence', 'gDispatcherRunning')
    if any(name not in symbols for name in required):
        raise ValueError('required compiled DXE symbols absent')
    base, splash = 0xfa800000, 0xb8000000
    pe = pefile.PE(data=core)
    pe.relocate_image(base)
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    mu.mem_write(base, pe.get_memory_mapped_image())
    mu.mem_map(splash, 0x2b00000)
    payload = (root / 'usb-payload.bin').read_bytes()
    mu.mem_map(0xf6000000, (len(payload) + 4095) & ~4095)
    mu.mem_write(0xf6000000, payload)
    mu.mem_map(0xa760d000, 0x40000)
    mu.reg_write(UC_ARM64_REG_SP, 0xa764c000)
    mu.reg_write(UC_ARM64_REG_LR, base)
    mu.reg_write(UC_ARM64_REG_PSTATE, 0x3c5)
    traces = []
    event_reached = False

    def string(address):
        out = bytearray()
        for i in range(64):
            value = bytes(mu.mem_read(address + i, 1))
            if value == b'\0':
                return out.decode('ascii')
            out += value
        raise ValueError('unterminated trace phase')

    def skip_delay(mu, pc, size, data):
        mu.reg_write(UC_ARM64_REG_PC, mu.reg_read(UC_ARM64_REG_LR))

    def trace(mu, pc, size, data):
        traces.append({'phase': string(mu.reg_read(UC_ARM64_REG_X2)),
                       'sequence': mu.reg_read(UC_ARM64_REG_X0)})

    def event(mu, pc, size, data):
        nonlocal event_reached
        event_reached = True
        mu.emu_stop()

    def invalid(mu, kind, address, size, value, data):
        raise RuntimeError(f'invalid access {kind} at {address:#x}; RVA={mu.reg_read(UC_ARM64_REG_PC) - base:#x}')

    for name, rva in symbols.items():
        if name == 'CupidDelay' or name.startswith('CupidDelay.'):
            mu.hook_add(UC_HOOK_CODE, skip_delay, begin=base + rva, end=base + rva)
        if name == 'CupidTraceDriver' or name.startswith('CupidTraceDriver.'):
            mu.hook_add(UC_HOOK_CODE, trace, begin=base + rva, end=base + rva)
    mu.hook_add(UC_HOOK_CODE, event, begin=base + symbols['CoreCreateEventInternal'],
                end=base + symbols['CoreCreateEventInternal'])
    mu.hook_add(UC_HOOK_MEM_INVALID, invalid)
    mu.emu_start(base + symbols['CoreDispatcher'], base, count=80000000)
    expected = ['DISPATCH ENTRY', 'DISPATCH GLOBALS', 'CREATE DISPATCH EVENT']
    if not event_reached or [t['phase'] for t in traces] != expected or any(t['sequence'] for t in traces):
        raise ValueError(f'entry incomplete: event={event_reached}, traces={traces}')
    if bytes(mu.mem_read(base + symbols['gDispatcherRunning'], 1)) != b'\x01':
        raise ValueError('dispatcher running state was not set')
    pixels = bytes(mu.mem_read(splash, 1080 * 2400 * 4))
    for panel in (0, 800, 1600):
        title = pixels[(panel + 32) * 1080 * 4:(panel + 68) * 1080 * 4]
        if title.count(b'\xff\xff\xff\xff') < 500 or title.count(b'\0\0\0\xff') < 500:
            raise ValueError(f'repeated trace panel absent at row {panel}')
    png = root / 'emulated-dxe-entry.png'
    Image.frombytes('RGB', (1080, 2400), pixels, 'raw', 'BGRX').save(png)
    report = {'status': 'passed', 'core_sha256': hashlib.sha256(core).hexdigest(),
              'relocation_base': hex(base), 'traces': traces, 'event_constructor_reached': event_reached,
              'framebuffer_sha256': hashlib.sha256(pixels).hexdigest(), 'png': png.name,
              'scope': 'Frozen ARM64 PE; normal stage-14 return, traces and cache clean executed in modeled RAM; delays skipped, physical display/MMU/IOMMU/interrupts/drivers not modeled'}
    (root / 'emulated-dxe-entry.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
