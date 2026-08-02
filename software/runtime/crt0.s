# crt0.s - C runtime startup for bare-metal programs (used by build_c.sh).
#
# The CPU resets with PC=0, so _start must be the very first thing in the image;
# link_c.ld places this file's `.text.init` section at 0x0. Responsibilities:
#   1. open the non-cachable MMIO window so UART stores reach the AXI-Lite bus,
#   2. point mtvec at trap_handler so a fault is reported instead of rebooting,
#   3. set up gp (linker-relaxed globals) and sp (top of RAM),
#   4. zero .bss (C assumes statics start at 0),
#   5. force stdout unbuffered, then call main(), then park in a self-loop so
#      run_program_test detects the end.

    .section .text.init, "ax"
    .globl _start
_start:
    # --- 1. Open the non-cachable window (0x0000E000..0x0000E200) so loads and
    #        stores to the UART regs bypass the data cache. The bounds come from
    #        link_c.ld, which is also what places the window between the heap and
    #        the stack, so these two writes never drift from the memory map. ---
    la    t0, __mmio_base
    la    t1, __mmio_limit
    csrw  0x7C1, t0            # non_cachable_base
    csrw  0x7C2, t1            # non_cachable_limit

    # --- 2. Install the trap vector. ---
    # mtvec resets to 0, which is also _start's address, so until this runs any
    # exception vectors straight back into the reset path: the program silently
    # restarts and re-faults forever, with no output saying why. Done after the
    # MMIO window (those four instructions cannot trap) so the handler already
    # has a working UART by the time it can be reached.
    #
    # Per spec mtvec[1:0] is MODE and the vector is mtvec[31:2]<<2, but the PC
    # mux consumes mtvec raw, so the address must arrive 4-byte aligned --
    # trap_handler's .align 2 is what guarantees that.
    la    t0, trap_handler
    csrw  mtvec, t0

    # --- 3. Global pointer (must not be relaxed away) and stack pointer. ---
    .option push
    .option norelax
    la    gp, __global_pointer$
    .option pop
    la    sp, _stack_top

    # --- 4. Zero the .bss section. ---
    la    t0, __bss_start
    la    t1, __bss_end
bss_clear:
    bgeu  t0, t1, bss_done
    sw    zero, 0(t0)
    addi  t0, t0, 4
    j     bss_clear
bss_done:

    # --- 5. Runtime init, then main(argc=0, argv=NULL), then park on return. ---
    # __holycore_init (syscalls.c) forces stdout unbuffered. It MUST run before
    # the first printf: with a real heap newlib would otherwise buffer stdout,
    # and since we park below instead of calling exit() nothing would ever be
    # flushed and every byte of UART output would be lost. 

    call  __holycore_init
    li    a0, 0
    li    a1, 0
    call  main
park:
    j     park

# ---------------------------------------------------------------------------
# Trap handler
#
# Prints "TRAP mcause=... mepc=... mtval=..." and halts. Deliberately does NOT
# mret: every exception this core raises (misaligned load/store, illegal
# instruction, ebreak, ecall) is a bug in the program, and mepc points AT the
# faulting instruction rather than past it, so returning would just re-execute
# it. 
# Written in bare assembly with no calls into libc and no use of the stack: a
# trap can fire from inside printf, or because sp itself went bad, and a
# handler that depended on either would re-trap and lose the diagnostic. For
# the same reason it never returns, so clobbering the caller's registers is
# fine -- but ra is left alone so mepc/ra still show the faulting context in a
# waveform dump.
# ---------------------------------------------------------------------------
    .align 2                   # mtvec is used raw by the PC mux: keep bits [1:0] clear
    .globl trap_handler
trap_handler:
    la    a0, trap_msg_cause
    call  trap_puts
    csrr  a0, mcause
    call  trap_puthex
    la    a0, trap_msg_epc
    call  trap_puts
    csrr  a0, mepc
    call  trap_puthex
    la    a0, trap_msg_tval
    call  trap_puts
    csrr  a0, mtval
    call  trap_puthex
    la    a0, trap_msg_nl
    call  trap_puts
trap_park:
    j     trap_park

# trap_putc: transmit the byte in a0. Spins on UART_STATUS bit 3 (TX busy),
# matching syscalls.c's _write. Clobbers t0/t1; links through t6 so callers
# keep their own ra.
trap_putc:
    li    t0, 0x0000E014       # UART_STATUS
1:  lw    t1, 0(t0)
    andi  t1, t1, 0x8          # UART_TX_BUSY
    bnez  t1, 1b
    li    t0, 0x0000E010       # UART_TX
    sw    a0, 0(t0)
    jr    t6

# trap_puts: print the NUL-terminated string at a0. Clobbers t0-t2, t6, a0.
trap_puts:
    mv    t2, a0
1:  lbu   a0, 0(t2)
    beqz  a0, 2f
    jal   t6, trap_putc
    addi  t2, t2, 1
    j     1b
2:  ret

# trap_puthex: print a0 as 8 lowercase hex digits, MSB first. Avoids t0/t1
# across the call since trap_putc clobbers them. Clobbers t0-t6, a0.
trap_puthex:
    mv    t3, a0               # value being printed
    li    t4, 28               # shift for the current nibble
1:  srl   a0, t3, t4
    andi  a0, a0, 0xf
    li    t5, 10
    blt   a0, t5, 2f
    addi  a0, a0, 87           # 'a' - 10
    j     3f
2:  addi  a0, a0, 48           # '0'
3:  jal   t6, trap_putc
    addi  t4, t4, -4
    bgez  t4, 1b
    ret

    .section .rodata
trap_msg_cause:
    .asciz "\nTRAP mcause="
trap_msg_epc:
    .asciz " mepc="
trap_msg_tval:
    .asciz " mtval="
trap_msg_nl:
    .asciz "\n"
