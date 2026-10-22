/* RAM-only Linux handoff probe. No UEFI, storage, USB, or stack dependency. */
.section .text, "ax"
.global _start
_start:
  .inst 0x91005a4d              /* Linux Image MZ instruction */
  b entry
  .quad 0                      /* text_offset: same as stock Cupid kernel */
  .quad 0x200000               /* padded image extent; DTB follows here */
  .quad 0xa                    /* little endian, 4 KiB, arbitrary placement */
  .quad 0, 0, 0
  .ascii "ARM\x64"
  .long 0
entry:
  msr daifset, #15
  /* Reset on an exception as well, so an inaccessible timer is observable. */
  adr x9, vectors
  mrs x10, CurrentEL
  cmp x10, #8
  b.eq el2
  cmp x10, #4
  b.ne reset
  msr vbar_el1, x9
  b ready
el2:
  msr vbar_el2, x9
ready:
  isb
  mrs x20, cntfrq_el0
  cbz x20, reset
  mrs x21, cntpct_el0
  lsl x20, x20, #3             /* eight seconds */
#ifdef CUPID_PROBE_DISPLAY
  /* Best effort only: stock panel/scanout may already be disabled by ABL. */
  movz x9, #0xb800, lsl #16
  movz w10, #0xff00
  movk w10, #0x00ff, lsl #16   /* yellow, little-endian BGRX */
  ldr w11, =2592000            /* 1080 * 2400 pixels, within splash region */
paint:
  str w10, [x9], #4
  sub w11, w11, #1
  cbnz w11, paint
  dsb sy
#endif
wait:
  mrs x9, cntpct_el0
  sub x9, x9, x21
  cmp x9, x20
  b.lo wait
reset:
  movz x0, #9
  movk x0, #0x8400, lsl #16   /* PSCI SYSTEM_RESET, SMC per supplied FDT */
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
stopped:
  wfe
  b stopped
.balign 2048
vectors:
.rept 16
  b reset
  .space 124
.endr
.ltorg
