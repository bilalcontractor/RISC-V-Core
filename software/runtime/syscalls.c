/* syscalls.c - minimal newlib retargeting for HolyCore bare-metal C.
 *
 * newlib's libc calls out to a handful of _xxx "syscalls" for I/O and heap.
 * We link with --specs=nosys.specs, which supplies stub versions of all of
 * them (each just fails with ENOSYS), and override only the two that need to
 * do something real on this core:
 *
 *   _write - route bytes to the simulation UART (makes printf/puts work),
 *   _sbrk  - hand out heap memory (makes malloc work).
 *
 */
#include <errno.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

/* UART MMIO. Must match __mmio_base in link_c.ld (which is what crt0.s programs
 * into the non-cachable-range CSRs), and hello.s / sim_uart / uart_bridge. */
#define UART_TX      (*(volatile unsigned int *)0x0000E010)  /* write a byte to transmit */
#define UART_STATUS  (*(volatile unsigned int *)0x0000E014)  /* bit3 = TX busy           */
#define UART_TX_BUSY 0x8

/* Heap bounds from link_c.ld: [__heap_start, __heap_end) == [_end, __mmio_base).
 * The heap stops at the bottom of the UART window, which sits between the heap
 * and the descending stack -- so refusing to cross __heap_end is what keeps a
 * growing heap out of both the window and the stack above it. */
extern char __heap_start;
extern char __heap_end;

static char *heap_ptr = &__heap_start;

// Called from crt0.s after .bss is zeroed and before main. Forces stdout unbuffered
void __holycore_init(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
}

void *_sbrk(int incr)
{
    char *prev = heap_ptr;
    if (heap_ptr + incr > &__heap_end) {
        errno = ENOMEM;
        return (void *)-1;
    }
    heap_ptr += incr;
    return prev;
}

int _write(int fd, const char *buf, int len)
{
    (void)fd;  // everything (stdout/stderr) goes to the one UART 
    for (int i = 0; i < len; i++) {
        while (UART_STATUS & UART_TX_BUSY) {
            // spin until the TX register is ready
        }
        UART_TX = (unsigned char)buf[i];
    }
    return len;
}