/* hello_c.c - first C program for core. Exercises the full C runtime:
 *   - printf (newlib libc -> _write -> UART),
 *   - runtime integer multiply (i * i -> __mulsi3 in libgcc),
 *   make c C=hello_c   (from tb/cpu)
 */
#include <stdio.h>

int main(void)
{
    int total = 0;
    puts("Hello from C!");
    for (int i = 1; i <= 50; i++) {
        total += i * i;
    }
    printf("sum of squares 1..50 = %d\n", total);

    return 0;
}
