/* hello_c.c - first C program for core. Exercises the full C runtime:
 *   - printf (newlib libc -> _write -> UART),
 *   - runtime integer multiply (i * i -> __mulsi3 in libgcc),
 *   ./build_c.sh hello_c && make run HEX=hello_c_imemory.hex
 */
#include <stdio.h>

int main(void)
{
    puts("Hello from C!");
    for (int i = 1; i <= 10; i++) {
        printf("  %d squared = %d\n", i, i * i);
    }
    return 0;
}
