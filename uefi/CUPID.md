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
