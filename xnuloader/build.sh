#!/bin/bash
# Build the XNU loader as a freestanding AArch64 UEFI application.
set -e
cd "$(dirname "$0")"
options=()
if [ "${DEVICE:-}" = cupid ]; then
  options+=("-DCUPID_LOADER=1")
fi
if [ -n "${PAYLOAD_BASE:-}" ]; then
  [[ "$PAYLOAD_BASE" =~ ^0x[0-9a-fA-F]+$ ]] || { echo "invalid PAYLOAD_BASE" >&2; exit 1; }
  options+=("-DPAYLOAD_BASE=${PAYLOAD_BASE}ULL")
fi
clang "${options[@]}" --target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector -fshort-wchar \
  -mgeneral-regs-only -O1 -Wall -Wextra -Wno-unused-parameter -c loader.c -o loader.obj
# /base: UEFI loads an image at its preferred address when that is free. The PE default (0x140000000)
# is in the middle of the phone's largest block of RAM, which XNU needs in one piece.
lld-link /subsystem:efi_application /entry:efi_main /nodefaultlib /base:0xA1000000 /out:loader.efi loader.obj
printf '%s %s\n' "${DEVICE:-auto}" "${PAYLOAD_BASE:-0xF0000000}" > loader.target
ls -la loader.efi
