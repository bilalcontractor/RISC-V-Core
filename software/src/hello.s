# hello.s - prints "Hello, World!" through the simulation UART (sim_uart.sv).
#
# The CPU starts at
# address 0x0 (= _start). Stores to the UART TX register (0x0000E010) are snooped
# by sim_uart and printed with $write().
#
# This links with link.ld, which defines no symbols, so the MMIO addresses are
# hardcoded here. They must match __mmio_base/__mmio_limit in runtime/link_c.ld.
#
# Register usage:
#   x5  = pointer walking the string
#   x6  = UART TX register address      (0x0000E010)
#   x7  = UART STATUS register address  (0x0000E014)
#   x10 = current character
#   x11 = status scratch

    .section .text
    .globl _start
_start:
    # --- Open the non-cachable MMIO window 0x0000E000..0x0000E200 so UART stores
    #     bypass the data cache and go straight out the AXI-Lite bus. ---
    lui   x20, 0xE              # x20 = 0x0000E000  (base)
    addi  x21, x20, 0x200       # x21 = 0x0000E200  (limit)
    csrrw x0, 0x7C1, x20        # non_cachable_base  = 0x0000E000
    csrrw x0, 0x7C2, x21        # non_cachable_limit = 0x0000E200

    # --- Set up pointers ---
    la    x5, msg               # string pointer (resolved by the assembler)
    lui   x6, 0xE
    addi  x6, x6, 0x10          # x6 = 0x0000E010  (UART TX)
    addi  x7, x6, 0x4           # x7 = 0x0000E014  (UART STATUS)

loop:
    lbu   x10, 0(x5)            # load next character
    beq   x10, x0, done         # '\0' terminator -> finished
poll:
    lw    x11, 0(x7)            # read UART STATUS
    andi  x11, x11, 0x8         # TX-busy bit (bit 3); 0 = ready
    bne   x11, x0, poll         # spin while busy
    sb    x10, 0(x6)            # TX = char  -> sim_uart prints it
    addi  x5, x5, 1             # advance pointer
    j     loop
done:
    j     done                 # park forever

    # --- The message. Change this string, rebuild, done. ---
    .section .rodata
msg:
    .asciz "Hello, World!\n"
