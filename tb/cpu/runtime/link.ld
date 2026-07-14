/* Shared linker script for bare-metal test programs (used by build_asm.sh).
 * Packs .text, .rodata and .data contiguously starting at address 0x0 so the
 * objcopy'd binary is a compact, gap-free image the testbench loads at 0x0.
 * (The default linker script would page-align .rodata to 0x1000 and bloat the
 * hex with thousands of zero words.) */
ENTRY(_start)
SECTIONS
{
    . = 0x00000000;
    .text : {
        *(.text*)
        *(.rodata*)
        *(.data*)
    }
}
