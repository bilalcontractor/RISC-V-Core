/* Linker script for bare-metal C on HolyCore (used by build_c.sh).
 *
 * Memory map for run_program_test's RAM (must match sim_common.py's MEM_BYTES):
 *   0x00000000 .. 0x0000E000   .text/.rodata/.data/.bss, then heap (grows up)
 *   0x0000E000 .. 0x0000E200   UART MMIO window (non-cachable; opened by crt0.s)
 *   0x0000E200 .. 0x00010000   stack (grows down from _stack_top)
 *
 * The MMIO window deliberately sits between the heap and the stack: the heap
 * climbs toward it from below and the stack descends toward it from above, so
 * neither can silently run straight into the other 
 *
 * The window used to sit at 0x2000 in a 16 KiB RAM, which put it halfway up and
 * capped the image + heap at 8 KiB -- the image had grown to 97% of that and the
 * heap was down to 244 bytes. What fixed that was growing RAM to 64 KiB and
 * moving the window near the top.
 *
 * Loadable sections (.text/.rodata/.data) are packed contiguously from 0x0 so
 * `objcopy -O binary` yields the gap-free image init_memory() loads at 0x0.
 */
OUTPUT_ARCH(riscv)
ENTRY(_start)

__ram_base   = 0x00000000;
__ram_size   = 0x00010000;  /* 64 KiB -- MUST equal sim_common.py's MEM_BYTES */
__ram_top    = __ram_base + __ram_size;

/* UART window. Must stay 512-byte aligned and a multiple of 512: data_cache.sv
 * decodes non-cachable on address[31:9], so the low 9 bits of both bounds are
 * discarded. */

__mmio_base  = 0x0000E000;  /* -> non_cachable_base  (CSR 0x7C1) */
__mmio_limit = 0x0000E200;  /* -> non_cachable_limit (CSR 0x7C2) */

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
    __heap_end   = __mmio_base;                 /* _sbrk's wall: heap stops below the window */
    _stack_top   = __ram_top;                   /* stack grows down toward __mmio_limit      */
    __stack_size = _stack_top - __mmio_limit;   /* derived; what the stack actually gets     */

    ASSERT(__heap_start <= __heap_end,
        "C image + .bss overflow the region below the UART MMIO window")
    ASSERT(__mmio_limit <= __ram_top,
        "MMIO window runs past the top of RAM -- __ram_size shrank below __mmio_limit")
    ASSERT((__mmio_base & 0x1FF) == 0,
        "MMIO base must be 512-byte aligned (data_cache.sv decodes address[31:9])")
    ASSERT((__mmio_limit & 0x1FF) == 0,
        "MMIO limit must be 512-byte aligned (data_cache.sv decodes address[31:9])")
}
