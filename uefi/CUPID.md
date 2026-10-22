# Cupid UEFI diagnostic build

The platform sources target Xiaomi 12 (SM8450), using the supplied runtime FDT
and stock `BOOT.MXF.2.0-01018.3-WAIPIO-1` configuration. Mu is pinned by `BASE`.
The stock binaries are installed locally from the user's `uefi.img`, separate
from the source repository. No successful hardware boot is established yet.

## Prepare local inputs

Build a fresh checkout of [UEFIReader](https://github.com/WOA-Project/UEFIReader)
with .NET 8, then extract the supplied **uefi.img**:

```sh
dotnet UEFIReader.dll /path/to/fresh-cupid-images/uefi.img /path/to/codex-cupid/references/cupid-uefi-extracted
```

Clone Mu-Silicium at `uefi/BASE` with recursive submodules into the separate
reference folder and link it as `Mu-Silicium` in this kernel checkout. Then:

```sh
python3 uefi/prepare-cupid.py \
  --firmware-dir ../codex-cupid/references/cupid-uefi-extracted/BOOT.MXF.2.0-01018.3-WAIPIO-1 \
  --fdt ../Documents/fdt-cupid/fdt
```

This verifies Mu's revision, checks referenced firmware files, applies the
shared HackiOS patch once, and copies Cupid sources, stock binaries and FDT.
It is repeatable on the prepared tree. It does not extract `payload.bin`.

## Build

Install the host packages listed in Mu's setup instructions and its Python
requirements in a separate virtual environment. On a newly prepared Mu tree,
run both dependency stages explicitly before invoking the build:

```sh
cd Mu-Silicium
python3 Platforms/Xiaomi/cupidPkg/DeviceBuild.py --setup -t RELEASE
python3 Platforms/Xiaomi/cupidPkg/DeviceBuild.py --update -t RELEASE
python3 build_uefi.py -d cupid -r RELEASE
cd ..
SKIP='kernel images' common/build.sh cupid
```

Mu's own `Mu-cupid.img` has no XNUP loader container. Use HackiOS's packed
`out/cupid-boot.img` for the USB loader diagnostic. The packer rebuilds BootShim
with the correct Cupid payload address. Do not select Redwood's prebuilt UEFI.

```sh
python3 tools/check-cupid-boot.py \
  --image out/cupid-boot.img --shim Mu-Silicium/BootShim/BootShim.bin \
  --fd Mu-Silicium/Build/cupidPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --payload out/usb-payload.bin --loader xnuloader/loader.efi \
  --fdt ../Documents/fdt-cupid/fdt
```

The validator compares the actual inputs byte for byte, checks image/PE/XNUP
structure and shim addresses, and rejects payload overlap with the runtime
FDT's explicit reserved regions. It cannot validate physical display scanout,
vendor protocol compatibility, or firmware handoff on the phone.

## Hardware test

From Windows, enter unlocked stock fastboot and run `fastboot boot IMAGE`.
After USB reconnects, `fastboot getvar product` should report `xnuloader`.
Collect `fastboot oem log` followed by `fastboot get_staged cupid-loader.log`.
`fastboot oem memmap` followed by the same log commands adds the firmware map.
Report the screen state even if USB does not reconnect. A power-key reset is
needed if this first diagnostic hangs: Cupid's watchdog is not yet configured.

## Driver compatibility

The first diagnostic uses **unmodified Cupid stock drivers**, not patched
Samsung or Redwood binaries. The Mu S22 port on the same SoC documents changes
to ClockDxe, PmicDxe/SPMIDxe, TzDxeLA, UFSDxe and UsbConfigDxe. Those are relevant
reference points, but their firmware offsets differ; they are not applied to
Cupid by this preparation script. Hardware results will determine the next
patches, with disassembly and input hashes recorded before modification.

The display uses SimpleFbDxe over the `0xb8000000` splash reservation. Its GOP
geometry is configured as 1080 by 2400, 32-bit BGRX; physical scanout and stride
still require hardware confirmation. Raw HackiOS log partition writes and
firmware log syncing are disabled in this diagnostic configuration.

## v001 failure and revised placement

The user booted v001: stock fastboot reported sending and booting OKAY, then the
phone stayed black and USB did not reconnect. A power-key reboot recovered
Android. This establishes transfer acceptance; no custom code execution is proven.

The supplied uefi.img places SEC at 0xa7000000. Its first MiB contains the HOB
registration function signatures and scheduler/DTB GUIDs scanned by Mu's
PlatformPeiLib/XblProtocols.c. v001 replaced that area and omitted FD Reserved.
Cupid now reserves the first MiB and builds a 3 MiB FD at 0xa7100000. The packed
shim must use the same updated destination and size. This corrects a concrete
firmware compatibility mismatch; hardware tests must establish the hang's cause.
The frozen v001 image can be checked using `--fd-base 0xa7000000 --fd-size 0x400000`.

See tools/build-cupid-probe.py for independent handoff diagnostics before UEFI.

## Early SEC diagnostics

Cupid enables CUPID_EARLY_DIAGNOSTICS in its platform build only. The preparation
script installs cupid-diagnostics.patch and Sec/CupidDiagnostics.h. Other device
builds compile the checkpoint calls as no-ops.

| Stage | Color (BGRX) | Reached point |
| --- | --- | --- |
| 0 | Red | SEC exception handler; eight-second delayed reset |
| 1 | Yellow | SecEntry, after assembly entry/stack setup |
| 2 | Cyan | Before PlatformInitialize (core wake and SMMU detach) |
| 3 | Green | After PlatformInitialize |
| 4 | Blue | After memory initialization |
| 5 | Magenta | After platform HOB recovery |
| 6 | White | After FV decompression |
| 7 | Orange | Before calling DXE core |

Each stage holds its color for one second. A sec-stop XNUP entry containing a
binary little-endian u32 stage selects a stop; that stage then waits eight
seconds and requests PSCI SYSTEM_RESET. The checkpoint code writes only the
splash framebuffer and reads the reserved payload; it uses no storage or USB.
The ordinary loader diagnostic omits sec-stop and continues through all stages.
The exception handler always shows red and requests reset in diagnostic builds.
These colors require continued scanout, which vendor initialization can change.

A frozen v003 baseline validated by tools/check-cupid-boot.py can produce the
stopping variants with tools/pack-cupid-sec-stops.py --artifact ARTIFACT_DIR.
Always test stage1 before advancing. Full source/userland compilation and APFS
validation do not establish a working XNU or iOS boot.
