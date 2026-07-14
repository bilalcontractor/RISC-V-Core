/* Linker script for bare-metal C on HolyCore (used by build_c.sh).
 *
 * Memory map for run_program_test's 16 KiB unified RAM (MEM_BYTES = 2**14):
 *   0x0000 .. 0x2000   .text/.rodata/.data/.bss, then heap (grows up)
 *   0x2000 .. 0x2200   UART MMIO window  (non-cachable; opened by crt0.s)
 *   0x2200 .. 0x4000   stack (grows down from _stack_top)
 *
 * The UART window deliberately splits RAM: the heap climbs toward it from
 * below and the stack descends toward it from above, so heap and stack can
 * never silently collide with each other -- each just hits the MMIO wall.
 *
 * Loadable sections (.text/.rodata/.data) are packed contiguously from 0x0 so
 * `objcopy -O binary` yields the gap-free image init_memory() loads at 0x0.
 */
OUTPUT_ARCH(riscv)
ENTRY(_start)

__mmio_base = 0x00002000;   /* UART window base -> non_cachable_base  */

SECTIONS
{
    . = 0x00000000;

    .text : {
        KEEP(*(.text.init))     /* crt0 _start MUST land at 0x0 (reset PC) */
        *(.text*)
        *(.rodata*)
        *(.srodata*)
    }

    .data : ALIGN(4) {
        __global_pointer$ = . + 0x800;
        *(.data*)
        *(.sdata*)
    }

    .bss (NOLOAD) : ALIGN(4) {
        __bss_start = .;
        *(.sbss*)
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    }

    _end         = .;
    __heap_start = .;
    __heap_end   = __mmio_base;    /* heap grows up to the MMIO window   */
    _stack_top   = 0x00004000;     /* top of 16 KiB RAM; stack grows down */

    ASSERT(__heap_start <= __mmio_base,
        "C image + .bss overflow the 0x0000-0x2000 region below the UART MMIO window")
}
