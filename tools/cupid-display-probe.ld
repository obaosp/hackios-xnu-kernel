ENTRY(_start)
SECTIONS {
  . = 0;
  .text : { KEEP(*(.text.entry)) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  .bss (NOLOAD) : { *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
  ASSERT(. < 0x200000, "probe exceeds Linux Image extent")
}
