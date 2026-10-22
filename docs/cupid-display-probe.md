# Cupid scanout diagnostic

The continuing v006 loader reaches the azure DXE-entry checkpoint, but neither
trace text nor loader USB is visible. Full-screen fills do not establish the live
framebuffer base, stride, crop or update behavior. This standalone probe compares
the configured surface with a plausible live source-pipe surface before UEFI
changes the hardware. It contains no loader, XNU or iOS.

Build into a new artifact directory; existing images are never overwritten:

```sh
python3 tools/build-cupid-display-probe.py \
  --fdt /path/to/supplied/fdt \
  --output /path/to/new/display-probe-v001
```

Boot from unlocked stock fastboot using `fastboot boot` and the resulting
`cupid-display-probe-v001.img`. Do not flash it. Observe these phases:

1. Four seconds: repeated `CUPID ASSUMED LAYOUT CONTROL` over a checkerboard.
2. Eight seconds: raw source-pipe register report in the assumed layout.
3. Twenty seconds: black/white checkerboard and report in the largest eligible
   source-pipe layout, or the assumed layout if no pipe qualifies. Automatic reset
   follows. Allow about 40 seconds from fastboot's `Booting OKAY`.

An exception branches to a stack-independent red fill and PSCI reset. A hardware
bus transaction that never completes can still require held-power recovery.
USB is not initialized in this probe; `fastboot devices` need not list it.

Report whether text is readable in each phase, whether it is cropped or skewed,
the final selected pipe/base/stride/width/height, pipe rows if readable, and reset
timing. A pipe is a candidate, not proven active scanout: registers can be stale,
addresses can be IOVAs, and split-panel pipes can describe only part of a frame.

## Inputs and limits

The runtime FDT supplies MDSS base `0x0ae00000`, eight source-pipe offsets and the
splash reservation `0xb8000000..0xbab00000`. Register offsets and bit fields come
from MiCode/Xiaomi_Kernel_OpenSource revision
`7d10d738b2c4299f3b8549c61a01ece39f19c788`, branch `zeus-s-oss`,
`drivers/gpu/drm/msm/disp/dpu1/dpu_hw_sspp.c` and `dpu_hw_catalog.c`.

The probe reads source size, crop, output size, plane-0 address, byte stride,
format, unpack pattern and operation mode for all eight pipes. It changes no
MMIO registers. Writes are limited to the probe image's own stack and splash RAM.
Only bounded, linear, four-byte interleaved RGB candidates qualify. No compressed,
tiled, YUV, rotated or out-of-reservation surface is selected. Cache lines are
cleaned if the bootloader left the data cache enabled.

The report abbreviates address as `A`, packed source size as `S` (height in high
16 bits, width in low 16), byte stride as `T`, format as `F`, unpack as `U`, and
operation mode as `O`. Numbers are hexadecimal. Repeated copies expose cropping
or partial-update behavior. Black/white avoids depending on RGB channel ordering.

## Host checks

The builder validates Linux Image and Android boot header v4, exact embedded FDT,
image contents and input/output hashes. The optional emulator requires `unicorn`
and `pillow` and runs the frozen ARM64 ELF at a nonzero physical address:

```sh
python3 tools/check-cupid-display-probe.py /path/to/artifacts --case exact
python3 tools/check-cupid-display-probe.py /path/to/artifacts --case offset-stride
python3 tools/check-cupid-display-probe.py /path/to/artifacts --case invalid
python3 tools/check-cupid-display-probe.py /path/to/artifacts --case tiled
python3 tools/check-cupid-display-probe.py /path/to/artifacts --case outside
```

The emulator saves each rendered phase, counts every expected MMIO read, rejects
MMIO writes, checks selected-surface pixels and requires the reset path. Delays
are skipped. Physical display, MMU/IOMMU state and bootloader handoff are not
modeled; passing host checks does not establish a hardware result.
