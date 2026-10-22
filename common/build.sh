#!/bin/bash
# Build everything a device needs, in order, skipping what cannot be built on this machine.
#
# usage: common/build.sh <device> [userland/build.sh variables...]
#   common/build.sh qemu-virt
#   common/build.sh redwood GL=1
#
#   1. kernel   xnu/apply.sh, xnu-deps/setup.sh, xnu-build.sh   -- only with theos + iPhoneOS16.5.sdk,
#                                                                  otherwise prebuilt/ is used
#   2. loader   xnuloader/build.sh                              -- only with clang + lld-link
#   3. images   userland/build.sh (REST=1 and the profile's USERLAND_VARS)
#                                                               -- needs ios165/fetch.sh to have run
#   4. boot     mkxnuimg.py -> out/<device>-boot.img             -- phones: the UEFI image for `fastboot boot`
#
#   SKIP="kernel loader images boot"   leave steps out
. "$(dirname "$(readlink -f "$0")")/lib.sh"
load_device "$1"; shift
skip() { [[ " $SKIP " == *" $1 "* ]]; }
mkdir -p out

if ! skip kernel; then
	if [ -d "${THEOS:-$HOME/theos}/sdks/iPhoneOS16.5.sdk" ] && command -v clang >/dev/null; then
		[ -d xnu-src ] || xnu/apply.sh
		[ -x xnu-deps/host/bin/ld64 ] || xnu-deps/setup.sh
		# Wi-Fi radio driver (phones with a WCN6750): fetched and built once
		[ "$WIFI_ATH11K" = 1 ] && [ ! -f xnu-deps/build/ath11k/out/ath11k.o ] && { tools/mk-ath11k.sh && tools/mk-wlfw.sh; }
		# the export check fails after the kernel is linked, on purpose (xnu/README.md): judge by the file
		touch out/.kernel-start
		./xnu-build.sh -j"$(nproc)" -k > out/kernel-build.log 2>&1 || true
		K=xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837
		[ -f $K ] && { [ $K -nt out/.kernel-start ] || ! grep -q "error:" out/kernel-build.log; } &&
			echo "build: kernel $(stat -c %s $K) bytes" || die "kernel build failed, see out/kernel-build.log"
	else
		echo "build: no theos/iPhoneOS16.5.sdk: using prebuilt/mach.development.bcm2837"
	fi
fi

if ! skip loader; then
	if command -v clang >/dev/null && command -v lld-link >/dev/null; then
		PAYLOAD_BASE=$PAYLOAD_BASE xnuloader/build.sh && echo "build: loader xnuloader/loader.efi"
	else
		[ "$DEVICE" = cupid ] && die "cupid requires clang and lld-link to build its own loader"
		echo "build: no clang/lld-link: using prebuilt/loader.efi"
	fi
fi

if ! skip images; then
	have_userland
	[ -d ios165/rootfs ] || die "no iOS files yet: run ios165/fetch.sh first (it downloads them from Apple to this machine)"
	env KERNEL_ROOT="$ROOT" FIRMWARE_ROOT="${FIRMWARE_ROOT:-$ROOT}" REST=1 $USERLAND_VARS "$@" userland/build.sh
fi

if ! skip boot && [ "$KIND" = phone ]; then
	# An unfinished port must not silently package redwood's UEFI, shim or DTB.
	if [ "$UEFI_TARGET" != redwood ]; then
		[ -n "$FD_BASE" ] && [ -n "$FD_SIZE" ] && [ -n "$PAYLOAD_BASE" ] ||
			die "boot addresses for $DEVICE are not configured; see docs/CUPID.md"
		F=${UEFI_FD:-Mu-Silicium/Build/${UEFI_TARGET}Pkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd}
		[ -f "$F" ] && [ -d Mu-Silicium/BootShim ] ||
			die "$DEVICE requires its own built UEFI and BootShim tree"
		D=${DTB:-Mu-Silicium/Resources/DTBs/${UEFI_TARGET}.dtb}
		[ -f "$D" ] || die "no $DEVICE DTB: $D"
	fi
	# the UEFI with the loader inside, the way `xl enter` makes it: the loader then brings up its USB link
	L=xnuloader/loader.efi; [ -f $L ] || L=prebuilt/loader.efi
	[ "$DEVICE" != cupid ] || [ "$L" = xnuloader/loader.efi ] || die "no source-built cupid loader"
	if [ "$DEVICE" = cupid ]; then
		[ "$(cat xnuloader/loader.target 2>/dev/null)" = "$DEVICE $PAYLOAD_BASE" ] ||
			die "loader target differs from cupid profile; rebuild without SKIP=loader"
	fi
	python3 xnuloader/mkpayload.py -o out/usb-payload.bin loader.efi=$L --usb > /dev/null
	FD_BASE=$FD_BASE FD_SIZE=$FD_SIZE PAYLOAD_BASE=$PAYLOAD_BASE UEFI_FD=$UEFI_FD DTB=$DTB UEFI_TARGET=$UEFI_TARGET BOOT_HEADER_VERSION=${BOOT_HEADER_VERSION:-1} \
		python3 mkxnuimg.py -p out/usb-payload.bin -o out/$DEVICE-boot.img
	echo "build: out/$DEVICE-boot.img -- boot it with: fastboot boot out/$DEVICE-boot.img (or common/run.sh $DEVICE)"
fi
