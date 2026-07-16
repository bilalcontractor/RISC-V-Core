# crt0.s - C runtime startup for bare-metal programs (used by build_c.sh).
#
# The CPU resets with PC=0, so _start must be the very first thing in the image;
# link_c.ld places this file's `.text.init` section at 0x0. Responsibilities:
#   1. open the non-cachable MMIO window so UART stores reach the AXI-Lite bus,
#   2. set up gp (linker-relaxed globals) and sp (top of RAM),
#   3. zero .bss (C assumes statics start at 0),
#   4. call main(), then park in a self-loop so run_program_test detects the end.

    .section .text.init, "ax"
    .globl _start
_start:
    # --- 1. Open the non-cachable window 0x2000..0x2200 (same as hello.s) so
    #        loads/stores to the UART regs bypass the data cache. ---
    lui   t0, 0x2              # t0 = 0x00002000  (base)
    addi  t1, t0, 0x200        # t1 = 0x00002200  (limit)
    csrw  0x7C1, t0            # non_cachable_base  = 0x2000
    csrw  0x7C2, t1            # non_cachable_limit = 0x2200

    # --- 2. Global pointer (must not be relaxed away) and stack pointer. ---
    .option push
    .option norelax
    la    gp, __global_pointer$
    .option pop
    la    sp, _stack_top

    # --- 3. Zero the .bss section. ---
    la    t0, __bss_start
    la    t1, __bss_end
bss_clear:
    bgeu  t0, t1, bss_done
    sw    zero, 0(t0)
    addi  t0, t0, 4
    j     bss_clear
bss_done:

    # --- 4. main(argc=0, argv=NULL), then park forever on return. ---
    li    a0, 0
    li    a1, 0
    call  main
park:
    j     park
