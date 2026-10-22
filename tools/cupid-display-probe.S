/* Standalone Linux Image entry; RAM boot only. See cupid-display-probe.c. */
.section .text.entry, "ax"
.global _start
_start:
  .inst 0x91005a4d
  b entry
  .quad 0
  .quad 0x200000
  .quad 0xa
  .quad 0, 0, 0
  .ascii "ARM\x64"
  .long 0
entry:
  msr daifset, #15
  adr x9, vectors
  mrs x10, CurrentEL
  cmp x10, #8
  b.eq el2
  cmp x10, #4
  b.ne probe_reset
  msr vbar_el1, x9
  b ready
el2:
  msr vbar_el2, x9
ready:
  isb
  adr x9, probe_stack_top
  mov sp, x9
  bl probe_main
.global probe_reset
probe_reset:
  movz x0, #9
  movk x0, #0x8400, lsl #16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
stopped:
  wfe
  b stopped
/* Exception path uses no stack, C code, further MMIO or timer accesses. */
fault:
  movz x9, #0xb800, lsl #16
  movz w10, #0
  movk w10, #0xff, lsl #16
  ldr w11, =2592000
fault_paint:
  str w10, [x9], #4
  subs w11, w11, #1
  b.ne fault_paint
  dsb sy
  /* Briefly leave red visible. A counter fault cannot recursively trap here. */
  movz x11, #0xffff
  movk x11, #0x3ff, lsl #16
fault_wait:
  subs x11, x11, #1
  b.ne fault_wait
  b probe_reset
.balign 2048
vectors:
.rept 16
  b fault
  .space 124
.endr
.ltorg
.section .bss.stack, "aw", %nobits
.balign 16
probe_stack:
  .space 16384
probe_stack_top:
