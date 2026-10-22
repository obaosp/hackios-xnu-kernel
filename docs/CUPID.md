# Xiaomi 12 (cupid) bring-up

This is an initial port from upstream sources. No phone boot has been validated.

The supplied live Android FDT identifies SM8450 and supplies:

| Item | Value |
| --- | --- |
| GIC distributor | 0x17100000, size 0x10000 |
| GIC redistributors | 0x17180000, size 0x200000, stride 0x40000 |
| CPU MPIDRs | 0x000 through 0x700 in steps of 0x100 |
| Little cores | 0–3 (lowest capacity-dmips-mhz) |
| PSCI conduit | SMC |
| Display splash reservation | 0xb8000000, size 0x2b00000 |
| GPU | Adreno730v2, qcom,adreno-gpu-gen7-0-1 |
| Touch | ST FTS, SPI controller 0x990000; IRQ GPIO21; reset GPIO20 |
| Touch coordinates | 10800 × 24000 (super resolution) |
| Wi-Fi | QCA6490, CNSS PCIe root complex 0; WLAN enable GPIO80 |
| Android boot / vendor_boot headers | version 4 |

The loader's framebuffer match uses the splash reservation base provisionally.
The first UEFI boot must confirm the GOP base before this is considered usable.
The kernel now accepts an explicit redistributor stride; the original default
continues to apply to redwood and QEMU.

## Boot platform

Cupid's supplied xbl.img is an early-stage bootloader, not its UEFI driver store.
The stock firmware has a separate uefi partition (also listed in LineageOS's
android_device_xiaomi_cupid/proprietary-firmware.txt). The user supplied uefi.img and xbl_config.img; UEFIReader extracted the drivers
and the original memory map from uefi.img into the separate local reference
folder. Do not substitute redwood's binary drivers.

The cupid profile preserves stock SEC at 0xa7000000..0xa7100000 and places
the new FD at 0xa7100000 (3 MiB). Mu scans the preserved SEC code for the live
Qualcomm scheduler and DTB-extension interfaces. Its XNUP
payload region is 0xf6000000..0xfa000000: this lies wholly in the supplied runtime
FDT RAM and overlaps none of its explicit reserved regions. The UEFI map reserves
it and shortens the stock DXE heap to 0xfa000000..0xffc00000. These choices still
require a successful hardware boot. Its initial boot arguments leave redwood-specific
touch, buttons, clocks, GPU, Wi-Fi, audio, and storage writes disabled. The
upstream ST FTS-free Goodix driver cannot drive this touchscreen; the upstream
Adreno 642L setup cannot initialize the Adreno 730.

## Workspace and sources

Kernel and userland remain independent repositories in sibling codex-xnu-kernel
and codex-xnu-userland directories. Source hashes and local analysis are recorded
in sibling codex-cupid. Existing local attempts are excluded. Firmware binaries
and runtime FDTs stay local.

## Build status and first hardware milestone

The first source-built Cupid UEFI FD (4 MiB), Cupid loader, XNU kernel (15,144,880
bytes) and minimal diagnostic APFS image exist. Mu's postbuild validation
passed 49 source-built PE images; the minimal APFS image passed `apfsck` and
the kernel APFS reader's comparison of all 14 entries. XNU linked successfully,
then hit the upstream documented IOKit export-list check failure.

The loader-only boot image has Android header v4 and a host-validated shim,
UEFI FD, XNUP container and appended supplied FDT. It does not launch iOS.
The v001 hardware test was accepted by stock fastboot but stayed black with no
USB reconnect, requiring a power-key reboot. It overwrote the stock SEC region;
this mismatch is corrected in the next build, with hardware causality still pending.
Stand-alone handoff probes isolate code execution from custom UEFI. See [the Cupid UEFI build instructions](../uefi/CUPID.md)
for preparation, structural validation, USB log collection, and the stock
driver compatibility limitations.

When using `xl`, set `DEVICE=cupid`. This selects the correct packing
addresses and conservative kernel arguments. Both the build script and `xl`
check `xnuloader/loader.target` to reject a loader built for another profile.
Touch, Adreno730, QCA6490 Wi-Fi and the other peripheral ports remain pending.

## First-stage probes

```sh
python3 tools/build-cupid-probe.py --fdt ../Documents/fdt-cupid/fdt \
  --output ../codex-cupid/artifacts/probe-v001
```

The reset probe uses a stock-compatible ARM64 header (text_offset0, flags0xa),
a 2 MiB padded Image, and the supplied appended FDT in boot header v4. It waits
eight seconds on the architectural counter then invokes PSCI SYSTEM_RESET via
SMC. Exception vectors request an immediate reset. It has no UEFI, USB, storage
or stack dependencies. Raw and gzip forms contain identical ARM64 Images.
The optional display probe writes yellow within the splash reservation; panel
scanout may already be disabled, so its visibility requires hardware validation.
Boot with fastboot boot; report transfer output and restart timing before
advancing to a new UEFI image.
