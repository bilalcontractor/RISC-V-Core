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
 * These strong definitions win over nosys's library versions at link time.
 */
#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>

/* UART MMIO, matching hello.s / sim_uart / uart_bridge (tx_addr=0x2010). */
#define UART_TX      (*(volatile unsigned int *)0x00002010)  /* write a byte to transmit */
#define UART_STATUS  (*(volatile unsigned int *)0x00002014)  /* bit3 = TX busy           */
#define UART_TX_BUSY 0x8

/* Heap bounds from link_c.ld: [__heap_start, __heap_end) == [_end, 0x2000). */
extern char __heap_start;
extern char __heap_end;

static char *heap_ptr = &__heap_start;

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
    (void)fd;  /* everything (stdout/stderr) goes to the one UART */
    for (int i = 0; i < len; i++) {
        while (UART_STATUS & UART_TX_BUSY) {
            /* spin until the TX register is ready */
        }
        UART_TX = (unsigned char)buf[i];
    }
    return len;
}