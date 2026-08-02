/* linklist.c - measures the heap and the stack with a singly linked list.
 *
 * The 64 KiB map gave malloc a real heap for the first time (it used to have
 * 244 bytes). This program spends all of it: it appends nodes until malloc
 * refuses, walks the list, and reports how much of the map each region actually
 * ended up using.
 *
 *   1. grow  - append nodes until malloc returns NULL, so the node count is a
 *              direct measurement of the heap rather than a number we picked,
 *   2. walk  - advance through the list checking every node still holds what it
 *              was given (catches a heap that overlaps .bss or the MMIO window),
 *   3. recurse - walk a bounded prefix recursively and watch sp descend, which
 *              measures the stack the same way the grow phase measures the heap,
 *   4. thin  - free every other node and re-walk, so the list survives a
 *              fragmented heap,
 *   5. reuse - free the rest and re-allocate, checking the freed chunks come
 *              back (a heap that only ever grows would fail here).
 *
 *   make c C=linklist MAX_CYCLES=1200000   (from tb/cpu)
 *
 * MAX_NODES below caps the list at around 40% of the heap. Raise it (and
 * MAX_CYCLES with it) to take the whole heap, at ~3x that.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

/* Laid out from the linker script (link_c.ld):
 *   _end/__heap_start .. __heap_end   heap, grows up
 *   __heap_end .. _stack_top          UART MMIO window, then the stack coming down */
extern char _end;
extern char __heap_end;
extern char _stack_top;

typedef struct node {
    struct node *next;
    unsigned index;      /* position in the list, assigned at append time */
    unsigned tag;        /* derived from index; re-checked on every walk   */
} node_t;

/* Cheap per-node fingerprint. Shifts and xors only: rv32i has no multiply, so
 * anything with a `*` in it becomes a call into libgcc's __mulsi3, and this runs
 * once per node per walk. */
static unsigned tag_of(unsigned index)
{
    unsigned t = index ^ 0x5A5A5A5Au;

    t ^= t << 7;
    t ^= t >> 9;
    return t;
}

/*
 * 1024 spends ~20 KB, a bit over 40% of the heap, for ~850k instructions -- enough
 * for the frees to fragment it and the reuse phase to have real holes to allocate
 * out of, without the wait. */
#define MAX_NODES 1024

/* Deep enough to show sp moving, shallow enough that it cannot reach the MMIO
 * window: the stack is _stack_top - __mmio_limit == 7.5 KiB, and a frame here is
 * a couple of dozen bytes. */
#define RECURSE_NODES 64

/* ---------------------------------------------------------------- */
/* Grow: append until the heap says no. Appending (rather than pushing at the
 * head) keeps indices in memory order, so a walk that finds them out of order
 * means the list, not the ordering, is wrong.                                  */
/* ---------------------------------------------------------------- */
static node_t *grow(unsigned *count_out)
{
    node_t *head = NULL, *tail = NULL;
    unsigned count = 0;

    while (count < MAX_NODES) {
        node_t *n = malloc(sizeof *n);

        if (!n) {
            break;              /* heap exhausted: _sbrk hit __heap_end */
        }
        n->next = NULL;
        n->index = count;
        n->tag = tag_of(count);

        if (tail) {
            tail->next = n;
        } else {
            head = n;
        }
        tail = n;
        count++;
    }

    *count_out = count;
    return head;
}

/* Advance through the list. Returns the number of nodes seen, or -1 on the first
 * node whose tag doesn't match its index. */
static int walk(const node_t *head)
{
    int seen = 0;

    for (const node_t *n = head; n; n = n->next) {
        if (n->tag != tag_of(n->index)) {
            printf("  corrupt node %d: index %u tag %08x != %08x\n",
                   seen, n->index, n->tag, tag_of(n->index));
            return -1;
        }
        seen++;
    }
    return seen;
}

/* Same walk, recursively, tracking the lowest stack address reached.
 *
 * The mark is carried as an integer, not a char*: each frame's marker is dead by
 * the time the caller looks at it, and we only ever compare and print the
 * address, never dereference it. */
static unsigned walk_recursive(const node_t *n, int budget, unsigned *low)
{
    char marker;
    unsigned sp = (unsigned)(uintptr_t)&marker;

    if (sp < *low) {
        *low = sp;
    }
    if (!n || budget == 0) {
        return 0;
    }
    return n->tag + walk_recursive(n->next, budget - 1, low);
}


static unsigned free_descending(node_t *head)
{
    unsigned freed = 0;

    while (head) {
        node_t *next = head->next;

        free(head);
        head = next;
        freed++;
    }
    return freed;
}

/* Reverse in place, so a list built low-to-high comes back high-to-low. */
static node_t *reverse(node_t *head)
{
    node_t *prev = NULL;

    while (head) {
        node_t *next = head->next;

        head->next = prev;
        prev = head;
        head = next;
    }
    return prev;
}

/* Drop every other node. malloc gets the freed chunks back interleaved with live
 * ones, which is the state the reuse phase below has to allocate out of. */
static unsigned thin(node_t *head)
{
    node_t *dead = NULL;

    for (node_t *n = head; n && n->next; n = n->next) {
        node_t *victim = n->next;

        n->next = victim->next;
        victim->next = dead;
        dead = victim;
    }
    return free_descending(dead);
}

int main(void)
{
    node_t *head;
    unsigned count, freed;
    char *heap_before, *heap_after;
    unsigned sp_main = (unsigned)(uintptr_t)&head;   /* where main's frame sits */
    unsigned low = sp_main;                          /* deepest sp the recursion reaches */
    int seen;

    printf("heap  0x%08x .. 0x%08x (%d bytes)\n",
           (unsigned)&_end, (unsigned)&__heap_end, (int)(&__heap_end - &_end));
    printf("stack top 0x%08x, node %d bytes\n\n",
           (unsigned)&_stack_top, (int)sizeof(node_t));

    /* 1. grow */
    heap_before = sbrk(0);
    head = grow(&count);
    heap_after = sbrk(0);
    if (!count) {
        puts("no nodes allocated -- the heap is empty");
        return 1;
    }
    printf("grew to %u nodes, sbrk 0x%08x -> 0x%08x (%d bytes, %d per node)\n",
           count, (unsigned)heap_before, (unsigned)heap_after,
           (int)(heap_after - heap_before), (int)(heap_after - heap_before) / (int)count);
    if (heap_after > &__heap_end) {
        puts("FAIL: the heap ran past __heap_end into the UART window");
        return 1;
    }
    if (count == MAX_NODES) {
        puts("note: stopped at MAX_NODES, so the heap was never exhausted");
    }

    /* 2. walk */
    seen = walk(head);
    if (seen != (int)count) {
        printf("FAIL: walk saw %d of %u nodes\n", seen, count);
        return 1;
    }
    printf("walked %d nodes, all tags intact\n", seen);

    /* 3. recurse */
    walk_recursive(head, RECURSE_NODES, &low);
    printf("recursed %d deep, sp reached 0x%08x (%d bytes of stack, %d per frame)\n",
           RECURSE_NODES, low, (int)((unsigned)(uintptr_t)&_stack_top - low),
           (int)(sp_main - low) / RECURSE_NODES);

    /* 4. thin */
    freed = thin(head);
    seen = walk(head);
    if (seen != (int)(count - freed)) {
        printf("FAIL: after freeing %u, walk saw %d, expected %u\n",
               freed, seen, count - freed);
        return 1;
    }
    printf("freed %u nodes, walked the remaining %d\n", freed, seen);

    /* 5. reuse: the freed holes should cover this without moving sbrk. */
    heap_before = sbrk(0);
    {
        node_t *refill[16];
        unsigned got = 0;

        for (unsigned i = 0; i < 16; i++) {
            refill[i] = malloc(sizeof *refill[i]);
            if (refill[i]) {
                got++;
            }
        }
        heap_after = sbrk(0);
        for (unsigned i = 0; i < got; i++) {
            free(refill[i]);
        }
        printf("re-allocated %u/16 nodes from freed space, sbrk moved %d bytes\n",
               got, (int)(heap_after - heap_before));
        if (got != 16) {
            puts("FAIL: freed chunks were not handed back");
            return 1;
        }
    }

    freed += free_descending(reverse(head));
    printf("\nfreed %u nodes in total, heap ends at 0x%08x\n", freed, (unsigned)sbrk(0));
    puts("linklist: PASS");
    return 0;
}
